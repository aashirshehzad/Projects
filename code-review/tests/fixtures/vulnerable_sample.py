"""Synthetic file with one deliberate vulnerability per rule (SEC-001..SEC-005).

Nothing here is executed -- the scanner only parses it. Code lives inside
functions so importing the module is inert.
"""

import os
import pickle
import subprocess

import yaml


def run_user_expression(expr):
    # SEC-001: dynamic code execution
    return eval(expr)


def lookup_user(cursor, user_id):
    # SEC-002: raw SQL string formatting via f-string
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
    return cursor.fetchone()


# SEC-003: hardcoded secret assignment
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI1K7MDENGbPxRfiCYEXAMPLEKEY"


def load_session(blob):
    # SEC-004: unsafe deserialization
    return pickle.loads(blob)


def load_config(raw):
    # SEC-004: yaml.load without SafeLoader
    return yaml.load(raw)


def ping(host):
    # SEC-005: command injection via shell=True + interpolation
    return subprocess.Popen("ping -c 1 " + host, shell=True)


def archive(path):
    # SEC-005: os.system with a runtime-built command
    os.system("tar czf backup.tgz " + path)
