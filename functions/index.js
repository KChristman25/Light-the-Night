const {setGlobalOptions} = require("firebase-functions");
const {onDocumentWritten} = require("firebase-functions/v2/firestore");
const {onSchedule} = require("firebase-functions/v2/scheduler");
const {initializeApp} = require("firebase-admin/app");
const {getFirestore, FieldValue, Timestamp} = require("firebase-admin/firestore");

setGlobalOptions({ maxInstances: 10 });

initializeApp();

const SMTP2GO_API_KEY = "api-E4A974165ED641AF9C41CCF78B42E62C";

async function sendSms(phoneNumber, subject, body) {
  const res = await fetch("https://api.smtp2go.com/v3/email/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      api_key: SMTP2GO_API_KEY,
      to: [`${phoneNumber}@sms.smtp2go.com`],
      sender: "noreply@scfbc.org",
      subject,
      text_body: body
    })
  });
  const json = await res.json();
  if (!res.ok || json.data?.error) throw new Error(JSON.stringify(json));
  return json;
}

exports.emergencyExitAlert = onDocumentWritten({ document: "emergencyExits/{exitId}", minInstances: 1 }, async (event) => {
  const before = event.data.before.exists ? event.data.before.data() : null;
  const after  = event.data.after.exists  ? event.data.after.data()  : null;

  if (!after || !after.isOpen || (before && before.isOpen)) return;

  const exitName = after.name || `Exit ${event.params.exitId}`;

  const db = getFirestore();
  const smsSnap = await db.collection("config").doc("smsSettings").get();
  const phoneNumbers = (smsSnap.data() || {}).phoneNumbers || [];
  if (phoneNumbers.length === 0) return;

  const message = `EMERGENCY EXIT OPENED: ${exitName}. Check the maze immediately.`;

  await Promise.all(
    phoneNumbers.map(num =>
      sendSms(num, "Emergency Exit Alert", message).catch(err => console.error(`SMS failed for ${num}:`, err.message))
    )
  );
});

exports.missingPersonAlert = onDocumentWritten({ document: "alerts_missing/{kidId}", minInstances: 1 }, async (event) => {
  const before = event.data.before.exists ? event.data.before.data() : null;
  const after  = event.data.after.exists  ? event.data.after.data()  : null;

  // Only fire when active flips to true
  if (!after || !after.active || (before && before.active)) return;

  const db = getFirestore();
  const smsSnap = await db.collection("config").doc("missingAlertSettings").get();
  const phoneNumbers = (smsSnap.data() || {}).phoneNumbers || [];
  if (phoneNumbers.length === 0) return;

  const name = after.name || "Unknown";
  const lastStation = after.lastStation ? ` Last seen at: ${after.lastStation}.` : "";
  const extra = after.message ? ` Note: ${after.message}` : "";
  const message = `MISSING CHILD: ${name}.${lastStation}${extra} All staff please search immediately.`;

  await Promise.all(
    phoneNumbers.map(num =>
      sendSms(num, "Missing Child Alert", message).catch(err => console.error(`SMS failed for ${num}:`, err.message))
    )
  );
});

exports.noStartAlert = onDocumentWritten({ document: "alerts/{alertId}" }, async (event) => {
  const before = event.data.before.exists ? event.data.before.data() : null;
  const after  = event.data.after.exists  ? event.data.after.data()  : null;

  // Only fire on new no_start alerts (not updates or deletes)
  if (!after || after.type !== "no_start" || before) return;

  const db = getFirestore();
  const smsSnap = await db.collection("config").doc("noStartAlertSettings").get();
  const phoneNumbers = (smsSnap.data() || {}).phoneNumbers || [];
  if (phoneNumbers.length === 0) return;

  const name = after.name || "Unknown";
  const station = after.stationLabel || after.stationId || "a station";
  const message = `${name} scanned ${station} without starting. Go to entrance to start them.`;

  await Promise.all(
    phoneNumbers.map(num =>
      sendSms(num, "Participant Not Started", message).catch(err => console.error(`SMS failed for ${num}:`, err.message))
    )
  );
});

exports.stationOfflineCheck = onSchedule("every 5 minutes", async () => {
  const db = getFirestore();

  const settingsSnap = await db.collection("config").doc("stationOfflineAlertSettings").get();
  const settings = settingsSnap.data() || {};
  if (!settings.enabled) return;

  const phoneNumbers = settings.phoneNumbers || [];
  if (phoneNumbers.length === 0) return;

  const THRESHOLD_MS = 240000;  // 4 min — matches admin offline flag
  const COOLDOWN_MS  = 600000;  // 10 min between repeat alerts per station

  const [stationsSnap, alertsSnap] = await Promise.all([
    db.collection("stations").get(),
    db.collection("config").doc("stationOfflineAlerts").get(),
  ]);

  const now = Date.now();
  const lastAlerts = alertsSnap.data() || {};
  const offlineLabels = [];
  const updates = {};

  stationsSnap.forEach(doc => {
    const d = doc.data() || {};
    if (d.active === false) return;  // intentionally disabled

    const hb = d.heartbeat?.toMillis?.() || (d.heartbeat?.seconds ? d.heartbeat.seconds * 1000 : 0);
    if (!hb) return;  // never sent a heartbeat yet

    const age = now - hb;

    if (age < THRESHOLD_MS) {
      // Back online — clear cooldown so next outage alerts immediately
      if (lastAlerts[doc.id]) updates[doc.id] = FieldValue.delete();
      return;
    }

    // Offline — check cooldown to avoid spam
    const lastAlertMs = lastAlerts[doc.id]?.toMillis?.() || (lastAlerts[doc.id]?.seconds ? lastAlerts[doc.id].seconds * 1000 : 0);
    if (lastAlertMs && (now - lastAlertMs) < COOLDOWN_MS) return;

    offlineLabels.push(d.label || "Station " + doc.id);
    updates[doc.id] = Timestamp.now();
  });

  if (Object.keys(updates).length) {
    await db.collection("config").doc("stationOfflineAlerts").set(updates, { merge: true });
  }

  if (offlineLabels.length === 0) return;

  const message = `STATION OFFLINE: ${offlineLabels.join(", ")}. Check the maze immediately.`;
  await Promise.all(
    phoneNumbers.map(num =>
      sendSms(num, "Station Offline Alert", message).catch(err => console.error(`SMS failed for ${num}:`, err.message))
    )
  );
});
