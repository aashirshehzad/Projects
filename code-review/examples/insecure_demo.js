/**
 * Deliberately insecure sample for exercising the JS/TS side of the auditor.
 * Every block is labelled with the rule it should trigger. The SAFE block at
 * the bottom must produce NO findings.
 *
 * Try it:
 *   python -m app.main audit examples/insecure_demo.js --no-llm
 * Or drop this file (zipped) into the web UI.
 */

const { exec, execFile } = require("child_process");
const https = require("https");
const crypto = require("crypto");

// ===========================================================================
// JS-001 -- Dynamic code execution (CRITICAL)
// ===========================================================================
function evalUserInput(expr) {
  return eval(expr);                                  // JS-001
}

function scheduleFromString(fn) {
  setTimeout(fn, 100);                                 // safe: function reference
  setTimeout("doStuff()", 100);                        // JS-001: literal string
}

function compileAtRuntime(src) {
  return new Function(src);                            // JS-001
}

// ===========================================================================
// JS-002 -- DOM-based XSS sink (HIGH)
// ===========================================================================
function renderComment(el, comment) {
  el.innerHTML = comment;                              // JS-002
}

function writeGreeting(name) {
  document.write("<b>Hello " + name + "</b>");         // JS-002
}

function insertSnippet(el, html) {
  el.insertAdjacentHTML("beforeend", html);            // JS-002
}

// ===========================================================================
// JS-003 -- Hardcoded secret assignment (HIGH)
// ===========================================================================
const STRIPE_SECRET_KEY = "sk_live_not_a_real_key_00000000000000";  // JS-003
const config = { password: "hunter2xyz" };                          // JS-003

class ApiClient {
  constructor() {
    this.apiKey = "abcd1234efgh5678ijkl";               // JS-003
  }
}

// ===========================================================================
// JS-004 -- Command injection (Node child_process) (HIGH)
// ===========================================================================
function backup(path) {
  exec("tar czf backup.tgz " + path);                  // JS-004
}

function build(target) {
  exec(`make ${target}`);                              // JS-004
}

// ===========================================================================
// JS-005 -- Insecure randomness for a secret (MEDIUM)
// ===========================================================================
function makeSessionToken() {
  const sessionToken = Math.random().toString(36).slice(2);  // JS-005
  return sessionToken;
}

// ===========================================================================
// JS-006 -- TLS verification disabled (HIGH)
// ===========================================================================
const insecureAgent = new https.Agent({ rejectUnauthorized: false }); // JS-006
process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";                        // JS-006

// ===========================================================================
// SAFE -- these must produce NO findings (false-positive check)
// ===========================================================================
function safeEval(expr) {
  return JSON.parse(expr);                              // safe
}

function safeSchedule(fn) {
  setTimeout(fn, 100);                                  // safe: function reference
}

function safeRender(el, text) {
  el.textContent = text;                                // safe
}

const apiKeyPath = "/etc/keys/stripe.pem";              // safe: name ends with _path
const publicKey = "not-actually-a-secret-value";        // safe: "public" excluded

function safeBackup(path) {
  execFile("tar", ["czf", "backup.tgz", path]);         // safe: argument array, no shell
}

function safeSessionToken() {
  return crypto.randomUUID();                           // safe: CSPRNG
}

const safeAgent = new https.Agent({ rejectUnauthorized: true }); // safe
