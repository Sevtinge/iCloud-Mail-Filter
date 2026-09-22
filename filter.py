import email
import imaplib
import os
import re
import time
import json
from email.header import decode_header
from email.message import Message
from email.utils import parseaddr
from html import unescape


def optional_env(*names, default=None):
    """Return an optional environment value; blank and the literal null disable it."""
    for name in names:
        if name not in os.environ:
            continue
        value = os.environ[name].strip()
        if not value or value.casefold() == "null":
            return None
        return value
    return default


HOST = os.getenv("IMAP_HOST", "imap.mail.me.com")
PORT = int(os.getenv("IMAP_PORT", "993"))
TIMEOUT = int(os.getenv("IMAP_TIMEOUT", "30"))
USER = os.environ["ICLOUD_EMAIL"]
PASSWORD = os.environ["ICLOUD_PASSWORD"]

SOURCE_FOLDER = os.getenv("SOURCE_FOLDER", "INBOX")
TARGET_FOLDER = os.getenv("TARGET_FOLDER", "Mail/Test")
MATCH_TEXT = optional_env("MATCH_TEXT", default="test")
# MATCH_SENDER is accepted as an alias for convenience. MATCH_FROM is preferred.
MATCH_FROM = optional_env("MATCH_FROM", "MATCH_SENDER")
INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))
FIRST_RUN_HOURS = int(os.getenv("FIRST_RUN_HOURS", "24"))
MAX_PER_RUN = int(os.getenv("MAX_PER_RUN", "50"))
STATE_FILE = os.getenv("STATE_FILE", "/data/state.json")


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def decode_header_text(value):
    if not value:
        return ""
    parts = []
    for part, enc in decode_header(value):
        if isinstance(part, bytes):
            parts.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            parts.append(part)
    return "".join(parts)


def html_to_text(s):
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return unescape(s)


def message_text(msg: Message):
    pieces = []
    pieces.append(decode_header_text(msg.get("Subject", "")))

    if msg.is_multipart():
        parts = msg.walk()
    else:
        parts = [msg]

    for part in parts:
        if part.get_content_maintype() == "multipart":
            continue
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        try:
            payload = part.get_payload(decode=True)
            if payload is None:
                payload = part.get_payload()
                if not isinstance(payload, str):
                    continue
                text = payload
            else:
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
            if ctype == "text/html":
                text = html_to_text(text)
            pieces.append(text)
        except Exception as e:
            log(f"[WARN] Failed to decode {ctype}: {e}")

    return "\n".join(pieces)


def message_sender(msg: Message):
    """Return decoded From header, display name, and address for matching."""
    raw_from = decode_header_text(msg.get("From", ""))
    display_name, address = parseaddr(raw_from)
    return "\n".join(value for value in (raw_from, display_name, address) if value)


def message_matches(msg: Message, match_text=MATCH_TEXT, match_from=MATCH_FROM):
    """Apply enabled filters. A None filter imposes no restriction."""
    if match_text is not None and match_text.casefold() not in message_text(msg).casefold():
        return False
    if match_from is not None and match_from.casefold() not in message_sender(msg).casefold():
        return False
    return True


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"initialized": False}


def save_state(state):
    directory = os.path.dirname(STATE_FILE)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)


def ensure_folder(imap):
    status, data = imap.list("", f'"{TARGET_FOLDER}"')
    if status == "OK" and data and any(x for x in data if x):
        return True
    status, _ = imap.create(TARGET_FOLDER)
    if status == "OK":
        log(f"[INFO] Created folder: {TARGET_FOLDER}")
        return True
    # Another process/server may have created it between LIST and CREATE.
    status, data = imap.list("", f'"{TARGET_FOLDER}"')
    if status == "OK" and data and any(x for x in data if x):
        return True
    log(f"[ERROR] Cannot create target folder: {TARGET_FOLDER}")
    return False


def connect():
    imap = imaplib.IMAP4_SSL(HOST, PORT, timeout=TIMEOUT)
    imap.login(USER, PASSWORD)
    return imap


def process_once(state):
    imap = None
    try:
        imap = connect()
        log("[INFO] IMAP login successful")

        if not ensure_folder(imap):
            return state

        # This must be writable: messages are flagged \Deleted and expunged below.
        status, _ = imap.select(SOURCE_FOLDER, readonly=False)
        if status != "OK":
            log(f"[ERROR] Cannot select {SOURCE_FOLDER}")
            return state

        # First run: only consider recent mail. Later: only unseen mail.
        if not state.get("initialized"):
            since = time.strftime("%d-%b-%Y", time.localtime(time.time() - FIRST_RUN_HOURS * 3600))
            status, data = imap.uid("SEARCH", None, "SINCE", since)
            log(f"[INFO] First run: searching mail since {since}")
        else:
            status, data = imap.uid("SEARCH", None, "UNSEEN")

        if status != "OK":
            log("[ERROR] IMAP SEARCH failed")
            return state

        uids = data[0].split() if data and data[0] else []
        if len(uids) > MAX_PER_RUN:
            uids = uids[-MAX_PER_RUN:]

        log(f"[INFO] Candidates this run: {len(uids)}")

        matched = 0
        for uid in uids:
            try:
                status, data = imap.uid("FETCH", uid, "(BODY.PEEK[])")
                if status != "OK" or not data:
                    continue

                raw = b""
                for item in data:
                    if isinstance(item, tuple):
                        raw += item[1]

                msg = email.message_from_bytes(raw)
                if not message_matches(msg):
                    continue

                status, _ = imap.uid("COPY", uid, TARGET_FOLDER)
                if status != "OK":
                    log(f"[ERROR] Failed to copy UID {uid.decode()} to {TARGET_FOLDER}")
                    continue

                status, _ = imap.uid("STORE", uid, "+FLAGS", r"(\Deleted)")
                if status != "OK":
                    log(f"[ERROR] Copied but failed to delete UID {uid.decode()}")
                    continue

                matched += 1
                log(f"[INFO] Matched and moved UID {uid.decode()}")

            except Exception as e:
                log(f"[WARN] Failed to process UID {uid!r}: {e}")

        # Actually remove messages marked \Deleted.
        if matched:
            imap.expunge()

        state["initialized"] = True
        save_state(state)
        return state

    except Exception as e:
        log(f"[ERROR] IMAP error: {e}")
        return state
    finally:
        if imap is not None:
            try:
                imap.close()
            except Exception:
                pass
            try:
                imap.logout()
            except Exception:
                pass


def main():
    if INTERVAL <= 0:
        raise ValueError("CHECK_INTERVAL must be greater than 0")
    if FIRST_RUN_HOURS < 0:
        raise ValueError("FIRST_RUN_HOURS must not be negative")
    if MAX_PER_RUN <= 0:
        raise ValueError("MAX_PER_RUN must be greater than 0")

    log("[INFO] iCloud Mail Filter started")
    log(
        f"[INFO] Source={SOURCE_FOLDER}, Target={TARGET_FOLDER}, "
        f"MatchText={MATCH_TEXT!r}, MatchFrom={MATCH_FROM!r}, Interval={INTERVAL}s"
    )
    state = load_state()

    while True:
        state = process_once(state)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()


