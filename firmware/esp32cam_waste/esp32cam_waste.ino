/*
 * AI Waste Segregation — ESP32-CAM firmware (AI-Thinker board)
 * ------------------------------------------------------------
 * The ESP32-CAM is the "eyes + hands" on the bin. The heavy ML model runs on
 * your laptop; this board just:
 *
 *   GET /capture        -> returns one JPEG photo of the item
 *   GET /status         -> {"object":bool,"distance_cm":float}   (HC-SR04)
 *   GET /result?type=X  -> drives LCD + 2-axis servo + conveyor belt
 *                          X is "DRY" or "WET"
 *
 * FLOW: belt carries item to the sensing point -> ultrasonic detects it ->
 * laptop grabs /capture, classifies, then calls /result -> LCD shows the class
 * and the 2-axis servo tips the item into the matching bin.
 *
 * ---------------------------------------------------------------------------
 * IMPORTANT — GPIO on the AI-Thinker ESP32-CAM is scarce (the camera uses most
 * pins). The assignments below use the few broken-out, camera-safe pins. If a
 * peripheral misbehaves, the cleanest fix is a second small MCU (Arduino Nano)
 * for the servos/motor/LCD, driven over serial. Verify pins for your board.
 * ---------------------------------------------------------------------------
 *
 * Libraries (Arduino Library Manager):
 *   - ESP32 board package (Espressif)      Tools > Board > "AI Thinker ESP32-CAM"
 *   - ESP32Servo
 *   - LiquidCrystal_I2C
 *
 * Flash with an FTDI adapter: GPIO0 -> GND to enter bootloader, then reset.
 */

#include "esp_camera.h"
#include "img_converters.h"   // frame2jpg() — software JPEG for non-JPEG sensors
#include <WiFi.h>
#include <WebServer.h>
#include <ESP32Servo.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ----------------------------------------------------------------------------
// USER SETTINGS
// ----------------------------------------------------------------------------
const char *WIFI_SSID = "YOUR_WIFI_SSID";
const char *WIFI_PASS = "YOUR_WIFI_PASSWORD";

// ----------------------------------------------------------------------------
// AI-Thinker camera pin map
// ----------------------------------------------------------------------------
#define PWDN_GPIO_NUM  32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM   0
#define SIOD_GPIO_NUM  26
#define SIOC_GPIO_NUM  27
#define Y9_GPIO_NUM    35
#define Y8_GPIO_NUM    34
#define Y7_GPIO_NUM    39
#define Y6_GPIO_NUM    36
#define Y5_GPIO_NUM    21
#define Y4_GPIO_NUM    19
#define Y3_GPIO_NUM    18
#define Y2_GPIO_NUM     5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM  23
#define PCLK_GPIO_NUM  22

// ----------------------------------------------------------------------------
// Peripheral pins  (camera-safe, broken-out headers)
// ----------------------------------------------------------------------------
#define PIN_TRIG      13   // HC-SR04 trigger
#define PIN_ECHO      12   // HC-SR04 echo  (use a 5V->3.3V divider!)
#define PIN_SERVO_SW  14   // 2-axis servo: swivel toward bin
#define PIN_SERVO_TIP 15   // 2-axis servo: tip platform to drop
#define PIN_MOTOR_IN1  2   // L298N IN1 (belt direction)
#define PIN_MOTOR_IN2  4   // L298N IN2 (also on-board flash LED — see note above)
#define I2C_SDA       16   // LCD I2C  (share with any I2C sensors)
#define I2C_SCL        1   // LCD I2C

const float OBJECT_DISTANCE_CM = 12.0;  // closer than this = object present

WebServer server(80);
Servo servoSwivel;
Servo servoTip;
LiquidCrystal_I2C lcd(0x27, 16, 2);   // change 0x27 to 0x3F if your LCD is blank

// ----------------------------------------------------------------------------
// Camera init
// ----------------------------------------------------------------------------
bool startCamera() {
  camera_config_t c;
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer   = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM;  c.pin_d1 = Y3_GPIO_NUM;
  c.pin_d2 = Y4_GPIO_NUM;  c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM;  c.pin_d5 = Y7_GPIO_NUM;
  c.pin_d6 = Y8_GPIO_NUM;  c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM;  c.pin_pclk = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM; c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM; c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn = PWDN_GPIO_NUM;  c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000;
  // This board's RHYX M21-45 (GC0308-class) sensor does NOT support hardware
  // JPEG, so we grab RGB565 and software-encode to JPEG in handleCapture().
  c.pixel_format = PIXFORMAT_RGB565;
  // Without PSRAM the frame buffer must live in internal RAM, so a 320x240
  // RGB565 frame (~153 KB) won't fit — drop to 160x120 (~38 KB) in that case.
  bool psram = psramFound();
  c.frame_size   = psram ? FRAMESIZE_QVGA : FRAMESIZE_QQVGA;
  c.jpeg_quality = 12;               // unused for RGB565 capture
  c.fb_count     = 1;
  c.grab_mode    = CAMERA_GRAB_LATEST;
  c.fb_location  = psram ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;

  Serial.printf("[cam] PSRAM=%s frame=%s\n", psram ? "yes" : "no",
                psram ? "QVGA(320x240)" : "QQVGA(160x120)");
  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) {
    Serial.printf("[cam] init failed: 0x%x\n", err);
    return false;
  }
  sensor_t *s = esp_camera_sensor_get();
  if (s) Serial.printf("[cam] sensor PID=0x%x\n", s->id.PID);
  return true;
}

// ----------------------------------------------------------------------------
// Ultrasonic
// ----------------------------------------------------------------------------
float readDistanceCm() {
  digitalWrite(PIN_TRIG, LOW);  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  long dur = pulseIn(PIN_ECHO, HIGH, 30000);   // 30ms timeout (~5 m)
  if (dur == 0) return 999.0;
  return dur * 0.0343 / 2.0;
}

// ----------------------------------------------------------------------------
// Actuation
// ----------------------------------------------------------------------------
void runBelt(int ms) {
  digitalWrite(PIN_MOTOR_IN1, HIGH);
  digitalWrite(PIN_MOTOR_IN2, LOW);
  delay(ms);
  digitalWrite(PIN_MOTOR_IN1, LOW);
  digitalWrite(PIN_MOTOR_IN2, LOW);
}

void dropInto(const String &type) {
  lcd.clear();
  lcd.setCursor(0, 0);
  if (type == "WET") {
    lcd.print("WET WASTE");
    servoSwivel.write(0);      // face the wet bin
  } else {
    lcd.print("DRY / PAPER");
    servoSwivel.write(180);    // face the dry bin
  }
  lcd.setCursor(0, 1);
  lcd.print("Sorting...");
  delay(500);
  servoTip.write(90);          // tip the platform -> item falls in
  delay(700);
  servoTip.write(0);           // reset platform
  lcd.setCursor(0, 1);
  lcd.print("Ready       ");
}

// ----------------------------------------------------------------------------
// HTTP handlers
// ----------------------------------------------------------------------------
void handleCapture() {
  // This board (RHYX/GC0308, no PSRAM) can't spare memory to JPEG-encode, so we
  // send the RAW RGB565 frame and let the laptop convert it. Dimensions + format
  // travel in headers so the backend knows how to decode.
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) { server.send(500, "text/plain", "camera error"); return; }

  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("X-Width",  String(fb->width));
  server.sendHeader("X-Height", String(fb->height));
  server.sendHeader("X-Format", "RGB565");
  server.setContentLength(fb->len);
  server.send(200, "application/octet-stream", "");
  server.sendContent((const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

void handleStatus() {
  float d = readDistanceCm();
  bool present = d < OBJECT_DISTANCE_CM;
  String json = "{\"object\":" + String(present ? "true" : "false") +
                ",\"distance_cm\":" + String(d, 1) + "}";
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "application/json", json);
}

void handleResult() {
  String type = server.hasArg("type") ? server.arg("type") : "DRY";
  type.toUpperCase();
  dropInto(type);
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "application/json", "{\"ok\":true,\"bin\":\"" + type + "\"}");
}

// ----------------------------------------------------------------------------
// Setup / loop
// ----------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  Serial.println();

  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_MOTOR_IN1, OUTPUT);
  pinMode(PIN_MOTOR_IN2, OUTPUT);

  Wire.begin(I2C_SDA, I2C_SCL);
  lcd.init();
  lcd.backlight();
  lcd.print("Booting...");

  servoSwivel.attach(PIN_SERVO_SW);
  servoTip.attach(PIN_SERVO_TIP);
  servoSwivel.write(90);
  servoTip.write(0);

  if (!startCamera()) {
    Serial.println("Camera init failed!");
    lcd.clear(); lcd.print("Camera FAIL");
  }

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(400); Serial.print("."); }
  Serial.println();
  Serial.print("ESP32-CAM IP: ");
  Serial.println(WiFi.localIP());     // <-- put this IP into backend/config.py

  lcd.clear();
  lcd.setCursor(0, 0); lcd.print("Ready");
  lcd.setCursor(0, 1); lcd.print(WiFi.localIP());

  server.on("/capture", handleCapture);
  server.on("/status",  handleStatus);
  server.on("/result",  handleResult);
  server.begin();
}

void loop() {
  server.handleClient();

  // Keep the belt feeding items toward the sensing point when idle.
  static unsigned long lastMove = 0;
  if (readDistanceCm() >= OBJECT_DISTANCE_CM && millis() - lastMove > 400) {
    runBelt(250);            // nudge the belt forward
    lastMove = millis();
  }
}
