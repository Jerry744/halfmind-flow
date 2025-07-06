from pythonosc.udp_client import SimpleUDPClient

# OSC target
ip = "192.168.31.180"
ip_max = "127.0.0.1"
port = 8888
port_max = 8000

# Create OSC client
client = SimpleUDPClient(ip, port)
client_max = SimpleUDPClient(ip_max, port_max)

# # Send message once
# client.send_message("/status", 4)
# client.send_message("/breathingrate", 3)
# print("OSC message sent: /status 0 to 192.168.31.180:8888")

# client_max.send_message("/breathpm", 17)
client.send_message("/status", 1)
# print("OSC message sent: /breathpm 17 to 127.0.0.1:8000")