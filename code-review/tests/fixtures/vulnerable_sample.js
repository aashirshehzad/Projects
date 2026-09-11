// Deliberate triggers for JS-001..JS-006. Parsed only, never executed.
const { exec } = require("child_process");
const https = require("https");

function runExpr(expr) {
  return eval(expr);                                // JS-001
}

function schedule() {
  setTimeout("runIt()", 100);                        // JS-001
}

function makeRunner(src) {
  return new Function(src);                          // JS-001
}

function render(el, data) {
  el.innerHTML = data;                                // JS-002
}

function writePage(name) {
  document.write("<b>" + name + "</b>");              // JS-002
}

const apiKey = "sk-live-not-a-real-key-000000000000"; // JS-003
const config = { password: "hunter2xyz" };            // JS-003

function backup(path) {
  exec("tar czf backup.tgz " + path);                 // JS-004
}

function makeToken() {
  const sessionToken = Math.random().toString(36).slice(2); // JS-005
  return sessionToken;
}

const agent = new https.Agent({ rejectUnauthorized: false }); // JS-006
process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";                // JS-006
