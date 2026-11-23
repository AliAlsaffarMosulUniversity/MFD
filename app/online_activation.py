"""Online one-computer activation using Firestore (free Spark plan, no server code).

A printed code (e.g. MFD-ABCDE-FGHIJ-KLMNO-PQRST) is a document  serials/<CODE>  with  device = null.
Activating writes this computer's Device ID into it ONCE (enforced by firestore.rules). Another computer
that enters the same code sees "already used".  After a successful claim the result is stored locally,
so the program then works offline.
"""
import datetime
import json
import os
import urllib.error
import urllib.request

import licensing

try:
    import online_config as CFG
except Exception:                                   # pragma: no cover
    CFG = None

OK, ALREADY_MINE, USED, INVALID, NETWORK, NOT_CONFIGURED = (
    "ok", "already_mine", "used_by_other", "invalid", "network", "not_configured")


def normalize(text):
    s = "".join(ch for ch in (text or "").upper() if ch.isalnum())
    if s.startswith("MFD"):
        s = s[3:]
    return s


def looks_like_online_code(text):
    return len(normalize(text)) == 20


def pretty(code):
    return "MFD-" + "-".join(code[i:i + 5] for i in range(0, 20, 5))


def _url(code, query=""):
    base = "https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents/serials/%s" % (
        CFG.FIREBASE_PROJECT_ID, code)
    return base + query


def _http(method, url, body=None, timeout=15):
    """Returns (status_code, json_or_None). Replaced in tests."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, None


def _device_of(doc):
    f = (doc or {}).get("fields", {})
    d = f.get("device", {})
    return d.get("stringValue") or None


def claim(text, device_id=None, http=None):
    """Claim a printed code for this computer. Returns one of the status constants above."""
    http = http or _http
    if not CFG or not CFG.FIREBASE_PROJECT_ID or not CFG.FIREBASE_API_KEY:
        return NOT_CONFIGURED
    code = normalize(text)
    if len(code) != 20:
        return INVALID
    me = (device_id or licensing.device_id()).replace("-", "")
    key = "key=" + CFG.FIREBASE_API_KEY
    try:
        st, doc = http("GET", _url(code, "?" + key))
        if st == 404:
            return INVALID
        if st != 200:
            return NETWORK
        owner = _device_of(doc)
        if owner == me:
            return ALREADY_MINE
        if owner:
            return USED
        q = "?currentDocument.exists=true&updateMask.fieldPaths=device&updateMask.fieldPaths=activatedAt&" + key
        body = {"fields": {"device": {"stringValue": me},
                           "activatedAt": {"stringValue": datetime.datetime.utcnow().isoformat() + "Z"}}}
        st, _ = http("PATCH", _url(code, q), body)
        # whatever the answer, read back: only the real owner wins a race
        st2, doc2 = http("GET", _url(code, "?" + key))
        if st2 != 200:
            return NETWORK
        return OK if _device_of(doc2) == me else USED
    except (urllib.error.URLError, OSError, TimeoutError):
        return NETWORK


# ---------------------------------------------------------------- local record (works offline afterwards)
def _path(data_dir):
    return os.path.join(data_dir, "activation.json")


def save_local(data_dir, text, device_id=None):
    with open(_path(data_dir), "w", encoding="ascii") as f:
        json.dump({"code": normalize(text), "device": (device_id or licensing.device_id())}, f)


def local_status(data_dir):
    """(ok, message) for an online activation stored on this computer."""
    try:
        with open(_path(data_dir), "r", encoding="ascii") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return False, "No serial number has been entered yet."
    if d.get("device") == licensing.device_id() and len(d.get("code", "")) == 20:
        return True, "OK"
    return False, "This serial number belongs to another computer."


MESSAGES = {
    INVALID: "The serial number is not valid.",
    USED: "This code has already been used on another computer.",
    NETWORK: "Could not reach the activation server. Check your internet connection and try again.",
    NOT_CONFIGURED: "Online activation is not configured in this build.",
}
