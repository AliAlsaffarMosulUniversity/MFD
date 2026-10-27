"""
Local bridge between the browser extension and the app.
Listens only on 127.0.0.1. Requests must carry the X-JDM header and JSON body,
so ordinary web pages cannot add downloads (browsers block that cross-origin).
"""
import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

PORT = 9614
events = queue.Queue()          # read by the UI timer


class _Handler(BaseHTTPRequestHandler):
    server_version = "JDM"

    def log_message(self, *a):
        pass

    def _reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _allowed(self):
        origin = self.headers.get("Origin", "")
        if origin and not origin.startswith(("chrome-extension://", "moz-extension://",
                                              "extension://")):
            return False
        return self.headers.get("X-JDM") == "1"

    def do_OPTIONS(self):
        self.send_response(403)
        self.end_headers()

    def do_GET(self):
        if self.path == "/ping":
            return self._reply(200, {"app": "JDM", "ok": True})
        self._reply(404, {"ok": False})

    def do_POST(self):
        if not self._allowed():
            return self._reply(403, {"ok": False})
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(min(n, 1_000_000)) or b"{}")
        except (ValueError, OSError):
            return self._reply(400, {"ok": False})
        if self.path == "/add":
            url = str(data.get("url", ""))
            if not url.lower().startswith(("http://", "https://")):
                return self._reply(400, {"ok": False, "error": "bad url"})
            events.put(("add", data))
            return self._reply(200, {"ok": True})
        if self.path == "/show":
            events.put(("show", {}))
            return self._reply(200, {"ok": True})
        self._reply(404, {"ok": False})


def start_server(port=PORT):
    """Returns the server, or None if the port is taken (another JDM is running)."""
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    except OSError:
        return None
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def signal_running_instance(port=PORT, url=None):
    """If JDM is already running, ask it to show itself (and add url). True if it answered."""
    base = f"http://127.0.0.1:{port}"
    h = {"X-JDM": "1", "Content-Type": "application/json"}
    try:
        if requests.get(base + "/ping", timeout=1).json().get("app") != "JDM":
            return False
        if url:
            requests.post(base + "/add", data=json.dumps({"url": url}), headers=h, timeout=2)
        else:
            requests.post(base + "/show", data="{}", headers=h, timeout=2)
        return True
    except (requests.RequestException, ValueError):
        return False
