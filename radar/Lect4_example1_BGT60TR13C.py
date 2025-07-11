# % ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# % SPS Short Course: Radar Signal Processing Mastery
# % Theory and Hands-On Applications with mmWave MIMO Radar Sensors
# % Date: 7-11 October 2024
# % Time: 9:00AM-11:00AM ET (New York Time)
# % Presenter: Mohammad Alaee-Kerahroodi
# % ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# % Website: https://radarmimo.com/
# % Email: info@radarmimo.com, mohammad.alaee@uni.lu
# % ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
import pprint
import queue
import sys
import threading
import time
import socket

import numpy as np
import pyqtgraph as pg
import scipy.signal as signal
import statsmodels.api as sm
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
from ifxradarsdk import get_version
from ifxradarsdk.fmcw import DeviceFmcw
from ifxradarsdk.fmcw.types import create_dict_from_sequence, FmcwSimpleSequenceConfig, FmcwSequenceChirp
from pyqtgraph.Qt import QtCore
from scipy.ndimage import uniform_filter1d
from scipy.signal import lfilter, firwin, find_peaks
from pythonosc.udp_client import SimpleUDPClient
import paho.mqtt.client as mqtt

DEBUG_MODE = True

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ENABLE_RANGE_PROFILE_PLOT = True
ENABLE_PHASE_UNWRAP_PLOT = True
ENABLE_VITALSIGNS_SPECTRUM = False
ENABLE_ESTIMATION_PLOT = True
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Device settings
num_rx_antennas = 3
frame_rate = 20  # Hz (equivalent to vital signs sampling rate when number of chirps is 1)
number_of_chirps = 1
samples_per_chirp = 64
vital_signs_sample_rate = int(1 * frame_rate)
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Define constants
file_path = ''
number_of_frames = 0
frame_counter = 0
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
processing_window_time = 20  # second
buffer_time = 5 * processing_window_time  # second
estimation_time = 5  # second
time_offset_synch_plots = 1.0  # second
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
figure_update_time = 25  # m second
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
fft_size_range_profile = samples_per_chirp * 2
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
object_distance_start_range = 0.5
object_distance_stop_range = 1.0
epsilon_value = 0.00000001
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# peak detection
peak_finding_distance = 0.01
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
buffer_data_size = int(buffer_time * vital_signs_sample_rate)
processing_data_size = int(processing_window_time * vital_signs_sample_rate)
fft_size_vital_signs = processing_data_size * 4
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
estimation_rate = vital_signs_sample_rate  # Hz
estimation_index_breathing = buffer_data_size - estimation_time * estimation_rate
estimation_index_heart = buffer_data_size - estimation_time * estimation_rate
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# filter initial coefficients
# Calculate normalized cutoff frequencies for breathing
low_breathing = 0.15
high_breathing = 0.6
# Calculate normalized cutoff frequencies for heat rate
low_heart = 0.85
high_heart = 2.4
nyquist_freq = 0.5 * vital_signs_sample_rate
filter_order = vital_signs_sample_rate + 1
breathing_b = firwin(filter_order, [low_breathing / nyquist_freq, high_breathing / nyquist_freq], pass_zero=False)
heart_b = firwin(filter_order, [low_heart / nyquist_freq, high_heart / nyquist_freq], pass_zero=False)
index_start_breathing = int(low_breathing / vital_signs_sample_rate * fft_size_vital_signs)
index_end_breathing = int(high_breathing / vital_signs_sample_rate * fft_size_vital_signs)
index_start_heart = int(low_heart / vital_signs_sample_rate * fft_size_vital_signs)
index_end_heart = int(high_heart / vital_signs_sample_rate * fft_size_vital_signs)
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
data_queue = queue.Queue()
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Initial time
start_time = time.time()
neulog_start_time = start_time

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# UDP Configuration
UDP_IP_ESP32 = "192.168.31.62" # Replace with your UDP server IP
UDP_PORT_ESP32 = 8888 # Replace with your UDP server port
UDP_IP_MAX = "127.0.0.1"
UDP_PORT_MAX = 8000
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
range_profile_peak_index = 0
max_index_processing = True
# Global variables for thread management
data_thread = None
process_thread = None
radar_processor = None

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# data queue
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def read_data(device):
    global frame_counter, radar_processor
    try:
        while radar_processor is None or not radar_processor.should_exit:
            frame_contents = device.get_next_frame()
            for frame in frame_contents:
                data_queue.put(frame)
    except Exception as e:
        print(f"[Sensor Teminated] {e}")
        try:
            send_osc_messages(status=0)
        except Exception as ee:
            print(f"[OSC ERROR] {ee}")
        print("Program terminated")
        sys.exit(1)  # Terminate the program

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# MQTT Configuration
MQTT_BROKER = "homeassistant.local"  # Replace with your MQTT broker address
MQTT_PORT = 1883  # Default MQTT port
MQTT_TOPIC = "home/nanoleaf/cmd"  # Replace with your desired topic

def configure_mqtt():
    """
    Configure and connect to the MQTT broker with authentication.
    """
    client = mqtt.Client()
    client.username_pw_set("zhengyang", "raspberry")  # Replace with your MQTT username and password
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    return client

def send_to_home_assistant(client, value):
    """
    Send the filtered breathing data to Home Assistant via MQTT.

    Parameters:
    client: MQTT client instance.
    filtered_breathing_plot: The filtered breathing data to send.
    """
    # Convert the latest filtered breathing value to a string
    client.publish(MQTT_TOPIC, int(value))

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# processing class
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
class RadarDataProcessor:
    def __init__(self):
        self.buffer_size = 100
        self.breath_stream = [] # Buffer to store the last 300 breath values
        self.presence_max_buffer = []
        self.ema_alpha = 2 / (20 + 1)  # 1秒平滑，20帧/秒
        self.presence_ema = None
        self.last_presence = 0
        self.working_time = 0.0
        self._last_exist_time = None
        self.time_last_status_change = 0.0
        # Add buffer for presence status (3 seconds)
        self.presence_status_buffer = []
        self.presence_buffer_seconds = 5
        # Add reset timer for phase unwrap
        self.last_reset_time = time.time()
        self.reset_interval = 180  # 3 minutes in seconds
        # Add exit flag for graceful shutdown
        self.should_exit = False

    def calc_range_fft(self, data_queue):
        if not data_queue.empty():
            frame = data_queue.get()
            _, num_chirps_per_frame, num_samples_per_chirp = np.shape(frame)
            range_fft_antennas_buffer = np.zeros(int(fft_size_range_profile / 2), dtype=np.complex128)
            for iAnt in range(num_rx_antennas):
                # for iChirps in range(num_chirps_per_frame):
                mat = frame[iAnt, :, :]
                avgs = np.average(mat, 1).reshape(num_chirps_per_frame, 1)
                mat = mat - avgs
                mat = np.multiply(mat,
                                  signal.windows.blackmanharris(num_samples_per_chirp).reshape(1,
                                                                                               num_samples_per_chirp))
                zp1 = np.pad(mat, ((0, 0), (0, fft_size_range_profile - num_samples_per_chirp)), 'constant')
                range_fft = np.fft.fft(zp1, fft_size_range_profile) / num_samples_per_chirp
                range_fft = 2 * range_fft[:, :int(fft_size_range_profile / 2)]
                temp_range_fft = np.sum(range_fft, axis=0)
                range_fft_antennas_buffer = temp_range_fft + range_fft_antennas_buffer
            return range_fft_antennas_buffer / num_rx_antennas
        return None, None

    def find_signal_peaks(self, fft_windowed_signal, index_start, index_end, distance):
        signal_region = fft_windowed_signal[index_start: index_end]
        peaks, _ = find_peaks(signal_region,
                              distance=int(max(1, distance * fft_size_vital_signs / vital_signs_sample_rate)))
        # Filter peaks within the boundaries
        # filtered_peaks = peaks[(peaks > 0) & (peaks < len(signal_region) - 1)]
        rate_index = 0
        filtered_peaks = peaks
        if len(filtered_peaks) > 0:
            best_peak_index = np.argmax(signal_region[filtered_peaks])
            rate_index = filtered_peaks[best_peak_index] + index_start
        return rate_index

    def vital_signs_fft(self, data, nFFT, data_length):
        windowed_signal = np.multiply(data, signal.windows.blackmanharris(data_length))
        zp2 = np.zeros(nFFT, dtype=np.complex128)
        zp2[:data_length] = windowed_signal
        fft_result = 1.0 / nFFT * np.abs(np.fft.fft(zp2)) + epsilon_value
        return fft_result

    def update_scaled_breath(self, new_value):
        self.breath_stream.append(new_value)
        if len(self.breath_stream) > self.buffer_size:
            self.breath_stream.pop(0)
        
        if len(self.breath_stream) < self.buffer_size:
            return None  # Wait until buffer fills

        return self.scale_breath()

    def scale_breath(self):
        buf = np.array(self.breath_stream)

        # Step 1: Detrend (high-pass effect)
        detrended = buf - np.convolve(buf, np.ones(25)/25, mode='same')  # moving average subtraction

        # Step 2: Normalize to 0–100 (scale current value only!)
        breath_signal = detrended[-1]
        recent = detrended[-100:]  # recent segment to track range
        min_breath = np.min(recent)
        max_breath = np.max(recent)
        if max_breath - min_breath < 1e-5:
            return 0  # avoid divide by zero, return 0

        scaled = (breath_signal - min_breath) / (max_breath - min_breath) * 100
        # If scaled is not a valid number, return 0
        if not np.isfinite(scaled) or scaled is None:
            return 0
        return np.clip(scaled, 0, 100)

    def send_data_udp(self,socket1, message):
        sock = socket1
        sock.sendto(message, (UDP_IP_ESP32, UDP_PORT_ESP32))

    def detect_presence_by_range_profile(self, range_fft_abs, max_range, threshold=0.002):
        """
        基于距离范围内的 range_fft_abs 最大值判断人体存在。
        返回 1 表示有人，0 表示无人。
        对 presence_max 做缓存和EMA平滑。
        """
        start_bin = int(object_distance_start_range / max_range * (fft_size_range_profile / 2))
        stop_bin = int(object_distance_stop_range / max_range * (fft_size_range_profile / 2))
        presence_max = np.max(range_fft_abs[start_bin:stop_bin])
        
        # 缓存最新的presence_max
        self.presence_max_buffer.append(presence_max)
        if len(self.presence_max_buffer) > 60:  # 只保留最近2秒的数据
            self.presence_max_buffer.pop(0)
        # 用缓存做EMA
        if self.presence_ema is None:
            self.presence_ema = presence_max    
        else:
            self.presence_ema = self.ema_alpha * presence_max + (1 - self.ema_alpha) * self.presence_ema
        
        existence = 1 if self.presence_ema > threshold else 0
        # print(f"presence_max: {presence_max:.6f}, presence_ema: {self.presence_ema:.6f}, buffer: {self.presence_max_buffer[-1]:.6f}")
        
        # 3-second buffer to avoid false positive
        frame_rate = 20  # Hz, adjust if needed
        buffer_len = int(self.presence_buffer_seconds * frame_rate)
        self.presence_status_buffer.append(existence)
        if len(self.presence_status_buffer) > buffer_len:
            self.presence_status_buffer.pop(0)
        # Only allow switch to 'not present' if buffer contains no 1
        if existence == 0 and 1 in self.presence_status_buffer:
            existence = 1
        
        # send OSC message if presence status changes
        if existence != self.last_presence:
            self.last_presence = existence
            send_osc_messages(status=existence)
            if existence == 1:
                now_str = time.strftime('%H:%M:%S', time.localtime())
                print(f"[{now_str}] user present")
                send_osc_messages(status=1)
            else:
                send_osc_messages(status=0)
                now_str = time.strftime('%H:%M:%S', time.localtime())
                print(f"working time: {self.working_time / 60:.2f} minutes")
                print(f"[{now_str}] user left")
        return existence

    def process_data(self):
        global slow_time_buffer_data, I_Q_envelop, range_fft_abs, wrapped_phase_plot, unwrapped_phase_plot, \
            filtered_breathing_plot, filtered_heart_plot, buffer_raw_I_Q_fft, phase_unwrap_fft, breathing_fft, \
            heart_fft, breathing_rate_estimation_index, heart_rate_estimation_index, \
            neulog_respiration_peak_index, neulog_pulse_peak_index, neulog_respiration_fft, neulog_pulse_fft, \
            start_time, radar_time_stamp, range_profile_peak_index, range_profile_peak_indices
        counter = 0
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        while not self.should_exit:
            time.sleep(0.001)
            
            # Check if it's time to reset phase data (every 3 minutes)
            current_time = time.time()
            if current_time - self.last_reset_time >= self.reset_interval:
                self.reset_phase_data()
            
            if not data_queue.empty():
                time_passed = current_time - start_time
                start_time = current_time

                radar_time_stamp = np.roll(radar_time_stamp, -1)
                radar_time_stamp[-1] = radar_time_stamp[-2] + time_passed
                # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                range_fft_antennas_buffer = self.calc_range_fft(data_queue)
                # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                if range_fft_antennas_buffer is not None:
                    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                    # slow_time_index += 1
                    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                    range_fft_abs = np.abs(range_fft_antennas_buffer)
                    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                    slow_time_buffer_data = np.roll(slow_time_buffer_data, -1)
                    I_Q_envelop = np.roll(I_Q_envelop, -1)

                    start_index_range = int(object_distance_start_range / max_range * fft_size_range_profile / 2)
                    stop_index_range = int(object_distance_stop_range / max_range * fft_size_range_profile / 2)

                    range_profile_peak_indices = np.roll(range_profile_peak_indices, -1)
                    range_profile_peak_indices[-1] = np.argmax(
                        range_fft_abs[start_index_range: stop_index_range]) + start_index_range

                    range_profile_peak_index = int(np.mean(range_profile_peak_indices[-2 * vital_signs_sample_rate:]))
                    if max_index_processing:
                        slow_time_buffer_data[-1] = range_fft_antennas_buffer[range_profile_peak_index]
                    else:
                        slow_time_buffer_data[-1] = np.mean(
                            range_fft_antennas_buffer[start_index_range:stop_index_range])

                    I_Q_envelop[-1] = np.abs(slow_time_buffer_data[-1])

                    counter += 1
                    # if counter > processing_update_interval * vital_signs_sample_rate:
                    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                    # phase unwrap
                    wrapped_phase = np.angle(slow_time_buffer_data[-counter:])
                    wrapped_phase_plot = np.roll(wrapped_phase_plot, -counter)
                    wrapped_phase_plot[-counter:] = wrapped_phase[-counter:]

                    unwrapped_phase_plot = np.roll(unwrapped_phase_plot, -counter)
                    unwrapped_phase_plot[-counter:] = wrapped_phase_plot[-counter:]

                    unwrapped_phase = np.unwrap(unwrapped_phase_plot[-processing_data_size:])
                    unwrapped_phase_plot[-processing_data_size:] = unwrapped_phase
                    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                    # filter
                    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                    filtered_breathing = lfilter(breathing_b, 1, unwrapped_phase_plot[-processing_data_size:])
                    # cycle1, trend = sm.tsa.filters.hpfilter(filtered_breathing)
                    # filtered_breathing = uniform_filter1d(cycle1, size=2 * vital_signs_sample_rate)
                    filtered_breathing_plot = np.roll(filtered_breathing_plot, -counter)
                    filtered_breathing_plot[-counter:] = filtered_breathing[-counter:]
                    recorded_time = current_time

                    cycle2, trend = sm.tsa.filters.hpfilter(unwrapped_phase_plot[-processing_data_size:],
                                                            3 * vital_signs_sample_rate)
                    filtered_heart = lfilter(heart_b, 1, cycle2)
                    filtered_heart_plot = np.roll(filtered_heart_plot, -counter)
                    filtered_heart_plot[-counter:] = filtered_heart[-counter:]
                    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                    # Vital Signs FFT
                    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                    buffer_raw_I_Q_fft = self.vital_signs_fft(slow_time_buffer_data[-processing_data_size:],
                                                              fft_size_vital_signs,
                                                              processing_data_size)
                    phase_unwrap_fft = self.vital_signs_fft(unwrapped_phase_plot[-processing_data_size:],
                                                            fft_size_vital_signs,
                                                            processing_data_size)
                    breathing_fft = self.vital_signs_fft(filtered_breathing_plot[-processing_data_size:],
                                                         fft_size_vital_signs,
                                                         processing_data_size)
                    heart_fft = self.vital_signs_fft(filtered_heart_plot[-processing_data_size:], fft_size_vital_signs,
                                                     processing_data_size)

                    # Breathing and heart rate estimation
                    breathing_rate_estimation_index = np.roll(breathing_rate_estimation_index, -1)
                    breathing_rate_estimation_index[-1] = breathing_rate_estimation_index[-2]
                    rate_index_br = self.find_signal_peaks(breathing_fft, index_start_breathing,
                                                           index_end_breathing, peak_finding_distance)
                    if rate_index_br != 0:
                        breathing_rate_estimation_index[-1] = rate_index_br
                        xb = x_axis_vital_signs_spectrum[
                            round(fft_size_vital_signs / 2 + np.mean(
                                breathing_rate_estimation_index[estimation_index_breathing:]))] * 60
                        breathing_rate_bpm = round(xb) - 2
                        # --- Send breathing rate via OSC ---
                        if breathing_rate_bpm > 0:
                            try:
                                send_osc_messages(breathpm=breathing_rate_bpm)
                                # print(f"OSC send breathing rate: {breathing_rate_bpm}")
                            except Exception as e:
                                print(f"OSC send error: {e}")
                    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                    heart_rate_estimation_index = np.roll(heart_rate_estimation_index, -1)
                    heart_rate_estimation_index[-1] = heart_rate_estimation_index[-2]
                    rate_index_hr = self.find_signal_peaks(heart_fft, index_start_heart,
                                                           index_end_heart, peak_finding_distance)
                    if rate_index_hr != 0:
                        heart_rate_estimation_index[-1] = rate_index_hr

                    # Stream filtered_breathing_plot in real-time via OSC
                    breath_amplitude = self.update_scaled_breath(filtered_breathing_plot[-1])
                    send_osc_messages(amplitude=breath_amplitude)
                    
                    # Update scaled breath amplitude buffer for plotting
                    global scaled_breath_amplitude
                    if breath_amplitude is not None:
                        scaled_breath_amplitude = np.roll(scaled_breath_amplitude, -1)
                        scaled_breath_amplitude[-1] = breath_amplitude
                    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                    counter = 0

                    # Detect presence
                    presence_status = self.detect_presence_by_range_profile(range_fft_abs, max_range)

                    # Track working time
                    if not hasattr(self, 'working_time'):
                        self.working_time = 0.0
                        self._last_exist_time = None
                    if presence_status == 1:
                        if self._last_exist_time is None:
                            self._last_exist_time = time.time()
                    else:
                        if self._last_exist_time is not None:
                            self.working_time += time.time() - self._last_exist_time
                            now_str = time.strftime('%H:%M:%S', time.localtime())
                            print(f"[{now_str}] User focused for {self.working_time / 60:.2f} minutes")
                            self.working_time = 0.0
                            self._last_exist_time = None

    def calculate_breathing_rate_variability(self, window_seconds=240):
        """
        Calculate the rolling standard deviation (variability) of the breathing rate estimation
        over the last `window_seconds` seconds (default 4 minutes).
        Returns the standard deviation of nonzero breathing rates in the window.
        """
        # Calculate how many samples correspond to the window
        window_size = int(window_seconds * vital_signs_sample_rate)
        # Use the global breathing_rate_estimation_value buffer
        window = breathing_rate_estimation_value[-window_size:]
        # Only consider nonzero values (to avoid startup zeros)
        valid = window[window > 0]
        if len(valid) == 0:
            return 0.0
        return float(np.std(valid))

    def reset_phase_data(self):
        """
        Reset phase-related data buffers to prevent accumulated errors.
        This method resets all phase unwrap related variables and other radar data buffers.
        """
        global wrapped_phase_plot, unwrapped_phase_plot, filtered_breathing_plot, filtered_heart_plot, \
               buffer_raw_I_Q_fft, phase_unwrap_fft, breathing_fft, heart_fft, \
               breathing_rate_estimation_index, heart_rate_estimation_index, \
               breathing_rate_estimation_value, heart_rate_estimation_value, \
               range_profile_peak_indices, radar_time_stamp, slow_time_buffer_data, I_Q_envelop, \
               scaled_breath_amplitude
        
        # Reset phase-related buffers
        wrapped_phase_plot.fill(0)
        unwrapped_phase_plot.fill(0)
        filtered_breathing_plot.fill(0)
        filtered_heart_plot.fill(0)
        
        # Reset FFT buffers
        buffer_raw_I_Q_fft.fill(0)
        phase_unwrap_fft.fill(0)
        breathing_fft.fill(0)
        heart_fft.fill(0)
        
        # Reset estimation buffers
        breathing_rate_estimation_index.fill(0)
        heart_rate_estimation_index.fill(0)
        breathing_rate_estimation_value.fill(0)
        heart_rate_estimation_value.fill(0)
        scaled_breath_amplitude.fill(0)
        
        # Reset range profile and time buffers
        range_profile_peak_indices.fill(0)
        radar_time_stamp.fill(0)
        slow_time_buffer_data.fill(0)
        I_Q_envelop.fill(0)
        
        # Reset internal buffers
        self.breath_stream.clear()
        self.presence_max_buffer.clear()
        self.presence_status_buffer.clear()
        self.presence_ema = None
        
        # Update reset time
        self.last_reset_time = time.time()
        
        print(f"[{time.strftime('%H:%M:%S', time.localtime())}] Phase data reset completed to prevent accumulated errors")
    
    def stop(self):
        """Stop the processing thread"""
        self.should_exit = True
        print("Radar processor stopping...")

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def send_osc_messages(status=None, breathpm=None, brvsignal=None, amplitude=None):
    """
    Send OSC messages to both ESP32 and local MaxMSP clients.
    Args:
        status (int or None): Value for /status
        breathpm (int or None): Value for /breathpm
        brvsignal (int or None): Value for /brvsignal
        amplitude (float or None): Value for /amplitude
    """
    clients = [
        SimpleUDPClient(UDP_IP_ESP32, UDP_PORT_ESP32),
        SimpleUDPClient(UDP_IP_MAX, UDP_PORT_MAX)
    ]
    for client in clients:
        if status is not None:
            try:
                client.send_message("/status", int(status))
            except Exception as e:
                pass
                # print(f"OSC send error (/status): {e}")
        if breathpm is not None:
            try:
                client.send_message("/breathpm", int(breathpm))
            except Exception as e:
                print(f"OSC send error (/breathpm): {e}")
        if brvsignal is not None:
            try:
                client.send_message("/brvsignal", int(brvsignal))
            except Exception as e:
                print(f"OSC send error (/brvsignal): {e}")
        if amplitude is not None:
            try:
                client.send_message("/amplitude", float(amplitude))
            except Exception as e:
                print(f"OSC send error (/amplitude): {e}")

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def update_plots():
    global breathing_rate_estimation_value, heart_rate_estimation_value, \
        breathing_rate_estimation_time_stamp, heart_rate_estimation_time_stamp
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # range profile plot
    if ENABLE_RANGE_PROFILE_PLOT:
        # for k in range(num_rx_antennas):
        range_profile_plots[0][0].setData(x_axis_range_profile[min_range_index:], range_fft_abs[min_range_index:])
        range_profile_plots[3][0].setData([x_axis_range_profile[range_profile_peak_index]],
                                          [range_fft_abs[range_profile_peak_index]])

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # phase unwrap plot
    if ENABLE_PHASE_UNWRAP_PLOT:
        # for k in range(num_rx_antennas):
        phase_unwrap_plots[0][0].setData(radar_time_stamp, np.real(slow_time_buffer_data))
        phase_unwrap_plots[1][0].setData(radar_time_stamp, np.imag(slow_time_buffer_data))
        phase_unwrap_plots[2][0].setData(radar_time_stamp, I_Q_envelop)
        phase_unwrap_plots[3][0].setData(radar_time_stamp, wrapped_phase_plot * 180 / np.pi)
        phase_unwrap_plots[4][0].setData(radar_time_stamp, unwrapped_phase_plot * 180 / np.pi)
        phase_unwrap_plots[5][0].setData(radar_time_stamp, filtered_breathing_plot * 180 / np.pi)
        phase_unwrap_plots[6][0].setData(radar_time_stamp, filtered_heart_plot * 180 / np.pi)
        # Update scaled breath amplitude plot
        phase_unwrap_plots[7][0].setData(radar_time_stamp, scaled_breath_amplitude)

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # breathing fft plot
    if ENABLE_VITALSIGNS_SPECTRUM:
        # for k in range(num_rx_antennas):
        vital_signs_plots[0][0].setData(x_axis_vital_signs_spectrum, np.fft.fftshift(buffer_raw_I_Q_fft))
        vital_signs_plots[1][0].setData(x_axis_vital_signs_spectrum, np.fft.fftshift(phase_unwrap_fft))
        vital_signs_plots[2][0].setData(x_axis_vital_signs_spectrum, np.fft.fftshift(breathing_fft))
        vital_signs_plots[3][0].setData(x_axis_vital_signs_spectrum, np.fft.fftshift(heart_fft))
        if breathing_rate_estimation_index[estimation_index_breathing] > 0:
            xb = x_axis_vital_signs_spectrum[
                int(fft_size_vital_signs / 2 + np.mean(breathing_rate_estimation_index[estimation_index_breathing:]))]
            yb = breathing_fft[int(np.mean(breathing_rate_estimation_index[estimation_index_breathing:]))]
            vital_signs_plots[4][0].setData([xb], [yb])
        if heart_rate_estimation_index[estimation_index_heart] > 0:
            xh = x_axis_vital_signs_spectrum[
                int(fft_size_vital_signs / 2 + np.mean(heart_rate_estimation_index[estimation_index_heart:]))]
            yh = heart_fft[int(np.mean(heart_rate_estimation_index[estimation_index_heart:]))]
            vital_signs_plots[5][0].setData([xh], [yh])
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    if ENABLE_ESTIMATION_PLOT:
        global breathing_rate_estimation_value, heart_rate_estimation_value
        if breathing_rate_estimation_index[estimation_index_breathing] > 0:
            breathing_rate_estimation_value = np.roll(breathing_rate_estimation_value, -1)
            xb = x_axis_vital_signs_spectrum[
                     round(fft_size_vital_signs / 2 + np.mean(
                         breathing_rate_estimation_index[estimation_index_breathing:]))] * 60
            breathing_rate_estimation_value[-1] = round(xb) - 2
            estimation_plots[0][0].setData(radar_time_stamp, breathing_rate_estimation_value)

        if heart_rate_estimation_index[estimation_index_heart] > 0:
            heart_rate_estimation_value = np.roll(heart_rate_estimation_value, -1)
            xh = x_axis_vital_signs_spectrum[
                     round(
                         fft_size_vital_signs / 2 + np.mean(heart_rate_estimation_index[estimation_index_heart:]))] * 60
            heart_rate_estimation_value[-1] = round(xh) - 2
            estimation_plots[1][0].setData(radar_time_stamp, heart_rate_estimation_value)
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
app = QApplication([])


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# range profile plot setting up
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def generate_range_profile_plot():
    global object_distance_start_range, object_distance_stop_range
    plot = pg.plot(title='Range Profile')
    plot.showGrid(x=True, y=True, alpha=0.3)  
    plot.setBackground("w")
    plot.setLabel('bottom', 'Range [m]')
    plot.setLabel('left', 'Amplitude')
    plot.addLegend()
    plots = [
        ('lime', 'Sum of Rx channels'),
        ('red', 'Real'),
        ('blue', 'Imaginary'),
        ('lightcoral', 'Selected Range Index')
    ]
    plot_objects = [[] for _ in range(len(plots))]
    for j, (color, name) in enumerate(plots):
        if name == 'TI - rangeBinIndexPhase':
            symbol_pen = pg.mkPen(None)  # No border for the symbol
            symbol_brush = pg.mkBrush('sandybrown')
            plot_obj = plot.plot(pen=None, symbol='s', symbolPen=symbol_pen, symbolBrush=symbol_brush, symbolSize=15, name=f'{name}')
        elif name == 'Selected Range Index':
            symbol_pen = pg.mkPen(None)
            symbol_brush = pg.mkBrush('lightcoral')
            plot_obj = plot.plot(pen=None, symbol='o', symbolPen=symbol_pen, symbolBrush=symbol_brush, symbolSize=15, name=f'{name}')
        else:
            # Use orange for breathing data, otherwise keep original color
            line_color = 'orange' if 'breath' in name.lower() or 'Sum of Rx channels' in name else color
            line_style = {'color': line_color, 'width': 2}
            plot_obj = plot.plot(pen=pg.mkPen(**line_style), name=f'{name}')
            plot_obj.setVisible(False)
        plot_objects[j].append(plot_obj)
    plot_objects[0][0].setVisible(True)
    linear_region_range_profle = pg.LinearRegionItem([object_distance_start_range, object_distance_stop_range], brush=(255, 255, 0, 20))
    plot.addItem(linear_region_range_profle)
    def region_changed():
        global object_distance_start_range, object_distance_stop_range
        region = linear_region_range_profle.getRegion()
        object_distance_start_range = region[0]
        object_distance_stop_range = region[1]
    linear_region_range_profle.sigRegionChanged.connect(region_changed)
    return plot, plot_objects


# Usage:
if ENABLE_RANGE_PROFILE_PLOT:
    range_profile_figure, range_profile_plots = generate_range_profile_plot()
    range_profile_figure.show()


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Phase unwrap plot setting up
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def generate_phase_unwrap_plot():
    plot = pg.plot(title='Slow-Time Phase Unwrap')
    plot.showGrid(x=True, y=True, alpha=0.3)
    plot.setBackground("w")
    plot.setLabel('bottom', 'Time [s]')
    plot.setLabel('left', 'Unwrapped Phase [deg.]')
    plot.addLegend()
    plots = [
        ('orange', 'Slow-Time Signal [I]'),
        ('beige', 'Slow-Time Signal [Q]'),
        ('hotpink', 'Envelop'),
        ('y', 'Wrapped Angle'),
        ('m', 'Phase Unwrap'),
        ('orange', 'Breathing'),  # Breathing data in orange
        ('c', 'Heart'),
        ('black', 'Scaled Breath Amplitude')  # Scaled breath amplitude in black
    ]
    plot_objects = [[] for _ in range(len(plots))]
    for j, (color, name) in enumerate(plots):
        if 'Scaled Breath Amplitude' in name:
            # Black solid line for scaled breath amplitude
            line_style = {'color': 'black', 'width': 2}
            plot_obj = plot.plot(pen=pg.mkPen(**line_style), name=f'{name}')
            plot_obj.setVisible(True)  # Set visible on start
        else:
            # Use orange for breathing
            line_color = 'orange' if 'breath' in name.lower() else color
            line_style = {'color': line_color, 'width': 2}
            plot_obj = plot.plot(pen=pg.mkPen(**line_style), name=f'{name}')
            plot_obj.setVisible(False)
        plot_objects[j].append(plot_obj)
    plot_objects[5][0].setVisible(True)  # Keep breathing visible
    # plot_objects[6][0].setVisible(True)
    return plot, plot_objects


# Usage:
if ENABLE_PHASE_UNWRAP_PLOT:
    slow_time_phase_unwrap_figure, phase_unwrap_plots = generate_phase_unwrap_plot()
    slow_time_phase_unwrap_figure.show()

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Breathing Spectrum plot setting up
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def generate_vitalsigns_spectrum_plot():
    global low_breathing, high_breathing, low_heart, high_heart, breathing_b, heart_b, index_start_breathing, index_end_breathing, index_start_heart, index_end_heart
    plot = pg.plot(title='Vital Signs Spectrum')
    plot.showGrid(x=True, y=True, alpha=0.3)
    plot.setBackground("w")
    plot.setLabel('bottom', 'Frequency [Hz]')
    plot.setLabel('left', 'Amplitude')
    plot.addLegend()
    plots = [
        ('orange', 'I&Q Raw Data'),
        ('m', 'Phase Unwrap'),
        ('orange', 'Breathing'),  # Breathing data in orange
        ('c', 'Heart'),
        ('orange', 'Breathing Peak'),  # Breathing peak in orange
        ('c', 'Heart Peak')
    ]
    plot_objects = [[] for _ in range(len(plots))]
    for j, (color, name) in enumerate(plots):
        if name == 'Breathing Peak':
            symbol_pen = pg.mkPen(None)
            symbol_brush = pg.mkBrush('orange')
            plot_obj = plot.plot(pen=None, symbol='s', symbolPen=symbol_pen, symbolBrush=symbol_brush, symbolSize=15, name=f'{name}')
        elif name == 'Heart Peak':
            symbol_pen = pg.mkPen(None)
            symbol_brush = pg.mkBrush('c')
            plot_obj = plot.plot(pen=None, symbol='d', symbolPen=symbol_pen, symbolBrush=symbol_brush, symbolSize=15, name=f'{name}')
        else:
            # Use orange for breathing
            line_color = 'orange' if 'breath' in name.lower() else color
            line_style = {'color': line_color, 'width': 2}
            plot_obj = plot.plot(pen=pg.mkPen(**line_style), name=f'{name}')
        plot_obj.setVisible(False)
        plot_objects[j].append(plot_obj)
    plot_objects[2][0].setVisible(True)
    plot_objects[3][0].setVisible(True)
    linear_region_breathing = pg.LinearRegionItem([low_breathing, high_breathing], brush=(255, 255, 0, 20))
    plot.addItem(linear_region_breathing, 'Breathing Linear Region')
    def linear_region_breathing_changed():
        global low_breathing, high_breathing, breathing_b, index_start_breathing, index_end_breathing
        region = linear_region_breathing.getRegion()
        if (region[0] < vital_signs_sample_rate / 4 and region[1] < vital_signs_sample_rate / 2 and region[0] > 0 and region[1] > 0):
            low_breathing = region[0]
            high_breathing = region[1]
            breathing_b = firwin(filter_order, [low_breathing / nyquist_freq, high_breathing / nyquist_freq], pass_zero=False)
            index_start_breathing = int(low_breathing / vital_signs_sample_rate * fft_size_vital_signs)
            index_end_breathing = int(high_breathing / vital_signs_sample_rate * fft_size_vital_signs)
    linear_region_breathing.sigRegionChanged.connect(linear_region_breathing_changed)
    linear_region_heart = pg.LinearRegionItem([low_heart, high_heart], brush=(255, 255, 0, 20))
    plot.addItem(linear_region_heart)
    def linear_region_heart_changed():
        global low_heart, high_heart, heart_b, index_start_heart, index_end_heart
        region = linear_region_heart.getRegion()
        if (region[0] < vital_signs_sample_rate / 4 and region[1] < vital_signs_sample_rate / 2 and region[0] > 0 and region[1] > 0):
            low_heart = region[0]
            high_heart = region[1]
            heart_b = firwin(filter_order, [low_heart / nyquist_freq, high_heart / nyquist_freq], pass_zero=False)
            index_start_heart = int(low_heart / vital_signs_sample_rate * fft_size_vital_signs)
            index_end_heart = int(high_heart / vital_signs_sample_rate * fft_size_vital_signs)
    linear_region_heart.sigRegionChanged.connect(linear_region_heart_changed)
    plot.setXRange(low_breathing, high_heart + 0.5)
    return plot, plot_objects


# Usage:
if ENABLE_VITALSIGNS_SPECTRUM:
    vital_signs_spectrum_figure, vital_signs_plots = generate_vitalsigns_spectrum_plot()
    vital_signs_spectrum_figure.show()


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Estimation plot setting up
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def generate_estimation_plot():
    plot = pg.plot(title='Vital Signs Estimation')
    plot.showGrid(x=True, y=True, alpha=0.3)
    plot.setBackground("w")
    plot.setLabel('bottom', 'Time [s]')
    plot.setLabel('left', 'Rate [b.p.m.]')
    plot.addLegend()
    plots = [
        ('orange', 'Breathing'),  # Breathing data in orange
        ('c', 'Heart')
    ]
    plot_objects = [[] for _ in range(len(plots))]
    for j, (color, name) in enumerate(plots):
        # Use orange for breathing
        line_color = 'orange' if 'breath' in name.lower() else color
        line_style = {'color': line_color, 'width': 2}
        plot_obj = plot.plot(pen=pg.mkPen(**line_style), name=f'{name}')
        plot_obj.setVisible(True)
        plot_objects[j].append(plot_obj)
    plot_objects[1][0].setVisible(False)
    return plot, plot_objects


# Usage:
if ENABLE_ESTIMATION_PLOT:
    estimation_figure, estimation_plots = generate_estimation_plot()
    estimation_figure.show()
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
timer = QTimer()
timer.timeout.connect(update_plots)
timer.start(figure_update_time)  # Update the plots every 100 milliseconds
def cleanup_on_exit():
    """Cleanup function to stop all threads when application exits"""
    global data_thread, process_thread, radar_processor
    send_osc_messages(status=0)
    print("OSC send status=0")
    print("Cleaning up threads...")
    if radar_processor:
        radar_processor.stop()
    if process_thread and process_thread.is_alive():
        process_thread.join(timeout=2)
    if data_thread and data_thread.is_alive():
        data_thread.join(timeout=2)
    print("Cleanup completed")

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# main
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
if __name__ == "__main__":

    # connect to the device
    with DeviceFmcw() as device:
        print("Radar SDK Version: " + get_version())
        print("UUID of board: " + device.get_board_uuid())
        print("Sensor: " + str(device.get_sensor_type()))

        if num_rx_antennas == 3:
            rx_mask = 7  # rx_mask = 7 means all three receive antennas are activated
        elif num_rx_antennas == 2:
            rx_mask = 3  # rx_mask = 7 means all three receive antennas are activated
        else:
            rx_mask = 1  # rx_mask = 7 means all three receive antennas are activated

        config = FmcwSimpleSequenceConfig(
            frame_repetition_time_s=1 / frame_rate,
            chirp_repetition_time_s=0.001,
            num_chirps=number_of_chirps,
            tdm_mimo=True,
            chirp=FmcwSequenceChirp(
                start_frequency_Hz=58_000_000_000,
                end_frequency_Hz=63_500_000_000,
                sample_rate_Hz=1e6,
                num_samples=samples_per_chirp,
                rx_mask=rx_mask,
                tx_mask=1,
                tx_power_level=31,
                lp_cutoff_Hz=500000,
                hp_cutoff_Hz=80000,
                if_gain_dB=33,
            )
        )
        # num_rx_antennas = device.get_sensor_information()["num_rx_antennas"]
        sequence = device.create_simple_sequence(config)
        device.set_acquisition_sequence(sequence)

        pp = pprint.PrettyPrinter()
        pp.pprint(create_dict_from_sequence(sequence))
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # initialization
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        range_res = 3e8 / (2 * device.get_chirp_sampling_bandwidth(config.chirp))
        print("range resolution = ", range_res * 2)
        max_range = range_res * samples_per_chirp / 2
        print("maximum range = ", max_range)
        min_range = 0.15
        min_range_index = int(min_range * fft_size_range_profile / 2)
        print('vital_signs_sample_rate = ', vital_signs_sample_rate, 'Hz')
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

        range_fft_abs = np.zeros(int(fft_size_range_profile / 2))
        radar_time_stamp = np.zeros(buffer_data_size)
        slow_time_buffer_data = np.zeros(buffer_data_size, dtype=np.complex128)
        I_Q_envelop = np.zeros(buffer_data_size)
        wrapped_phase_plot = np.zeros(buffer_data_size)
        unwrapped_phase_plot = np.zeros(buffer_data_size)
        filtered_breathing_plot = np.zeros(buffer_data_size)
        filtered_heart_plot = np.zeros(buffer_data_size)
        buffer_raw_I_Q_fft = np.zeros(fft_size_vital_signs)
        phase_unwrap_fft = np.zeros(fft_size_vital_signs)
        breathing_fft = np.zeros(fft_size_vital_signs)
        heart_fft = np.zeros(fft_size_vital_signs)
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        range_profile_peak_indices = np.zeros(buffer_data_size)
        breathing_rate_estimation_index = np.zeros(buffer_data_size)
        heart_rate_estimation_index = np.zeros(buffer_data_size)
        breathing_rate_estimation_value = np.zeros(buffer_data_size)
        heart_rate_estimation_value = np.zeros(buffer_data_size)
        # Add buffer for scaled breath amplitude
        scaled_breath_amplitude = np.zeros(buffer_data_size)
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        x_axis_range_profile = np.linspace(0, max_range, int(fft_size_range_profile / 2))
        x_axis_vital_signs_spectrum = np.linspace(-vital_signs_sample_rate / 2, vital_signs_sample_rate / 2,
                                                  fft_size_vital_signs)
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # Threads for reading data and processing
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        data_thread = threading.Thread(target=read_data, args=(device,))
        data_thread.start()
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # start_index = int(object_distance_start_range/max_range * samples_per_chirp)
        # end_index = int(object_distance_stop_range/max_range * samples_per_chirp)
        radar_processor = RadarDataProcessor()
        process_thread = threading.Thread(target=radar_processor.process_data, args=())
        process_thread.start()

        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # plots
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        
        # Connect cleanup function to application about to quit
        app.aboutToQuit.connect(cleanup_on_exit)
        
        sys.exit(app.exec_())

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
