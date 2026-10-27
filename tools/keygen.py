"""
Serial number generator for Maria Free Download  -  FOR THE VENDOR ONLY (keep private).

  python tools/keygen.py init                       create your key pair (once) + write the public key into the app
  python tools/keygen.py make --device XXXX-XXXX-XXXX-XXXX [--name "Customer"] [--expires 2027-12-31]
  python tools/keygen.py verify --serial ... --device ...
  python tools/keygen.py                            (no arguments) opens a small window

The PRIVATE key is stored OUTSIDE the project:  ~/MariaKeys/private_key.pem  (override with MFD_KEY_DIR).
Back it up safely. If you lose it you cannot issue serials; if someone gets it they can issue serials.
"""
import argparse
import base64
import csv
import datetime
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "app")
sys.path.insert(0, APP)

import licensing as L                                            # noqa: E402
from cryptography.hazmat.primitives import serialization       # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

KEY_DIR = os.environ.get("MFD_KEY_DIR") or os.path.join(os.path.expanduser("~"), "MariaKeys")
PRIV = os.path.join(KEY_DIR, "private_key.pem")
LOG = os.path.join(KEY_DIR, "issued_serials.csv")


def load_private():
    with open(PRIV, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def cmd_init(force=False):
    if os.path.exists(PRIV) and not force:
        raise SystemExit("A private key already exists at %s\nRefusing to overwrite it (use --force only if you "
                         "really want a NEW key; old serials will stop working)." % PRIV)
    os.makedirs(KEY_DIR, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    with open(PRIV, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    try:
        os.chmod(PRIV, 0o600)
    except OSError:
        pass
    pub = base64.b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    path = os.path.join(APP, "license_key.py")
    src = open(path, encoding="utf-8").read()
    src = re.sub(r'PUBLIC_KEY = ".*"', 'PUBLIC_KEY = "%s"' % pub, src)
    open(path, "w", encoding="utf-8").write(src)
    print("Private key saved to:", PRIV)
    print("Public key written to app/license_key.py  -> commit that file and rebuild the installer.")
    return pub


def issue(device_text, name="", expires=None):
    raw = L.parse_device_id(device_text)
    exp = datetime.date.fromisoformat(expires) if expires else None
    serial = L.make_serial(load_private(), raw, exp)
    os.makedirs(KEY_DIR, exist_ok=True)
    new = not os.path.exists(LOG)
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "customer", "device_id", "expires", "serial"])
        w.writerow([datetime.date.today().isoformat(), name, L.format_device_id(raw), exp or "never", serial])
    return serial


def gui():
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.title("Maria - Serial Generator (vendor only)")
    root.geometry("640x420")
    tk.Label(root, text="Customer name").pack(anchor="w", padx=10, pady=(10, 0))
    name = tk.Entry(root, width=70); name.pack(padx=10)
    tk.Label(root, text="Device ID  (XXXX-XXXX-XXXX-XXXX)").pack(anchor="w", padx=10, pady=(8, 0))
    dev = tk.Entry(root, width=70); dev.pack(padx=10)
    tk.Label(root, text="Expiry date YYYY-MM-DD  (leave empty = never expires)").pack(anchor="w", padx=10, pady=(8, 0))
    exp = tk.Entry(root, width=70); exp.pack(padx=10)
    out = tk.Text(root, height=8, width=78, wrap="char"); out.pack(padx=10, pady=10)

    def go():
        try:
            if not os.path.exists(PRIV):
                cmd_init()
            s = issue(dev.get(), name.get().strip(), exp.get().strip() or None)
            out.delete("1.0", "end"); out.insert("1.0", s)
            root.clipboard_clear(); root.clipboard_append(s)
            messagebox.showinfo("Done", "Serial created and copied to the clipboard.")
        except Exception as e:
            messagebox.showerror("Error", str(e))
    tk.Button(root, text="Generate serial", command=go, width=24).pack()
    root.mainloop()


def main():
    if len(sys.argv) == 1:
        return gui()
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("make"); p.add_argument("--device", required=True); p.add_argument("--name", default="")
    p.add_argument("--expires")
    p = sub.add_parser("verify"); p.add_argument("--serial", required=True); p.add_argument("--device", required=True)
    a = ap.parse_args()
    if a.cmd == "init":
        cmd_init(a.force)
    elif a.cmd == "make":
        print(issue(a.device, a.name, a.expires))
    else:
        L.device_bytes = lambda: L.parse_device_id(a.device)      # check against the given device
        print(L.check_serial(a.serial))


if __name__ == "__main__":
    main()
