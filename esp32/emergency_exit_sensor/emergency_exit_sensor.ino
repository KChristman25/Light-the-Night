/*
 * Light the Night — Emergency Exit Sensor
 *
 * One of these is installed at each emergency exit.
 * Change EXIT_NUMBER to match the number written on the board (1–4).
 *
 * Wiring:
 *   Reed switch  → GPIO 15 (and GND)  — INPUT_PULLUP, LOW = door closed
 *   Button       → onboard BOOT button (GPIO 0) — press to disarm
 *
 * LED behaviour (built-in LED, GPIO 2):
 *   Solid ON   = armed / door closed
 *   Fast blink = alert active (door opened while armed)
 *   Slow blink = disarmed — staff mode, open/close freely, no alerts
 *
 * Button behaviour:
 *   Press = disarm (clears any active alert silently)
 *   Door physically closes = auto re-arm
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

const char* WIFI_SSID       = "Airplane";
const char* WIFI_PASSWORD   = "crispyink721";
const char* FIREBASE_API_KEY = "AIzaSyBYsQCbHZ6r2KeqJ3-dgmFiR1mZ_IFZ-10";
const char* PROJECT_ID      = "light-the-night-2025";

const int PIN_REED   = 15;
const int PIN_LED    = 2;   // built-in LED on most ESP32 boards
const int PIN_BTN    = 0;   // onboard BOOT button

const unsigned long POLL_MS       = 10000;   // check Firestore for remote clear every 10s
const unsigned long DEBOUNCE_MS   = 80;
const unsigned long TOKEN_MARGIN  = 300000;  // refresh token 5 min before expiry
const unsigned long BLINK_FAST_MS = 300;     // half-period when alert active
const unsigned long BLINK_SLOW_MS = 900;     // half-period when disarmed

String   idToken     = "";
unsigned long tokenExpiry = 0;
bool     doorOpen     = false;
bool     disarmed     = false;
bool     pendingClose = false;  // true when door was opened while disarmed; wait for close to re-arm
unsigned long lastPoll  = 0;
unsigned long lastBlink = 0;
bool     ledState    = false;

// ─── Setup ─────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  pinMode(PIN_REED, INPUT_PULLUP);
  pinMode(PIN_BTN,  INPUT_PULLUP);
  pinMode(PIN_LED, OUTPUT);

  connectWiFi();
  configTime(0, 0, "pool.ntp.org");
  delay(1000);

  signInAnonymously();

  // Sync state from Firestore on boot
  doorOpen = readDoorState();
  Serial.println(doorOpen ? "Boot: door is OPEN" : "Boot: door is secure");
  updateLed();
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

  bool physical = (digitalRead(PIN_REED) == HIGH);  // HIGH = door open

  // While disarmed, track if door was opened so we know to wait for close
  if (disarmed && physical && !pendingClose) {
    pendingClose = true;
    Serial.println("DEBUG: door opened while disarmed — pendingClose=true");
  }

  // Door closed after being opened while disarmed → re-arm
  if (pendingClose && disarmed && !physical) {
    disarmed = false;
    pendingClose = false;
    writeDisarmedState(false);
    Serial.println("Door closed — re-armed");
    updateLed();
  }

  // Debug: print state every 2 seconds
  static unsigned long lastDebug = 0;
  if (millis() - lastDebug > 2000) {
    lastDebug = millis();
    Serial.printf("STATE: physical=%d disarmed=%d pendingClose=%d doorOpen=%d\n", physical, disarmed, pendingClose, doorOpen);
  }

  // BOOT button: disarm (clears any active alert silently)
  if (digitalRead(PIN_BTN) == LOW) {
    delay(50);
    if (digitalRead(PIN_BTN) == LOW) {
      disarmed = true;
      pendingClose = physical;  // only wait for close if door is already open
      if (doorOpen) { doorOpen = false; writeDoorState(false); }
      writeDisarmedState(true);
      Serial.println("Disarmed via button");
      updateLed();
      while (digitalRead(PIN_BTN) == LOW) delay(10);
    }
  }

  // Door opened while armed → trigger alert
  if (!disarmed && physical && !doorOpen) {
    delay(DEBOUNCE_MS);
    if (digitalRead(PIN_REED) == HIGH) {
      doorOpen = true;
      writeDoorState(true);
      Serial.println("Door OPENED");
      updateLed();
    }
  }

  // Poll for remote clear (admin cleared it from the web)
  if (millis() - lastPoll > POLL_MS) {
    lastPoll = millis();
    bool remote = readDoorState();
    if (!remote && doorOpen) {
      doorOpen = false;
      Serial.println("Cleared remotely");
      updateLed();
    }
  }

  updateLed();
  delay(100);
}

// ─── LED ───────────────────────────────────────────────────────────────────
void updateLed() {
  if (!doorOpen && !disarmed) {
    // Solid ON — armed, door closed
    digitalWrite(PIN_LED, HIGH);
    ledState = true;
  } else {
    // Fast blink = alert active, slow blink = disarmed
    unsigned long period = doorOpen ? BLINK_FAST_MS : BLINK_SLOW_MS;
    if (millis() - lastBlink >= period) {
      lastBlink = millis();
      ledState = !ledState;
      digitalWrite(PIN_LED, ledState ? HIGH : LOW);
    }
  }
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

void writeDisarmedState(bool isDisarmed) {
  if (idToken == "") return;

  String url = firestoreBase() + "?updateMask.fieldPaths=disarmed";
  String body = String("{\"fields\":{\"disarmed\":{\"booleanValue\":") +
                (isDisarmed ? "true" : "false") + "}}}";

  HTTPClient http;
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", "Bearer " + idToken);

  int code = http.PATCH(body);
  Serial.println("Disarmed write: " + String(code));
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
