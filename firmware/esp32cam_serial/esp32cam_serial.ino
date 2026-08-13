/*
 * AI Waste Segregation — ESP32-CAM firmware (USB / SERIAL mode, NO Wi-Fi)
 * ----------------------------------------------------------------------
 * The board stays plugged into the laptop over the FTDI/USB cable. The laptop
 * drives everything with one-byte commands over serial; the ESP32 answers.
 * No Wi-Fi, no streaming.
 *
 * PROTOCOL (laptop -> board, one command at a time, request/response):
 *   'C'  capture      -> board replies:  "IMG0" + uint32 len + uint16 w + uint16 h + <len raw RGB565 bytes>
 *   'S'  status       -> board replies:  "DIST <millimetres>\n"   (HC-SR04; 9999 = nothing)
 *   'W'  result=WET   -> drive LCD + 2-axis servo toward wet bin, replies "OK\n"
 *   'D'  result=DRY   -> drive LCD + 2-axis servo toward dry bin, replies "OK\n"
 *   'P'  ping         -> replies "PONG\n"   (used to auto-detect the board)
 *
 * The image is RAW RGB565 (this RHYX/GC0308 sensor + no-PSRAM board can't do
 * JPEG); the laptop converts + byte-swaps it. QQVGA 160x120 = 38400 bytes.
 *
 * Set SERIAL_BAUD to match backend/config.py (SERIAL_BAUD). 115200 is safest;
 * raise to 230400/460800 for faster captures if your FTDI is reliable.
 *
 * Flash: GPIO0->GND + reset to enter bootloader; remove jumper + reset to run.
 * IMPORTANT: close any Serial Monitor before the backend opens the port.
 */

#include "esp_camera.h"
#include "img_converters.h"   // frame2jpg() — software JPEG (small payload, fast transfer)

// AI-Thinker camera pin map
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

// Peripheral pins (broken-out, camera-safe). Wire only what you use.
#define PIN_TRIG      13
#define PIN_ECHO      12
#define PIN_SERVO_SW  14
#define PIN_SERVO_TIP 15

// The serial data rate. MUST equal SERIAL_BAUD in backend/config.py.
const uint32_t SERIAL_BAUD = 921600;

#include <ESP32Servo.h>
Servo servoSwivel;
Servo servoTip;

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
  c.pixel_format = PIXFORMAT_RGB565;                       // no HW JPEG on this sensor
  bool psram = psramFound();
  c.frame_size   = psram ? FRAMESIZE_QVGA : FRAMESIZE_QQVGA;
  c.jpeg_quality = 12;
  // One buffer, filled on demand. The sensor free-runs (no HW single-shot), so
  // doCapture() discards the one stale frame and grabs the next fresh one.
  c.fb_count     = 1;
  c.grab_mode    = CAMERA_GRAB_WHEN_EMPTY;
  c.fb_location  = psram ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  return esp_camera_init(&c) == ESP_OK;
}

float readDistanceMm() {
  digitalWrite(PIN_TRIG, LOW);  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  long dur = pulseIn(PIN_ECHO, HIGH, 30000);
  if (dur == 0) return 9999.0;
  return (dur * 0.0343 / 2.0) * 10.0;   // cm -> mm
}

void writeU32(uint32_t v) { Serial.write((uint8_t *)&v, 4); }
void writeU16(uint16_t v) { Serial.write((uint8_t *)&v, 2); }

void doCapture() {
  // Discard the one stale buffered frame so we send the CURRENT view.
  camera_fb_t *d = esp_camera_fb_get();
  if (d) esp_camera_fb_return(d);
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) { Serial.print("ERR0"); writeU32(0); writeU16(0); writeU16(0); return; }

  // Prefer JPEG (tiny payload -> fast). Fall back to raw RGB565 if it fails.
  uint8_t *jpg = NULL;
  size_t jlen = 0;
  if (frame2jpg(fb, 80, &jpg, &jlen)) {
    Serial.print("JPG0");
    writeU32(jlen); writeU16(fb->width); writeU16(fb->height);
    Serial.write(jpg, jlen);
    Serial.flush();
    free(jpg);
  } else {
    Serial.print("IMG0");
    writeU32(fb->len); writeU16(fb->width); writeU16(fb->height);
    Serial.write(fb->buf, fb->len);
    Serial.flush();
  }
  esp_camera_fb_return(fb);
}

void drive(bool wet) {
  servoSwivel.write(wet ? 0 : 180);
  delay(400);
  servoTip.write(90); delay(700); servoTip.write(0);
  Serial.print("OK\n");
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  servoSwivel.attach(PIN_SERVO_SW);
  servoTip.attach(PIN_SERVO_TIP);
  servoSwivel.write(90);
  servoTip.write(0);
  startCamera();
  // Let a few frames auto-expose before the first real capture.
  for (int i = 0; i < 3; i++) { camera_fb_t *f = esp_camera_fb_get(); if (f) esp_camera_fb_return(f); }
  Serial.print("READY\n");
}

void loop() {
  if (!Serial.available()) return;
  char cmd = Serial.read();
  switch (cmd) {
    case 'C': doCapture(); break;
    case 'S': Serial.print("DIST "); Serial.print((int)readDistanceMm()); Serial.print("\n"); break;
    case 'W': drive(true);  break;
    case 'D': drive(false); break;
    case 'P': Serial.print("PONG\n"); break;
    default: break;   // ignore stray bytes / newlines
  }
}
