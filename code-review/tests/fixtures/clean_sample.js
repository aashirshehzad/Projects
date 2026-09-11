// Safe counterparts to every pattern in vulnerable_sample.js.
const { execFile } = require("child_process");
const crypto = require("crypto");

function runExpr(expr) {
  return JSON.parse(expr);                    // safe: no eval
}

function schedule(fn) {
  setTimeout(fn, 100);                        // safe: function reference, not a string
}

function render(el, text) {
  el.textContent = text;                      // safe: no HTML sink
}

function writePage(name) {
  document.title = name;                      // safe: unrelated call
}

const apiKeyPath = "/etc/keys/api.pem";        // safe: name ends with _path
const publicKey = "not-actually-a-secret-value"; // safe: "public" excluded

function backup(path) {
  execFile("tar", ["czf", "backup.tgz", path]); // safe: argument array, no shell
}

function makeToken() {
  return crypto.randomUUID();                  // safe: CSPRNG
}

const agent = { rejectUnauthorized: true };     // safe: verification stays on
