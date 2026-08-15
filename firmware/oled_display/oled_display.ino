/*
 * Waste Segregation — OLED status display  (ESP32 DevKit + 1.3" I2C OLED)
 * ----------------------------------------------------------------------
 * A second ESP32 whose only job is to show the classification result. The
 * laptop sends newline-terminated commands over USB serial:
 *
 *   PING                       -> replies "OLED"  (so the backend can find it)
 *   DIST?                      -> replies "DIST <millimetres>"  (HC-SR04)
 *   SHOW:<name>|<category>|<bin>-> big BIN word + category + item name
 *   SCAN                       -> shows "Scanning..."
 *   IDLE                       -> shows "Ready"
 *
 * Example:  SHOW:Plastic bottle|Recyclable|DRY
 *
 * Wiring:
 *   OLED    -> VCC->3V3  GND->GND  SDA->GPIO21  SCL->GPIO22
 *   HC-SR04 -> VCC->5V   GND->GND  Trig->GPIO25  Echo->GPIO34 (via 1k/2k divider!)
 * 1.3" OLED is usually SH1106; if the screen is split/garbled it's an SSD1306
 * -> switch the constructor (see the commented line).
 * Library: "U8g2" by oliver.
 */
#include <U8g2lib.h>
#include <Wire.h>
#include <ESP32Servo.h>

U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);
// U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);

#define SDA_PIN 21
#define SCL_PIN 22
#define PIN_TRIG 25          // HC-SR04 trigger
#define PIN_ECHO 34          // HC-SR04 echo (input-only pin; use a 1k/2k divider)
#define PIN_SERVO_WETDRY 26  // servo 1: flap to WET or DRY bin
#define PIN_SERVO_EWASTE 27  // servo 2: diverter to the E-WASTE bin
const uint32_t BAUD = 115200;

Servo servoWetDry;   // WET vs DRY
Servo servoEwaste;   // E-waste diverter

// Angles — tweak these to match your mechanism.
const int WD_REST  = 0;     // servo 1 initial / neutral
const int WD_WET   = 90;    // servo 1 -> WET bin
const int WD_DRY   = 180;   // servo 1 -> DRY bin
const int EW_PASS  = 0;     // servo 2 initial / closed
const int EW_DIVERT = 90;   // servo 2 open -> drops into E-WASTE bin
const int HOLD_MS  = 900;   // time to let the item fall

// route is "WET", "DRY" or "EWASTE"
void sortInto(const String &route) {
  if (route == "EWASTE") {
    servoWetDry.write(WD_REST);                 // keep WET/DRY flap neutral
    servoEwaste.write(EW_DIVERT); delay(HOLD_MS);
    servoEwaste.write(EW_PASS);
  } else {
    servoEwaste.write(EW_PASS);                 // make sure e-waste flap closed
    servoWetDry.write(route == "WET" ? WD_WET : WD_DRY);
    delay(HOLD_MS);
    servoWetDry.write(WD_REST);
  }
}

float readDistanceMm() {
  digitalWrite(PIN_TRIG, LOW);  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  long dur = pulseIn(PIN_ECHO, HIGH, 30000);   // 30ms timeout (~5 m)
  if (dur == 0) return 9999.0;
  return (dur * 0.0343 / 2.0) * 10.0;          // cm -> mm
}

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
  // route word (big, center)
  String big = (bin == "WET") ? "WET" : (bin == "DRY") ? "DRY"
             : (bin == "EWASTE") ? "E-WASTE" : "--";
  centerBig(big.c_str(), 40);
  // item name (bottom)
  u8g2.setFont(u8g2_font_6x12_tr);
  u8g2.drawStr(0, 62, name.c_str());
  u8g2.sendBuffer();

  // ...then physically sort it into the bin.
  sortInto(bin);
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
  } else if (line == "DIST?") {
    Serial.print("DIST ");
    Serial.println((int)readDistanceMm());
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
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  servoWetDry.attach(PIN_SERVO_WETDRY);
  servoEwaste.attach(PIN_SERVO_EWASTE);
  servoWetDry.write(WD_REST);
  servoEwaste.write(EW_PASS);
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
