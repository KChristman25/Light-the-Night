#define TRIG_PIN 9
#define ECHO_PIN 10
#define THRESHOLD_CM 100
unsigned long lastTriggerTime = 0;
const unsigned long cooldown = 3000;  // 3 second cooldown

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
}

void loop() {
  // Trigger the ultrasonic pulse
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  // Read echo time
  long duration = pulseIn(ECHO_PIN, HIGH);
  int distance = duration * 0.034 / 2;

  // If object is within range and cooldown passed
  if (distance < THRESHOLD_CM && (millis() - lastTriggerTime > cooldown)) {
    Serial.println("MOTION");
    lastTriggerTime = millis();
  }

  delay(100);
}
