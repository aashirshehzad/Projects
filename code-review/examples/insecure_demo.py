"""Deliberately insecure sample for exercising the Hybrid Code Auditor.

Every block below is labelled with the rule it should trigger. The SAFE blocks
at the bottom must produce NO findings -- they are the false-positive check.

Nothing here runs on import (everything is inside a function or a constant), and
the scanner only ever parses this file -- it is never executed.

Try it:
    python -m app.main audit examples/insecure_demo.py --no-llm
    python -m app.main audit examples/insecure_demo.py --pdf demo.pdf
Or zip this folder and drop it into the web UI.
"""

import hashlib
import marshal
import os
import pickle
import random
import ssl
import subprocess

import requests
import yaml

try:  # cPickle only exists on Python 2; import guarded so this file still parses
    import cPickle  # type: ignore
except ImportError:  # pragma: no cover
    cPickle = pickle


# ===========================================================================
# SEC-001  --  Dynamic code execution   (CRITICAL)
# ===========================================================================
def eval_user_input(expr):
    return eval(expr)                       # SEC-001


def exec_user_script(src):
    exec(src)                              # SEC-001


def dynamic_import(name):
    return __import__(name)                # SEC-001


# ===========================================================================
# SEC-002  --  Raw SQL string formatting   (HIGH)
# ===========================================================================
def sql_fstring(cursor, user_id):
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")          # SEC-002


def sql_percent(cursor, name):
    cursor.execute("SELECT * FROM users WHERE name = '%s'" % name)       # SEC-002


def sql_concat(cursor, email):
    cursor.execute("SELECT * FROM users WHERE email = '" + email + "'")  # SEC-002


def sql_format(cursor, role):
    cursor.execute("SELECT * FROM users WHERE role = '{}'".format(role)) # SEC-002


# ===========================================================================
# SEC-003  --  Hardcoded secret assignment   (HIGH)
# ===========================================================================
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI1K7MDENGbPxRfiCYEXAMPLEKEY"        # SEC-003
DATABASE_PASSWORD = "sup3r-s3cret-p4ss"                                  # SEC-003
github_token = "ghp_1234567890abcdefghijklmnopqrstuvwxyzAB"             # SEC-003


class Config:
    api_key = "sk-live-not-a-real-key-000000000000"                     # SEC-003


# ===========================================================================
# SEC-004  --  Unsafe deserialization   (CRITICAL)
# ===========================================================================
def load_pickle(blob):
    return pickle.loads(blob)             # SEC-004


def load_pickle_file(fh):
    return pickle.load(fh)                # SEC-004


def load_yaml(raw):
    return yaml.load(raw)                 # SEC-004  (no SafeLoader)


def load_yaml_fullloader(raw):
    return yaml.load(raw, Loader=yaml.FullLoader)   # SEC-004  (FullLoader still unsafe)


# ===========================================================================
# SEC-005  --  Command injection   (MEDIUM / HIGH when the input is dynamic)
# ===========================================================================
def ping_host(host):
    return subprocess.Popen("ping -c 1 " + host, shell=True)            # SEC-005


def run_with_shell(cmd):
    subprocess.run(cmd, shell=True)                                    # SEC-005


def archive_path(path):
    os.system("tar czf backup.tgz " + path)                            # SEC-005


def os_popen(name):
    return os.popen("id " + name).read()                              # SEC-005


# ===========================================================================
# SEC-006  --  TLS verification disabled   (HIGH)
# ===========================================================================
def fetch_insecure(url):
    return requests.get(url, verify=False)                            # SEC-006


def unverified_ssl():
    return ssl._create_unverified_context()                           # SEC-006


# ===========================================================================
# SEC-007  --  Weak cryptography   (MEDIUM)
# ===========================================================================
def md5_digest(data):
    return hashlib.md5(data).hexdigest()                              # SEC-007


def sha1_via_new(data):
    return hashlib.new("sha1", data).hexdigest()                      # SEC-007


def csrf_token():
    csrf_secret = random.getrandbits(128)                             # SEC-007
    return csrf_secret


# ===========================================================================
# SEC-008  --  Insecure framework configuration   (MEDIUM / HIGH)
# ===========================================================================
DEBUG = True                                                          # SEC-008
ALLOWED_HOSTS = ["*"]                                                 # SEC-008


def serve(app):
    app.run(host="0.0.0.0", debug=True)                               # SEC-008 (x2)


# ===========================================================================
# SEC-009  --  Overly permissive CORS   (HIGH with credentials)
# ===========================================================================
def wire_cors(app):
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_credentials=True,  # SEC-009
    )


CORS_ORIGIN_ALLOW_ALL = True                                          # SEC-009


# ===========================================================================
# SEC-010  --  Extended unsafe deserialization   (CRITICAL / HIGH)
# ===========================================================================
def load_marshal(blob):
    return marshal.loads(blob)                                        # SEC-010


def load_unsafe_yaml(raw):
    return yaml.unsafe_load(raw)                                      # SEC-010


# ===========================================================================
# SAFE  --  these must produce NO findings (false-positive check)
# ===========================================================================
import ast
import json


def safe_eval(expr):
    return ast.literal_eval(expr)                                      # safe


def safe_sql(cursor, user_id):
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))     # safe (bound param)


AWS_SECRET_ACCESS_KEY_FROM_ENV = os.environ["AWS_SECRET_ACCESS_KEY"]   # safe (not a literal)
PUBLIC_KEY_PATH = "/etc/ssl/certs/server.pem"                          # safe ("public" + _path)


def safe_pickle(blob):
    return json.loads(blob)                                            # safe (JSON, not pickle)


def safe_yaml(raw):
    return yaml.safe_load(raw)                                         # safe (safe_load)


def safe_subprocess(host):
    return subprocess.run(["ping", "-c", "1", host], check=True)       # safe (arg list, no shell)


def safe_os_system():
    os.system("echo static string with no user input")                # safe (constant, not dynamic)


def safe_fetch(url):
    return requests.get(url, timeout=10)                              # safe (verify defaults on)


def safe_hash(data):
    return hashlib.sha256(data).hexdigest()                          # safe (strong hash)


def safe_token():
    import secrets

    return secrets.token_hex(16)                                     # safe (CSPRNG)


SAFE_DEBUG = os.environ.get("DEBUG") == "1"                          # safe (env, defaults off)
SAFE_ALLOWED_HOSTS = ["api.example.com"]                            # safe (explicit allowlist)


def safe_marshal_alt(blob):
    import json

    return json.loads(blob)                                          # safe (JSON, not marshal)
