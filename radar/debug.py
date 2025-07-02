from pythonosc.udp_client import SimpleUDPClient

# OSC target
ip = "192.168.31.180"
port = 8888

# Create OSC client
client = SimpleUDPClient(ip, port)

# Send message once
client.send_message("/status", 0)
# client.send_message("/breathingrate", 3)
print("OSC message sent: /status 0 to 192.168.31.180:8888")
