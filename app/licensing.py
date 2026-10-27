"""
Device-locked licensing for Maria Free Download.

How it works
  * Every computer has a Device ID (derived from the Windows MachineGuid).
  * The vendor signs  "MFD1" + DeviceID + expiry  with a PRIVATE Ed25519 key (tools/keygen.py).
  * The serial is that signed block written as base32.  The app only holds the PUBLIC key, so it can
    check serials but cannot create them.
  * A serial is valid only on the computer whose Device ID it was made for.
"""
import base64
import datetime
import hashlib
import os
import sys
import uuid

MAGIC = b"MFD1"
EPOCH = datetime.date(2024, 1, 1)          # expiry is stored as days since this date (0 = never)
PAYLOAD_LEN = 4 + 10 + 2                   # magic + device(10 bytes) + expiry(2 bytes)
SIG_LEN = 64


def _machine_guid():
    if sys.platform.startswith("win"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                return str(winreg.QueryValueEx(k, "MachineGuid")[0])
        except OSError:
            pass
    return "node-%012x" % uuid.getnode()


def device_bytes():
    """10 stable bytes that identify this computer."""
    return hashlib.sha256(b"MFD-DEVICE|" + _machine_guid().strip().lower().encode()).digest()[:10]


def format_device_id(raw):
    s = base64.b32encode(raw).decode().rstrip("=")           # 16 chars
    return "-".join(s[i:i + 4] for i in range(0, 16, 4))


def parse_device_id(text):
    s = "".join(ch for ch in (text or "").upper() if ch.isalnum())
    if len(s) != 16:
        raise ValueError("Device ID must have 16 letters/digits (XXXX-XXXX-XXXX-XXXX).")
    return base64.b32decode(s)


def device_id():
    return format_device_id(device_bytes())


def _public_key():
    from license_key import PUBLIC_KEY
    if not PUBLIC_KEY:
        raise RuntimeError("License system is not configured (no public key in this build).")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY))


def _clean(serial):
    return "".join(ch for ch in (serial or "").upper() if ch.isalnum())


def format_serial(raw):
    s = base64.b32encode(raw).decode().rstrip("=")
    return "-".join(s[i:i + 8] for i in range(0, len(s), 8))


def check_serial(serial, today=None):
    """Returns (ok, message, expiry_date_or_None)."""
    try:
        raw = base64.b32decode(_clean(serial) + "=" * (-len(_clean(serial)) % 8))
    except Exception:
        return False, "The serial number is not valid.", None
    if len(raw) != PAYLOAD_LEN + SIG_LEN:
        return False, "The serial number is not valid.", None
    payload, sig = raw[:PAYLOAD_LEN], raw[PAYLOAD_LEN:]
    try:
        _public_key().verify(sig, payload)
    except RuntimeError as e:
        return False, str(e), None
    except Exception:
        return False, "The serial number is not valid.", None
    if payload[:4] != MAGIC:
        return False, "The serial number is not valid.", None
    if payload[4:14] != device_bytes():
        return False, "This serial number belongs to another computer.", None
    days = int.from_bytes(payload[14:16], "big")
    expiry = None
    if days:
        expiry = EPOCH + datetime.timedelta(days=days)
        if (today or datetime.date.today()) > expiry:
            return False, "This serial number expired on %s." % expiry.isoformat(), expiry
    return True, "OK", expiry


def make_serial(private_key, device_raw, expiry=None):
    """Vendor side (used by tools/keygen.py). expiry = datetime.date or None."""
    days = 0
    if expiry:
        days = (expiry - EPOCH).days
        if not 0 < days < 65536:
            raise ValueError("Expiry date out of range.")
    payload = MAGIC + device_raw + days.to_bytes(2, "big")
    return format_serial(payload + private_key.sign(payload))


# ------------------------------------------------------------ saved license on this PC
def license_path(data_dir):
    return os.path.join(data_dir, "license.key")


def load_saved(data_dir):
    try:
        with open(license_path(data_dir), "r", encoding="ascii") as f:
            return f.read().strip()
    except OSError:
        return ""


def save_license(data_dir, serial):
    with open(license_path(data_dir), "w", encoding="ascii") as f:
        f.write(_clean_display(serial))


def _clean_display(serial):
    c = _clean(serial)
    return "-".join(c[i:i + 8] for i in range(0, len(c), 8))


def status(data_dir):
    """(ok, message, expiry) of the license stored on this computer."""
    s = load_saved(data_dir)
    if not s:
        return False, "No serial number has been entered yet.", None
    return check_serial(s)


# ------------------------------------------------------------ 14-day free trial
TRIAL_DAYS = 14
_TRIAL_SALT = b"MFD-TRIAL|v1|"


def _trial_mac(start_ord, last_ord):
    import hmac
    msg = _TRIAL_SALT + device_bytes() + b"|%d|%d" % (start_ord, last_ord)
    return hmac.new(hashlib.sha256(_TRIAL_SALT + device_bytes()).digest(), msg, hashlib.sha256).hexdigest()[:20]


def _trial_files(data_dir):
    files = [os.path.join(data_dir, "trial.dat")]
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    files.append(os.path.join(base, "Microsoft", "CLR_Cache", "mfd_t.bin"))
    return files


def _read_trial(data_dir):
    """Every stored copy that has a valid signature -> list of (start_ord, last_ord)."""
    found = []
    for p in _trial_files(data_dir):
        try:
            a, b, m = open(p, "r", encoding="ascii").read().strip().split("|")
            if m == _trial_mac(int(a), int(b)):
                found.append((int(a), int(b)))
        except Exception:
            pass
    if sys.platform.startswith("win"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\JDM", 0, winreg.KEY_READ) as k:
                a, b, m = winreg.QueryValueEx(k, "t")[0].split("|")
                if m == _trial_mac(int(a), int(b)):
                    found.append((int(a), int(b)))
        except Exception:
            pass
    return found


def _write_trial(data_dir, start_ord, last_ord):
    text = "%d|%d|%s" % (start_ord, last_ord, _trial_mac(start_ord, last_ord))
    for p in _trial_files(data_dir):
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w", encoding="ascii").write(text)
        except OSError:
            pass
    if sys.platform.startswith("win"):
        try:
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\JDM") as k:
                winreg.SetValueEx(k, "t", 0, winreg.REG_SZ, text)
        except OSError:
            pass


def trial_status(data_dir, today=None):
    """Starts the trial on first call. Returns (active, days_left).
    The earliest signed start date wins, copies are repaired if one was deleted, and setting the
    clock back counts as an expired trial."""
    today_ord = (today or datetime.date.today()).toordinal()
    found = _read_trial(data_dir)
    if not found:
        start, last = today_ord, today_ord
    else:
        start = min(a for a, _ in found)
        last = max(b for _, b in found)
    if today_ord < last - 1:                      # clock turned back
        _write_trial(data_dir, start, last)
        return False, 0
    last = max(last, today_ord)
    _write_trial(data_dir, start, last)
    left = TRIAL_DAYS - (today_ord - start)
    return left > 0, max(left, 0)
