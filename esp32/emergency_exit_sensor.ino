/*
 * Light the Night — Emergency Exit Sensor
 *
 * One of these is installed at each emergency exit.
 * Change EXIT_NUMBER to match the number written on the board (1–4).
 *
 * Wiring:
 *   Reed switch  → GPIO 4  (and GND)  — INPUT_PULLUP, LOW = door closed
 *
 * Libraries required (install via Arduino Library Manager):
 *   - ArduinoJson  (by Benoit Blanchon)
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <time.h>

// ─── CHANGE THIS PER DEVICE ────────────────────────────────────────────────
#define EXIT_NUMBER "1"   // 1, 2, 3, or 4 — match the number on the ESP32
// ───────────────────────────────────────────────────────────────────────────

const char* WIFI_SSID       = "Light the Night";
const char* WIFI_PASSWORD   = "Halloween2026";
const char* FIREBASE_API_KEY = "AIzaSyBYsQCbHZ6r2KeqJ3-dgmFiR1mZ_IFZ-10";
const char* PROJECT_ID      = "light-the-night-2025";

const int PIN_REED   = 4;

const unsigned long POLL_MS       = 10000;   // check Firestore for remote clear every 10s
const unsigned long DEBOUNCE_MS   = 80;
const unsigned long TOKEN_MARGIN  = 300000;  // refresh token 5 min before expiry

String   idToken     = "";
unsigned long tokenExpiry = 0;
bool     doorOpen    = false;
unsigned long lastPoll = 0;

// ─── Setup ─────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  pinMode(PIN_REED, INPUT_PULLUP);

  connectWiFi();
  configTime(0, 0, "pool.ntp.org");
  delay(1000);

  signInAnonymously();

  // Sync state from Firestore on boot
  doorOpen = readDoorState();
  Serial.println(doorOpen ? "Boot: door is OPEN" : "Boot: door is secure");
}

// ─── Loop ──────────────────────────────────────────────────────────────────
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi lost — reconnecting");
    connectWiFi();
  }

  if (millis() > tokenExpiry - TOKEN_MARGIN) {
    signInAnonymously();
  }

  // Reed switch: HIGH = door open (magnet pulled away)
  bool physical = (digitalRead(PIN_REED) == HIGH);
  if (physical && !doorOpen) {
    delay(DEBOUNCE_MS);
    if (digitalRead(PIN_REED) == HIGH) {
      doorOpen = true;
      writeDoorState(true);
      Serial.println("Door OPENED");
    }
  }

  // Poll for remote clear (admin cleared it from the web)
  if (millis() - lastPoll > POLL_MS) {
    lastPoll = millis();
    bool remote = readDoorState();
    if (!remote && doorOpen) {
      doorOpen = false;
      Serial.println("Cleared remotely");
    }
  }

  delay(100);
}

// ─── WiFi ──────────────────────────────────────────────────────────────────
void connectWiFi() {
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 40) {
    delay(500);
    Serial.print(".");
    tries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi connected: " + WiFi.localIP().toString());
  } else {
    Serial.println("\nWiFi failed — will retry in loop");
  }
}

// ─── Firebase anonymous auth ───────────────────────────────────────────────
void signInAnonymously() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String("https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=") + FIREBASE_API_KEY;
  http.begin(url);
  http.addHeader("Content-Type", "application/json");

  int code = http.POST("{\"returnSecureToken\":true}");
  if (code == 200) {
    DynamicJsonDocument doc(2048);
    deserializeJson(doc, http.getString());
    idToken = doc["idToken"].as<String>();
    unsigned long expiresIn = doc["expiresIn"].as<unsigned long>();
    tokenExpiry = millis() + expiresIn * 1000UL;
    Serial.println("Auth OK");
  } else {
    Serial.println("Auth failed: " + String(code));
  }
  http.end();
}

// ─── Firestore helpers ─────────────────────────────────────────────────────
String isoNow() {
  time_t now;
  time(&now);
  char buf[25];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", gmtime(&now));
  return String(buf);
}

String firestoreBase() {
  return String("https://firestore.googleapis.com/v1/projects/") +
         PROJECT_ID + "/databases/(default)/documents/emergencyExits/" + EXIT_NUMBER;
}

void writeDoorState(bool isOpen) {
  if (idToken == "") { Serial.println("No token — skipping write"); return; }

  String field = isOpen ? "openedAt" : "clearedAt";
  String url = firestoreBase() + "?updateMask.fieldPaths=isOpen&updateMask.fieldPaths=" + field;

  String body = String("{\"fields\":{\"isOpen\":{\"booleanValue\":") +
                (isOpen ? "true" : "false") +
                "},\"" + field + "\":{\"timestampValue\":\"" + isoNow() + "\"}}}";

  HTTPClient http;
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", "Bearer " + idToken);

  int code = http.PATCH(body);
  Serial.println("Write result: " + String(code));
  http.end();
}

bool readDoorState() {
  if (idToken == "") return false;

  HTTPClient http;
  http.begin(firestoreBase());
  http.addHeader("Authorization", "Bearer " + idToken);

  int code = http.GET();
  bool isOpen = false;

  if (code == 200) {
    DynamicJsonDocument doc(2048);
    deserializeJson(doc, http.getString());
    isOpen = doc["fields"]["isOpen"]["booleanValue"] | false;
  } else if (code == 404) {
    // Document doesn't exist yet — create it with isOpen: false
    writeDoorState(false);
  } else {
    Serial.println("Read failed: " + String(code));
  }

  http.end();
  return isOpen;
}
