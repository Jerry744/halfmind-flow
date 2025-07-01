#include <WiFi.h>
#include <WiFiUdp.h>
#include <Adafruit_NeoPixel.h>
#include <OSCMessage.h>

#define LED_PIN     5
#define NUM_LEDS    7
#define TOUCH_PIN   T0  // GPIO4 - Single touch pin for mode switching

Adafruit_NeoPixel strip(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);

// WiFi & OSC
const char* ssid = "YOUR_SSID";
const char* password = "YOUR_PASSWORD";
WiFiUDP Udp;
const int localPort = 8000;

// State control
int state = -1;  // Start with setup test (-1)
unsigned long stateStartTime = 0;
bool waitingForTimeout = false;
unsigned long lastTouchTrigger = 0;
bool setupComplete = false;

void setup() {
  Serial.begin(115200);
  strip.begin();
  strip.show();
  
  // Setup test: turn on green light for 2 seconds
  for (int i = 0; i < NUM_LEDS; i++) {
    strip.setPixelColor(i, strip.Color(0, 255, 0)); // Green
  }
  strip.show();
  delay(2000);
  
  // Turn off all lights
  strip.clear();
  strip.show();
  
  setupComplete = true;
  state = 0; // Start with status 0 (nobody - breathing orange)
  
  touchAttachInterrupt(TOUCH_PIN, onTouch, 40);

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected");
  Udp.begin(localPort);
}

void loop() {
  if (!setupComplete) return;
  
  checkOSC();

  unsigned long now = millis();
  
  switch (state) {
    case 0: // Status 0: nobody - breathing orange light
      orangeBreath();
      break;
      
    case 1: // Status 1: user appear - red light for 5 seconds
      redSolid();
      if (!waitingForTimeout) {
        stateStartTime = now;
        waitingForTimeout = true;
      } else if (now - stateStartTime >= 5000) {
        state = 2; // Move to status 2 (user working)
        waitingForTimeout = false;
      }
      break;
      
    case 2: // Status 2: user working - orange light 20% brightness
      orangeLowBrightness();
      break;
      
    case 3: // Status 3: out of focus - blink once
      blinkOnce();
      break;
      
    case 4: // Status 4: time up - rainbow strip
      rainbowCycle(5);
      state = 0; // Return to status 0
      break;
      
    case 5: // Status 5: user leave - blinking red for 5 seconds
      redBlink();
      if (!waitingForTimeout) {
        stateStartTime = now;
        waitingForTimeout = true;
      } else if (now - stateStartTime >= 5000) {
        state = 0; // Return to status 0
        waitingForTimeout = false;
      }
      break;
  }
}

// OSC receive handling
void checkOSC() {
  int size = Udp.parsePacket();
  if (size > 0) {
    OSCMessage msg;
    while (size--) {
      msg.fill(Udp.read());
    }
    if (!msg.hasError()) {
      msg.route("/state", handleState);
    }
  }
}

void handleState(OSCMessage &msg, int addrOffset) {
  if (msg.isInt(0)) {
    int newState = msg.getInt(0);
    if (newState >= 0 && newState <= 5) {
      state = newState;
      waitingForTimeout = false;
      Serial.print("OSC State changed to ");
      Serial.println(state);
    }
  }
}

// Lighting functions
void orangeBreath() {
  static int brightness = 0;
  static int fadeAmount = 5;
  for (int i = 0; i < NUM_LEDS; i++) {
    strip.setPixelColor(i, strip.Color(255 * brightness / 255, 80 * brightness / 255, 0));
  }
  strip.show();
  brightness += fadeAmount;
  if (brightness <= 0 || brightness >= 255) fadeAmount = -fadeAmount;
  delay(20);
}

void redSolid() {
  for (int i = 0; i < NUM_LEDS; i++) {
    strip.setPixelColor(i, strip.Color(255, 0, 0));
  }
  strip.show();
}

void orangeLowBrightness() {
  // 20% brightness orange
  for (int i = 0; i < NUM_LEDS; i++) {
    strip.setPixelColor(i, strip.Color(255 * 0.2, 80 * 0.2, 0));
  }
  strip.show();
}

void blinkOnce() {
  static bool hasBlinked = false;
  static unsigned long blinkStartTime = 0;
  
  if (!hasBlinked) {
    // Turn on all LEDs
    for (int i = 0; i < NUM_LEDS; i++) {
      strip.setPixelColor(i, strip.Color(255, 255, 255)); // White blink
    }
    strip.show();
    blinkStartTime = millis();
    hasBlinked = true;
  } else if (millis() - blinkStartTime >= 500) { // Blink for 500ms
    // Turn off all LEDs
    strip.clear();
    strip.show();
    state = 2; // Return to status 2 (user working)
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

void redBlink() {
  static bool on = false;
  static unsigned long lastBlink = 0;
  if (millis() - lastBlink > 1000) { // 1 second interval
    on = !on;
    for (int i = 0; i < NUM_LEDS; i++) {
      strip.setPixelColor(i, on ? strip.Color(255, 0, 0) : 0);
    }
    strip.show();
    lastBlink = millis();
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

// Touch function - each touch changes status once
void onTouch() {
  if (millis() - lastTouchTrigger > 300) { // Debounce
    state = (state + 1) % 6; // Cycle through states 0-5
    waitingForTimeout = false;
    Serial.println("Touch -> State: " + String(state));
    lastTouchTrigger = millis();
  }
}
