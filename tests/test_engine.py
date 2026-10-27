"""Engine self-test: runs a local HTTP server with Range support and checks
segmented download, pause/resume, non-range fallback and speed limiting."""
import hashlib
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import engine as E  # noqa: E402

DATA = os.urandom(12 * 1024 * 1024 + 12345)
SHA = hashlib.sha256(DATA).hexdigest()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        ranges = "norange" not in self.path
        rng = self.headers.get("Range")
        if ranges and rng:
            a, b = rng.split("=")[1].split("-")
            a = int(a)
            b = int(b) if b else len(DATA) - 1
            body = DATA[a:b + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {a}-{b}/{len(DATA)}")
        else:
            body = DATA
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", 'attachment; filename="test file.bin"')
        if ranges:
            self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        try:
            for i in range(0, len(body), 32768):
                self.wfile.write(body[i:i + 32768])
                if "slow" in self.path:
                    time.sleep(0.004)
        except (BrokenPipeError, ConnectionResetError):
            pass


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_port}"


def wait(eng, d, until, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        eng.tick()
        if until(d):
            return True
        time.sleep(0.1)
    return False


def check(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest() == SHA


tmp = tempfile.mkdtemp()
settings = {"download_dir": tmp, "connections": 8, "max_concurrent": 3, "speed_limit_kb": 0}
eng = E.Engine(tmp, settings)

# 1) segmented
d = eng.add(BASE + "/f")
assert wait(eng, d, lambda x: x.status in (E.COMPLETED, E.ERROR)), d.status
assert d.status == E.COMPLETED, d.error
assert d.filename == "test file.bin" and check(d.path)
print("1 segmented OK, parts:", len(d.segments))

# 2) pause / resume across a restart
d = eng.add(BASE + "/slow")
assert wait(eng, d, lambda x: x.downloaded > 2_000_000)
eng.pause(d)
assert wait(eng, d, lambda x: not x.is_running())
got = d.downloaded
eng.save()
eng2 = E.Engine(tmp, settings)          # simulate app restart
d2 = eng2.get(d.id)
assert d2.status == E.PAUSED and d2.downloaded == got
eng2.resume(d2)
assert wait(eng2, d2, lambda x: x.status in (E.COMPLETED, E.ERROR))
assert d2.status == E.COMPLETED and check(d2.path), d2.error
print("2 pause/resume OK, paused at", got)

# 3) server without Range support
d = eng2.add(BASE + "/norange")
assert wait(eng2, d, lambda x: x.status in (E.COMPLETED, E.ERROR))
assert d.status == E.COMPLETED and check(d.path), d.error
assert not d.resumable
print("3 no-range fallback OK")

# 4) speed limit 2 MB/s on ~12 MB -> ~6 s
eng2.set_speed_limit_kb(2048)
t0 = time.time()
d = eng2.add(BASE + "/f")
assert wait(eng2, d, lambda x: x.status == E.COMPLETED)
dt = time.time() - t0
assert check(d.path)
print(f"4 speed limit OK, {dt:.1f}s (expected ~6s)")
assert 4.5 < dt < 9
print("ALL TESTS PASSED")

# 5) video mode (yt-dlp) end-to-end on a local file via its generic extractor
eng2.set_speed_limit_kb(0)
d = eng2.add(BASE + "/video.mp4", kind="video")
assert wait(eng2, d, lambda x: x.status in (E.COMPLETED, E.ERROR), 60)
assert d.status == E.COMPLETED, d.error
assert check(d.path), d.path
print("5 video mode OK ->", os.path.basename(d.path))
print("ALL VIDEO TESTS PASSED")
