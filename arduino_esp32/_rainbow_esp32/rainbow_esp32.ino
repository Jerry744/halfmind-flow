#include <FastLED.h>

#define LED_PIN     5        // 数据线连接的 GPIO 引脚
#define NUM_LEDS    7        // 灯珠数量
#define BRIGHTNESS  50      // 亮度 0-255
#define LED_TYPE    WS2812B  // LED 类型
#define COLOR_ORDER GRB      // 一般为 GRB

CRGB leds[NUM_LEDS];

void setup() {
  FastLED.addLeds<LED_TYPE, LED_PIN, COLOR_ORDER>(leds, NUM_LEDS);
  FastLED.setBrightness(BRIGHTNESS);
}

void loop() {
  rainbowCycle(10);  // 每帧等待10毫秒
}

// 彩虹循环效果
void rainbowCycle(uint8_t wait) {
  uint16_t i, j;

  for (j = 0; j < 256; j++) { // 一个完整循环
    for (i = 0; i < NUM_LEDS; i++) {
      leds[i] = Wheel((i * 256 / NUM_LEDS + j) & 255);
    }
    FastLED.show();
    delay(wait);
  }
}

// 生成彩虹色
CRGB Wheel(byte WheelPos) {
  WheelPos = 255 - WheelPos;
  if (WheelPos < 85) {
    return CRGB(255 - WheelPos * 3, 0, WheelPos * 3);
  } else if (WheelPos < 170) {
    WheelPos -= 85;
    return CRGB(0, WheelPos * 3, 255 - WheelPos * 3);
  } else {
    WheelPos -= 170;
    return CRGB(WheelPos * 3, 255 - WheelPos * 3, 0);
  }
}