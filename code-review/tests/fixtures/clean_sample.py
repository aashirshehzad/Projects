"""Safe counterparts to every pattern in ``vulnerable_sample.py``.

The scanner must report zero violations here.
"""

import ast
import json
import os
import subprocess

import yaml


def run_user_expression(expr):
    # Safe: literal_eval cannot execute code
    return ast.literal_eval(expr)


def lookup_user(cursor, user_id):
    # Safe: bound parameter
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()


# Safe: secret comes from the environment
AWS_SECRET_ACCESS_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]

# Safe: not actually a secret despite the name fragment
PUBLIC_KEY_PATH = "/etc/ssl/certs/public.pem"


def load_session(blob):
    # Safe: JSON instead of pickle
    return json.loads(blob)


def load_config(raw):
    # Safe: SafeLoader / safe_load
    return yaml.safe_load(raw)


def ping(host):
    # Safe: argument list, no shell
    return subprocess.run(["ping", "-c", "1", host], check=True)


def archive(path):
    # Safe: argument list, no shell
    subprocess.run(["tar", "czf", "backup.tgz", path], check=True)


# ---- safe counterparts for SEC-006 .. SEC-010 ----------------------------
import hashlib
import secrets

import requests


def fetch(url):
    # Safe: verification left on (the default)
    return requests.get(url, timeout=10)


def digest(data):
    # Safe: strong hash
    return hashlib.sha256(data).hexdigest()


def make_token():
    # Safe: cryptographically secure RNG
    session_token = secrets.token_hex(16)
    return session_token


# Safe: read from the environment, default off
DEBUG = os.environ.get("DEBUG") == "1"
ALLOWED_HOSTS = ["example.com", "www.example.com"]


def add_cors(app):
    from fastapi.middleware.cors import CORSMiddleware

    # Safe: explicit origin allowlist
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://app.example.com"],
        allow_credentials=True,
    )


def load_config_file(raw):
    # Safe: safe_load, not unsafe_load
    return yaml.safe_load(raw)
