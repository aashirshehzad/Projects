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

import os
import pickle
import subprocess
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
