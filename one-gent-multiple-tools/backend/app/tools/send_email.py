"""Send an email from the operator's Gmail account via SMTP.

The agent calls this when a user asks for information to be emailed to them
and supplies a recipient address. The message is sent FROM the Gmail account
configured in backend/.env (GMAIL_ADDRESS) using a Google App Password.

Setup (one time):
  1. Turn on 2-Step Verification for the Gmail account.
  2. Create an App Password:  https://myaccount.google.com/apppasswords
  3. In backend/.env set:
       EMAIL_ENABLED=1
       GMAIL_ADDRESS=you@gmail.com
       GMAIL_APP_PASSWORD=the 16-char app password (no spaces)
       EMAIL_ALLOWED_RECIPIENTS=          # optional comma list; empty = any address
       EMAIL_MAX_PER_HOUR=10              # optional simple abuse guard
"""
from __future__ import annotations

import os
import re
import smtplib
import ssl
import time
from email.message import EmailMessage

DECLARATION = {
    "name": "send_email",
    "description": (
        "Email some information to a recipient. Use this ONLY when the user explicitly "
        "asks to be emailed (or to email someone) AND has given a destination email "
        "address. Put a short clear subject and the full information in the body."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email address the user provided."},
            "subject": {"type": "string", "description": "Short subject line."},
            "body": {"type": "string", "description": "Plain-text email body with the information."},
        },
        "required": ["to", "subject", "body"],
    },
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_sent_times: list[float] = []


def _rate_ok(limit: int) -> bool:
    now = time.time()
    cutoff = now - 3600
    _sent_times[:] = [t for t in _sent_times if t > cutoff]
    if len(_sent_times) >= limit:
        return False
    _sent_times.append(now)
    return True


def run(to: str, subject: str, body: str) -> dict:
    if os.environ.get("EMAIL_ENABLED", "").strip().lower() not in ("1", "true", "yes"):
        return {"error": "Email sending is disabled. Set EMAIL_ENABLED=1 and Gmail credentials in backend/.env."}

    sender = os.environ.get("GMAIL_ADDRESS", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not sender or not password:
        return {"error": "GMAIL_ADDRESS / GMAIL_APP_PASSWORD are not set in backend/.env."}

    to = (to or "").strip()
    if not _EMAIL_RE.match(to):
        return {"error": f"'{to}' is not a valid email address."}

    allow = [a.strip().lower() for a in os.environ.get("EMAIL_ALLOWED_RECIPIENTS", "").split(",") if a.strip()]
    if allow and to.lower() not in allow:
        return {"error": f"'{to}' is not in the allowed-recipients list."}

    try:
        limit = int(os.environ.get("EMAIL_MAX_PER_HOUR", "10"))
    except ValueError:
        limit = 10
    if not _rate_ok(limit):
        return {"error": f"Email rate limit reached ({limit}/hour). Try again later."}

    subject = (subject or "(no subject)").strip()[:200]
    body = (body or "").strip()[:8000]

    msg = EmailMessage()
    msg["From"] = f"One Agent <{sender}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body + "\n\n--\nSent by One Agent on behalf of " + sender)

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=20) as smtp:
            smtp.login(sender, password)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        return {"error": "Gmail rejected the login. Check GMAIL_ADDRESS and that GMAIL_APP_PASSWORD is a valid App Password."}
    except (smtplib.SMTPException, OSError) as exc:
        return {"error": f"Failed to send email: {exc}"}

    return {"sent": True, "to": to, "subject": subject, "from": sender}
