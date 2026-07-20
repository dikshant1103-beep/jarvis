"""Read-only Gmail access over IMAP.

Deliberately read-only in two ways:
  1. The mailbox is opened with readonly=True, so even *reading* a message
     never marks it as read or changes anything on the server.
  2. There is no code here that sends, deletes, moves, or flags mail. Jarvis
     can look; it cannot touch.

Auth is an app password (not your real Google password), kept in .env. Uses
only the Python standard library — imaplib + email.
"""
import email
import imaplib
import re
from email.header import decode_header
from email.utils import parseaddr

import config

HOST = "imap.gmail.com"


def configured():
    env = config._load_env()
    return bool(env.get("MAIL_USER")) and bool(env.get("MAIL_APP_PASSWORD"))


def _creds():
    env = config._load_env()
    return env.get("MAIL_USER", ""), env.get("MAIL_APP_PASSWORD", "")


def _decode(raw):
    """Decode a possibly MIME-encoded header into plain text."""
    if not raw:
        return ""
    out = []
    for part, enc in decode_header(raw):
        if isinstance(part, bytes):
            try:
                out.append(part.decode(enc or "utf-8", errors="replace"))
            except (LookupError, TypeError):
                out.append(part.decode("utf-8", errors="replace"))
        else:
            out.append(part)
    return "".join(out).strip()


def _snippet(msg, limit=180):
    """First chunk of the plain-text body, whitespace-collapsed."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and \
                    "attachment" not in str(part.get("Content-Disposition", "")):
                try:
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace")
                    break
                except (AttributeError, LookupError):
                    continue
    else:
        try:
            body = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace")
        except (AttributeError, LookupError):
            body = ""
    return re.sub(r"\s+", " ", body).strip()[:limit]


def fetch(n=8, unread_only=False):
    """Return the most recent messages as dicts. Never mutates the mailbox.

    Raises on connection/auth failure so the caller can show a clear message.
    """
    user, pw = _creds()
    if not user or not pw:
        raise RuntimeError("no mail credentials in .env")

    conn = imaplib.IMAP4_SSL(HOST)
    try:
        conn.login(user, pw)
        # readonly=True → fetching does NOT set the \Seen flag.
        conn.select("INBOX", readonly=True)
        criterion = "UNSEEN" if unread_only else "ALL"
        typ, data = conn.search(None, criterion)
        ids = data[0].split()
        ids = ids[-n:][::-1]  # most recent first

        out = []
        for mid in ids:
            typ, raw = conn.fetch(mid, "(RFC822)")
            if typ != "OK" or not raw or not raw[0]:
                continue
            msg = email.message_from_bytes(raw[0][1])
            name, addr = parseaddr(_decode(msg.get("From", "")))
            out.append({
                "from": name or addr,
                "addr": addr,
                "subject": _decode(msg.get("Subject", "(no subject)")),
                "date": _decode(msg.get("Date", "")),
                "snippet": _snippet(msg),
            })
        return out
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def unread_count():
    user, pw = _creds()
    conn = imaplib.IMAP4_SSL(HOST)
    try:
        conn.login(user, pw)
        conn.select("INBOX", readonly=True)
        typ, data = conn.search(None, "UNSEEN")
        return len(data[0].split())
    finally:
        try:
            conn.logout()
        except Exception:
            pass
