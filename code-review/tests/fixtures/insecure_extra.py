"""Deliberate triggers for the SEC-006 .. SEC-010 rules. Parsed, never run."""

import hashlib
import marshal
import ssl

import numpy as np
import requests
import torch


# --- SEC-006  TLS verification disabled -------------------------------------
def fetch(url):
    return requests.get(url, verify=False)                    # SEC-006


def unverified_context():
    return ssl._create_unverified_context()                   # SEC-006


# --- SEC-007  weak cryptography -------------------------------------------
def digest(data):
    return hashlib.md5(data).hexdigest()                      # SEC-007


def digest2(data):
    return hashlib.new("sha1", data).hexdigest()              # SEC-007


def encrypt(key, block):
    from Crypto.Cipher import AES

    return AES.new(key, AES.MODE_ECB).encrypt(block)          # SEC-007


import random


def make_token():
    session_token = random.getrandbits(128)                   # SEC-007
    return session_token


# --- SEC-008  insecure framework configuration ---------------------------
DEBUG = True                                                  # SEC-008
ALLOWED_HOSTS = ["*"]                                         # SEC-008


def serve(app):
    app.run(host="0.0.0.0", debug=True)                       # SEC-008 (x2: host + debug)


# --- SEC-009  overly permissive CORS -----------------------------------
def add_cors(app):
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,                               # SEC-009 (wildcard + creds)
    )


CORS_ORIGIN_ALLOW_ALL = True                                  # SEC-009


# --- SEC-010  extended unsafe deserialization -------------------------
def load_marshal(blob):
    return marshal.loads(blob)                                # SEC-010


def load_model(path):
    return torch.load(path)                                   # SEC-010 (no weights_only)


def load_npy(path):
    return np.load(path, allow_pickle=True)                   # SEC-010
