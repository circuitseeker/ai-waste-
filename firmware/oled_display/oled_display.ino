/*
 * Waste Segregation — OLED status display  (ESP32 DevKit + 1.3" I2C OLED)
 * ----------------------------------------------------------------------
 * A second ESP32 whose only job is to show the classification result. The
 * laptop sends newline-terminated commands over USB serial:
 *
 *   PING                       -> replies "OLED"  (so the backend can find it)
 *   SHOW:<name>|<category>|<bin>-> big BIN word + category + item name
 *   SCAN                       -> shows "Scanning..."
 *   IDLE                       -> shows "Ready"
 *
 * Example:  SHOW:Plastic bottle|Recyclable|DRY
 *
 * Wiring (OLED -> ESP32 DevKit):  VCC->3V3  GND->GND  SDA->GPIO21  SCL->GPIO22
 * 1.3" OLED is usually SH1106; if the screen is split/garbled it's an SSD1306
 * -> switch the constructor (see the commented line).
 * Library: "U8g2" by oliver.
 */
#include <U8g2lib.h>
#include <Wire.h>

U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);
// U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);

#define SDA_PIN 21
#define SCL_PIN 22
const uint32_t BAUD = 115200;

void centerBig(const char *s, int y) {
  u8g2.setFont(u8g2_font_ncenB18_tr);
  int w = u8g2.getStrWidth(s);
  u8g2.drawStr((128 - w) / 2, y, s);
}

void showResult(String name, String cat, String bin) {
  u8g2.clearBuffer();
  // category (top)
  u8g2.setFont(u8g2_font_6x12_tr);
  u8g2.drawStr(0, 10, cat.c_str());
  u8g2.drawHLine(0, 13, 128);
  // bin word (big, center)
  String big = (bin == "WET") ? "WET" : (bin == "DRY") ? "DRY" : "--";
  centerBig(big.c_str(), 40);
  // item name (bottom)
  u8g2.setFont(u8g2_font_6x12_tr);
  u8g2.drawStr(0, 62, name.c_str());
  u8g2.sendBuffer();
}

void showMsg(const char *line1, const char *line2) {
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB14_tr);
  int w = u8g2.getStrWidth(line1);
  u8g2.drawStr((128 - w) / 2, 30, line1);
  if (line2 && line2[0]) {
    u8g2.setFont(u8g2_font_6x12_tr);
    int w2 = u8g2.getStrWidth(line2);
    u8g2.drawStr((128 - w2) / 2, 50, line2);
  }
  u8g2.sendBuffer();
}

void handleLine(String line) {
  line.trim();
  if (line == "PING") {
    Serial.println("OLED");
  } else if (line == "SCAN") {
    showMsg("Scanning", "...");
  } else if (line == "IDLE") {
    showMsg("Ready", "Waste Sorter");
  } else if (line.startsWith("SHOW:")) {
    String body = line.substring(5);
    int p1 = body.indexOf('|');
    int p2 = body.indexOf('|', p1 + 1);
    if (p1 > 0 && p2 > p1) {
      String name = body.substring(0, p1);
      String cat  = body.substring(p1 + 1, p2);
      String bin  = body.substring(p2 + 1);
      showResult(name, cat, bin);
    }
  }
}

void setup() {
  Serial.begin(BAUD);
  Wire.begin(SDA_PIN, SCL_PIN);
  u8g2.begin();
  showMsg("Ready", "Waste Sorter");
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    handleLine(line);
  }
}
