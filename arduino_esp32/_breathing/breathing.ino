#include <Adafruit_NeoPixel.h>

#define LED_PIN     5      // D5 for LED strip
#define NUM_LEDS    7
#define TOUCH_PIN   T0     // D4 (GPIO4) for touch

Adafruit_NeoPixel strip(NUM_LEDS, LED_PIN, NEO_GRB + NEO_KHZ800);

bool ledOn = false;
bool lastTouch = false;
unsigned long lastTouchTime = 0;

void setup() {
  strip.begin();
    for (int i = 0; i < NUM_LEDS; i++) {
    strip.setPixelColor(i, strip.Color(0, 255, 0)); // Green
  }
  strip.show();
  delay(2000);
}

void loop() {
  handleTouch();
  
  if (ledOn) {
    orangeBreath();
  } else {
    strip.clear();
    strip.show();
  }
}

void handleTouch() {
  bool touch = touchRead(TOUCH_PIN) < 40;
  unsigned long now = millis();
  
  if (touch && !lastTouch && now - lastTouchTime > 300) {
    ledOn = !ledOn;  // Toggle on/off
    lastTouchTime = now;
  }
  lastTouch = touch;
}

void orangeBreath() {
  static int brightness = 0;
  static int fadeAmount = 5;
  
  for (int i = 0; i < NUM_LEDS; i++) {
    strip.setPixelColor(i, strip.Color(
      (int)(255 * brightness / 255.0), 
      (int)(80 * brightness / 255.0), 
      0
    ));
  }
  strip.show();
  
  brightness += fadeAmount;
  if (brightness <= 0 || brightness >= 255) {
    fadeAmount = -fadeAmount;
  }
  delay(20);
}
