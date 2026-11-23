"""Create a batch of printable serial codes in Firestore (vendor only).

  pip install firebase-admin
  python tools/serial_batch.py --count 50 --batch "Disc batch 1"

Needs the Firebase *service account* JSON (Project settings -> Service accounts -> Generate new private key).
Keep it next to your private key, e.g. %USERPROFILE%\\MariaKeys\\firebase_service_account.json (never commit it).
Writes  serial_codes_<batch>.csv  with the codes to print on the discs.
"""
import argparse
import base64
import csv
import datetime
import os
import re
import secrets

KEY_DIR = os.environ.get("MFD_KEY_DIR") or os.path.join(os.path.expanduser("~"), "MariaKeys")


def new_code():
    raw = base64.b32encode(secrets.token_bytes(13)).decode().rstrip("=")[:20]     # 100 bits of randomness
    return raw


def pretty(code):
    return "MFD-" + "-".join(code[i:i + 5] for i in range(0, 20, 5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--batch", default="batch")
    ap.add_argument("--key", default=os.path.join(KEY_DIR, "firebase_service_account.json"))
    a = ap.parse_args()
    import firebase_admin
    from firebase_admin import credentials, firestore
    firebase_admin.initialize_app(credentials.Certificate(a.key))
    db = firestore.client()
    codes = []
    while len(codes) < a.count:
        c = new_code()
        ref = db.collection("serials").document(c)
        if ref.get().exists or c in codes:
            continue
        ref.set({"device": None, "activatedAt": None, "batch": a.batch,
                 "created": datetime.datetime.utcnow().isoformat() + "Z"})
        codes.append(c)
    out = "serial_codes_%s.csv" % re.sub(r"\W+", "_", a.batch)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["#", "code", "batch"])
        for i, c in enumerate(codes, 1):
            w.writerow([i, pretty(c), a.batch])
    print("Created %d codes. Print list: %s" % (len(codes), out))


if __name__ == "__main__":
    main()
