/*
 * 1.3" I2C OLED "Hello" test  (ESP32)
 * -----------------------------------
 * A 1.3" I2C OLED is almost always an SH1106 (128x64). If your screen stays
 * blank or the image is shifted/split, it's an SSD1306 instead — just switch
 * to the commented-out constructor below (one line).
 *
 * Wiring (ESP32 DevKit):   VCC->3V3   GND->GND   SDA->GPIO21   SCL->GPIO22
 * OLED I2C address is usually 0x3C (some are 0x3D — U8g2 handles it).
 *
 * Library: install "U8g2" by oliver in Arduino Library Manager.
 *
 * NOTE: On an ESP32-CAM (AI-Thinker) GPIO21/22 are used by the camera and are
 * NOT broken out. There, use software I2C on free pins, e.g. SCL=GPIO14,
 * SDA=GPIO15 — see the SW_I2C line at the bottom.
 */
#include <U8g2lib.h>
#include <Wire.h>

// --- 1.3" OLED: SH1106 (default) ---
U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, /*reset=*/U8X8_PIN_NONE);

// --- If it's really an SSD1306, comment the line above and use this: ---
// U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);

#define SDA_PIN 21
#define SCL_PIN 22

void setup() {
  Wire.begin(SDA_PIN, SCL_PIN);
  u8g2.begin();

  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB14_tr);
  u8g2.drawStr(30, 30, "Hello");
  u8g2.setFont(u8g2_font_6x12_tr);
  u8g2.drawStr(10, 52, "Waste Segregation");
  u8g2.sendBuffer();
}

void loop() {
  // nothing — the text just stays on screen
}

/*
 * ESP32-CAM alternative (software I2C on broken-out pins). Replace the
 * constructor + Wire/pins above with:
 *
 *   U8G2_SH1106_128X64_NONAME_F_SW_I2C u8g2(U8G2_R0, 14, 15, U8X8_PIN_NONE);
 *   // args: rotation, SCL=GPIO14, SDA=GPIO15, reset
 *   // and in setup() just call u8g2.begin();  (no Wire.begin needed)
 */
