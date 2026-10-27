"""Licensing tests - run:  python tests/test_license.py"""
import base64, datetime, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
import licensing as L
import license_key
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

key = Ed25519PrivateKey.generate()
license_key.PUBLIC_KEY = base64.b64encode(key.public_key().public_bytes(
    serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()

me = L.device_bytes()
other = bytes(b ^ 0xFF for b in me)
today = datetime.date(2026, 10, 28)

# 1. valid serial on the right device
s = L.make_serial(key, me)
assert L.check_serial(s)[0], "valid serial rejected"
# 2. same serial must NOT work on another computer
L_dev = L.device_bytes
L.device_bytes = lambda: other
ok, msg, _ = L.check_serial(s)
assert not ok and "another computer" in msg, msg
L.device_bytes = L_dev
# 3. serial made for another device is refused here
assert not L.check_serial(L.make_serial(key, other))[0]
# 4. expiry
e = L.make_serial(key, me, datetime.date(2027, 1, 1))
assert L.check_serial(e, today)[0]
ok, msg, _ = L.check_serial(e, datetime.date(2027, 1, 2))
assert not ok and "expired" in msg
# 5. tampering (flip one character) and garbage
t = list(s); i = 5; t[i] = "A" if t[i] != "A" else "B"
assert not L.check_serial("".join(t))[0]
assert not L.check_serial("")[0] and not L.check_serial("hello world")[0]
# 6. serial signed by a different (attacker) key
evil = Ed25519PrivateKey.generate()
assert not L.check_serial(L.make_serial(evil, me))[0]
# 7. formatting: lower case, spaces and dashes are tolerated
assert L.check_serial(s.lower().replace("-", " "))[0]
# 8. device id round trip
d = L.device_id(); assert L.parse_device_id(d) == me and len(d) == 19
# 9. unconfigured build refuses everything
license_key.PUBLIC_KEY = ""
assert not L.check_serial(s)[0]
print("license tests OK  | serial length:", len(s), "| device id:", d)
