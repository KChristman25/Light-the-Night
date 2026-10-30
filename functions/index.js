const {setGlobalOptions} = require("firebase-functions");
const {onDocumentWritten} = require("firebase-functions/v2/firestore");
const {initializeApp} = require("firebase-admin/app");
const {getFirestore} = require("firebase-admin/firestore");

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
