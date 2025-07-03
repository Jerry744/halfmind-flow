#include <Adafruit_NeoPixel.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <OSCMessage.h>

#define LED_PIN     5      // D5
#define NUM_LEDS    7
#define TOUCH_PIN   T0     // D4 (GPIO4, touch-capable)
#define BREATH_CYCLE_LENGTH 4.0  // Half breathing cycle in seconds

// WiFi settings
const char* ssid = "TP-Link_CF74";
const char* password = "81541027";

// OSC settings
WiFiUDP Udp;
const unsigned int localPort = 8888;  // Local port to listen on
const char* oscStatusAddress = "/status";        // OSC address for state control
const char* oscBreathingAddress = "/breathingrate"; // OSC address for breathing rate
const char* oscConfigAddress = "/config";            // OSC address for configuration

// Designated IP address for OSC messages (change this to your sender's IP)
IPAddress designatedIP(192, 168, 31, 128);  // Change to your designated IP address
bool enableIPFiltering = false;  // Set to false to accept from any IP

// Dynamic breathing rate control
float currentBreathingRate = BREATH_CYCLE_LENGTH;  // Current breathing rate in seconds

// Global variables for breathing effect
float breathingBrightness = 0;
bool breathingIncreasing = true; // true = brightening, false = dimming
uint32_t breathingColor = 0;     // Set this to strip.Color(r, g, b) before use

Adafruit_NeoPixel strip(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);

// 状态定义
enum {
  SETUP_TEST = 0,
  STATUS_0,   // nobody
  STATUS_1,   // user appear
  STATUS_2,   // user working
  STATUS_3,   // out of focus
  STATUS_4,   // time up
  STATUS_5    // user leave
};
int state = SETUP_TEST;
unsigned long stateStartTime = 0;
bool waitingForTimeout = false;
unsigned long lastTouchTime = 0;

// Helper function to connect to WiFi with timeout (returns true if connected, false if timeout)
bool connectToWiFiWithTimeout(const char* ssid, const char* password, unsigned long timeoutMs) {
  // Turn all LEDs yellow while connecting
  for (int i = 0; i < NUM_LEDS; i++) {
    strip.setPixelColor(i, strip.Color(30, 30, 0)); // Yellow
  }
  strip.show();

  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  unsigned long startAttemptTime = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startAttemptTime < timeoutMs) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  bool connected = WiFi.status() == WL_CONNECTED;
  if (connected) {
    // Show green for 2 seconds
    for (int i = 0; i < NUM_LEDS; i++) {
      strip.setPixelColor(i, strip.Color(0, 30, 0)); // Green
    }
    strip.show();
    delay(2000);
  } else {
    // Show red for 2 seconds
    for (int i = 0; i < NUM_LEDS; i++) {
      strip.setPixelColor(i, strip.Color(30, 0, 0)); // Red
    }
    strip.show();
    delay(2000);
  }
  // Clear LEDs after feedback
  strip.clear();
  strip.show();
  return connected;
}

void setup() {
  Serial.begin(115200);
  Serial.println("Starting LED State Controller with OSC...");
  
  // Initialize LED strip
  strip.begin();
  strip.show();

  // Connect to WiFi with 30s timeout
  bool wifiConnected = connectToWiFiWithTimeout(ssid, password, 30000);
  if (wifiConnected) {
    Serial.print("Connected! IP address: ");
    Serial.println(WiFi.localIP());
    // Start UDP
    Udp.begin(localPort);
    Serial.print("OSC listening on port: ");
    Serial.println(localPort);
    Serial.println("OSC addresses: /status, /breathingrate, /config");
    // Display OSC security settings
    if (enableIPFiltering) {
      Serial.print("OSC IP filtering ENABLED - Only accepting messages from: ");
      Serial.println(designatedIP);
    } else {
      Serial.println("OSC IP filtering DISABLED - Accepting messages from any IP");
    }
  } else {
    Serial.println("WiFi connection failed after 30 seconds. Skipping network setup.");
  }
  
  state = STATUS_0;
  Serial.println("Setup complete. Entering STATUS_0 (nobody)");
}

void loop() {
  handleTouch();
  handleOSC();  // Handle incoming OSC messages

  unsigned long now = millis();
  switch (state) {
    case STATUS_0: // nobody, breathing orange
      orangeBreath();
      break;
    case STATUS_1: // user appear, red for 5s, then STATUS_2
      redSolid();
      delay(5000);
      break;
    case STATUS_2: // user working, orange 20%
      orangeLow();
      break;
    case STATUS_3: // out of focus, blink once, then STATUS_2
      blinkOnce();
      break;
    case STATUS_4: // time up, rainbow, then STATUS_5
      rainbowCycle(5);
      state = STATUS_5;
      break;
    case STATUS_5: // user leave, blink red 5s, then STATUS_0
      redBlink5s();
      break;
  }
}

// Handle incoming OSC messages
void handleOSC() {
  OSCMessage msg;
  int size = Udp.parsePacket();
  
  if (size > 0) {
    // Get the sender's IP address
    IPAddress senderIP = Udp.remoteIP();
    
    // Check if IP filtering is enabled and if the sender is authorized
    if (enableIPFiltering && senderIP != designatedIP) {
      Serial.print("OSC message rejected from unauthorized IP: ");
      Serial.println(senderIP);
      
      // Clear the packet buffer
      while (size--) {
        Udp.read();
      }
      return;
    }
    
    // Process the message if IP is authorized or filtering is disabled
    while (size--) {
      msg.fill(Udp.read());
    }
    
    if (!msg.hasError()) {
      Serial.print("OSC message accepted from: ");
      Serial.println(senderIP);
      
      msg.route(oscStatusAddress, routeStatus);
      msg.route(oscBreathingAddress, routeBreathingRate);
      msg.route(oscConfigAddress, routeConfig);
    } else {
      Serial.println("OSC message has errors");
    }
  }
}

// Route function for status OSC messages
void routeStatus(OSCMessage &msg, int addrOffset) {
  if (msg.isInt(0)) {
    int newState = msg.getInt(0);
    // Accept only 0-5 and map to STATUS_0..STATUS_5
    if (newState >= 0 && newState <= 5) {
      int oldState = state;
      state = STATUS_0 + newState;
      waitingForTimeout = false;
      Serial.print("OSC /status received! State changed from ");
      Serial.print(getStateName(oldState));
      Serial.print(" to ");
      Serial.println(getStateName(state));
    } else {
      Serial.print("Invalid state received via OSC /status: ");
      Serial.println(newState);
    }
  } else {
    Serial.println("OSC /status message received but not an integer");
  }
}

// Route function for breathing rate OSC messages
void routeBreathingRate(OSCMessage &msg, int addrOffset) {
  if (msg.isFloat(0)) {
    float newRate = msg.getFloat(0);
    
    // Validate breathing rate (0.1 to 20 seconds)
    if (newRate >= 0.1 && newRate <= 20.0) {
      float oldRate = currentBreathingRate;
      currentBreathingRate = newRate;
      
      Serial.print("OSC /breathingrate received! Breathing rate changed from ");
      Serial.print(oldRate);
      Serial.print("s to ");
      Serial.print(currentBreathingRate);
      Serial.println("s");
    } else {
      Serial.print("Invalid breathing rate received via OSC /breathingrate: ");
      Serial.println(newRate);
      Serial.println("Valid range: 0.1 to 20.0 seconds");
    }
  } else if (msg.isInt(0)) {
    // Also accept integer values
    int newRate = msg.getInt(0);
    
    if (newRate >= 1 && newRate <= 20) {
      float oldRate = currentBreathingRate;
      currentBreathingRate = (float)newRate;
      
      Serial.print("OSC /breathingrate received! Breathing rate changed from ");
      Serial.print(oldRate);
      Serial.print("s to ");
      Serial.print(currentBreathingRate);
      Serial.println("s");
    } else {
      Serial.print("Invalid breathing rate received via OSC /breathingrate: ");
      Serial.println(newRate);
      Serial.println("Valid range: 1 to 20 seconds");
    }
  } else {
    Serial.println("OSC /breathingrate message received but not a number");
  }
}

// Route function for configuration OSC messages
void routeConfig(OSCMessage &msg, int addrOffset) {
  // /config/ipfilter 0|1 - Enable/disable IP filtering
  // /config/setip a.b.c.d - Set designated IP address
  
  if (msg.match("/ipfilter", addrOffset)) {
    if (msg.isInt(0)) {
      bool newFiltering = msg.getInt(0) != 0;
      bool oldFiltering = enableIPFiltering;
      enableIPFiltering = newFiltering;
      
      Serial.print("OSC /config/ipfilter received! IP filtering changed from ");
      Serial.print(oldFiltering ? "ENABLED" : "DISABLED");
      Serial.print(" to ");
      Serial.println(enableIPFiltering ? "ENABLED" : "DISABLED");
    }
  } 
  else if (msg.match("/setip", addrOffset)) {
    if (msg.isString(0)) {
      char ipStr[16];
      msg.getString(0, ipStr, 16);
      
      // Parse IP address string (format: "192.168.1.100")
      IPAddress newIP;
      if (newIP.fromString(ipStr)) {
        IPAddress oldIP = designatedIP;
        designatedIP = newIP;
        
        Serial.print("OSC /config/setip received! Designated IP changed from ");
        Serial.print(oldIP);
        Serial.print(" to ");
        Serial.println(designatedIP);
      } else {
        Serial.print("Invalid IP address format received: ");
        Serial.println(ipStr);
      }
    }
  }
  else {
    Serial.println("Unknown config command received");
  }
}

// Helper function to get state name for debugging
String getStateName(int stateNum) {
  switch (stateNum) {
    case SETUP_TEST: return "SETUP_TEST";
    case STATUS_0: return "STATUS_0 (nobody)";
    case STATUS_1: return "STATUS_1 (user appear)";
    case STATUS_2: return "STATUS_2 (user working)";
    case STATUS_3: return "STATUS_3 (out of focus)";
    case STATUS_4: return "STATUS_4 (time up)";
    case STATUS_5: return "STATUS_5 (user leave)";
    default: return "UNKNOWN";
  }
}

// Touch: only one change per touch, regardless of touch time
void handleTouch() {
  static bool lastTouch = false;
  bool touch = touchRead(TOUCH_PIN) < 40; // Adjust threshold as needed
  unsigned long now = millis();
  if (touch && !lastTouch && now - lastTouchTime > 300) { // Debounce
    state = (state + 1) % 6 + 1; // Cycle STATUS_0~STATUS_5
    if (state > STATUS_5) state = STATUS_0;
    waitingForTimeout = false;
    lastTouchTime = now;
  }
  lastTouch = touch;
}

// Lighting functions

void orangeBreath() {
  // Set min and max brightness (0-255)
  const uint8_t minBrightness = 30;
  const uint8_t maxBrightness = 200;
  static float brightness = minBrightness;
  static bool increasing = true;
  // fadeAmount is based on breathing rate: higher rate = faster breathing
  float fadeAmount = (maxBrightness - minBrightness) / (currentBreathingRate * 50.0);

  // Calculate brightness step direction
  if (increasing) {
    brightness += fadeAmount;
    if (brightness >= maxBrightness) {
      brightness = maxBrightness;
      increasing = false;
    }
  } else {
    brightness -= fadeAmount;
    if (brightness <= minBrightness) {
      brightness = minBrightness;
      increasing = true;
    }
  }

  // Use constant color RGB(255,162,57), scale by brightness/255
  uint8_t r = (uint8_t)(255 * (brightness / 255.0));
  uint8_t g = (uint8_t)(162 * (brightness / 255.0));
  uint8_t b = (uint8_t)(57 * (brightness / 255.0));
  for (int i = 0; i < NUM_LEDS; i++) {
    strip.setPixelColor(i, strip.Color(r, g, b));
  }
  strip.show();
  delay(20);
}

void redSolid() {
  for (int i = 0; i < NUM_LEDS; i++) {
    strip.setPixelColor(i, strip.Color(255, 0, 0));
  }
  strip.show();
}

void orangeLow() {
  // 20% brightness of orange (255,162,57)
  float scale = 51.0 / 255.0; // 51 is 20% of 255
  uint8_t r = (uint8_t)(255 * scale);
  uint8_t g = (uint8_t)(162 * scale);
  uint8_t b = (uint8_t)(57 * scale);
  for (int i = 0; i < NUM_LEDS; i++) {
    strip.setPixelColor(i, strip.Color(r, g, b));
  }
  strip.show();
}

void blinkOnce() {
  static bool hasBlinked = false;
  static unsigned long blinkStart = 0;
  if (!hasBlinked) {
    for (int i = 0; i < NUM_LEDS; i++) {
      strip.setPixelColor(i, strip.Color(255, 255, 255));
    }
    strip.show();
    blinkStart = millis();
    hasBlinked = true;
  } else if (millis() - blinkStart >= 500) {
    strip.clear();
    strip.show();
    state = STATUS_2;
    hasBlinked = false;
  }
}

void rainbowCycle(uint8_t seconds) {
  uint32_t start = millis();
  while (millis() - start < seconds * 1000) {
    for (int j = 0; j < 256; j++) {
      for (int i = 0; i < NUM_LEDS; i++) {
        strip.setPixelColor(i, Wheel((i * 256 / NUM_LEDS + j) & 255));
      }
      strip.show();
      delay(20);
    }
  }
}

void redBlink5s() {
  static bool on = false;
  static unsigned long lastBlink = 0;
  static unsigned long startBlink = 0;
  if (!waitingForTimeout) {
    startBlink = millis();
    waitingForTimeout = true;
    on = false;
    lastBlink = 0;
  }
  if (millis() - lastBlink > 1000) {
    on = !on;
    for (int i = 0; i < NUM_LEDS; i++) {
      strip.setPixelColor(i, on ? strip.Color(255, 0, 0) : 0);
    }
    strip.show();
    lastBlink = millis();
  }
  if (millis() - startBlink >= 5000) {
    state = STATUS_0;
    waitingForTimeout = false;
  }
}

uint32_t Wheel(byte pos) {
  pos = 255 - pos;
  if (pos < 85) return strip.Color(255 - pos * 3, 0, pos * 3);
  else if (pos < 170) {
    pos -= 85;
    return strip.Color(0, pos * 3, 255 - pos * 3);
  } else {
    pos -= 170;
    return strip.Color(pos * 3, 255 - pos * 3, 0);
  }
}

void customBreathEffect(float minBrightness, float maxBrightness, float step) {
  // Update brightness
  if (breathingIncreasing) {
    breathingBrightness += step;
    if (breathingBrightness >= maxBrightness) {
      breathingBrightness = maxBrightness;
      breathingIncreasing = false;
    }
  } else {
    breathingBrightness -= step;
    if (breathingBrightness <= minBrightness) {
      breathingBrightness = minBrightness;
      breathingIncreasing = true;
    }
  }

  // Set all LEDs to the current color and brightness
  uint8_t r = (uint8_t)(((breathingColor >> 16) & 0xFF) * (breathingBrightness / 255.0));
  uint8_t g = (uint8_t)(((breathingColor >> 8) & 0xFF) * (breathingBrightness / 255.0));
  uint8_t b = (uint8_t)((breathingColor & 0xFF) * (breathingBrightness / 255.0));
  for (int i = 0; i < NUM_LEDS; i++) {
    strip.setPixelColor(i, strip.Color(r, g, b));
  }
  strip.show();
  delay(10); // Adjust for smoother/faster effect
}

// Helper to set all LEDs to a color with brightness scaling (0-255)
void setAllLedsColorWithBrightness(uint8_t r, uint8_t g, uint8_t b, uint8_t brightness) {
  float scale = brightness / 255.0;
  uint8_t r_scaled = (uint8_t)(r * scale);
  uint8_t g_scaled = (uint8_t)(g * scale);
  uint8_t b_scaled = (uint8_t)(b * scale);
  for (int i = 0; i < NUM_LEDS; i++) {
    strip.setPixelColor(i, strip.Color(r_scaled, g_scaled, b_scaled));
  }
  strip.show();
}
