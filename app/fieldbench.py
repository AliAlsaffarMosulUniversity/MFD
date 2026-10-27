"""
Field measurement mode for the research study (Section 6.5 of the paper).

Runs the real Maria engine against a test file and records, per run:
link label, time slot, RTT and loss (ping), strategy, connections, completion time,
goodput, straggler gap, requests, splits, retries and a SHA-256 of the file.
Results are appended to  Documents/MariaBench/field_results.csv
"""
import csv
import datetime
import hashlib
import os
import platform
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import statistics
import urllib.parse

import engine as E

CONFIGS = [("single", 1), ("static", 4), ("adaptive", 4), ("static", 8), ("adaptive", 8),
           ("static", 16), ("adaptive", 16)]
FIELDS = ["timestamp", "link", "time_slot", "server", "file_mb", "rtt_ms", "loss_pct", "note",
          "strategy", "conns", "rep", "completion_s", "goodput_mbps", "straggler_gap_s",
          "requests", "splits", "retries", "status", "sha256"]


def results_dir():
    base = os.path.join(os.path.expanduser("~"), "Documents")
    if not os.path.isdir(base):
        base = os.path.expanduser("~")
    p = os.path.join(base, "MariaBench")
    os.makedirs(p, exist_ok=True)
    return p


def time_slot(now=None):
    h = (now or datetime.datetime.now()).hour
    if 6 <= h < 14:
        return "morning"
    if 17 <= h < 24:
        return "evening-peak"
    if 0 <= h < 6:
        return "night"
    return "afternoon"


def ping(host, count=30):
    """Returns (avg RTT ms, loss %) using the system ping; (None, None) if unavailable."""
    win = platform.system() == "Windows"
    cmd = ["ping", "-n" if win else "-c", str(count), host]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=count * 3 + 10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return None, None
    loss = re.search(r"(\d+(?:\.\d+)?)%\s*(?:packet\s*)?loss", out, re.I)
    if win:
        avg = re.search(r"Average\s*=\s*(\d+)\s*ms", out, re.I)
        rtt = float(avg.group(1)) if avg else None
    else:
        m = re.search(r"=\s*[\d.]+/([\d.]+)/", out)
        rtt = float(m.group(1)) if m else None
    return rtt, (float(loss.group(1)) if loss else None)


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


class FieldRun(threading.Thread):
    """Background measurement; progress messages go to self.events (a queue)."""

    def __init__(self, urls, link, reps, note=""):
        super().__init__(daemon=True)
        self.urls, self.link, self.reps, self.note = urls, link, reps, note
        self.events = queue.Queue()
        self.stop_flag = threading.Event()
        self.total = len(urls) * len(CONFIGS) * reps
        self.done = 0

    def log(self, text):
        self.events.put(("log", text))

    def run(self):
        out = os.path.join(results_dir(), "field_results.csv")
        new = not os.path.exists(out)
        try:
            with open(out, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                if new:
                    w.writeheader()
                for url in self.urls:
                    host = urllib.parse.urlparse(url).hostname or ""
                    self.log(f"Ping {host} …")
                    rtt, loss = ping(host)
                    self.log(f"RTT = {rtt} ms, loss = {loss} %")
                    jobs = [(s, c, r) for r in range(self.reps) for (s, c) in CONFIGS]
                    for s, c, r in jobs:
                        if self.stop_flag.is_set():
                            self.events.put(("end", out))
                            return
                        row = self.one(url, host, s, c, r, rtt, loss)
                        w.writerow(row)
                        f.flush()
                        self.done += 1
                        self.events.put(("progress", self.done, self.total))
                        self.log(f"{s:8s} C={c:2d} rep {r + 1}: {row['completion_s']} s, "
                                 f"{row['goodput_mbps']} Mbps [{row['status']}]")
        except Exception as e:  # noqa: BLE001
            self.log(f"ERROR: {e}")
        self.events.put(("end", out))

    def one(self, url, host, strategy, conns, rep, rtt, loss):
        tmp = tempfile.mkdtemp(prefix="mariabench_")
        eng = E.Engine(tmp, {"download_dir": tmp, "connections": conns, "max_concurrent": 1,
                             "speed_limit_kb": 0})
        d = eng.add(url, tmp, None, conns, None, kind="file")
        d.split_policy = "static" if strategy == "single" else strategy
        t0 = time.monotonic()
        while d.status not in (E.COMPLETED, E.ERROR) and not self.stop_flag.is_set() \
                and time.monotonic() - t0 < 1800:
            eng.tick()
            time.sleep(0.05)
        eng.tick()
        st = d.stats
        t = ((st["t_end"] or time.monotonic()) - (st["t_start"] or t0))
        done = sorted(st["worker_done"])
        gap = done[-1] - statistics.median(done) if len(done) > 1 else 0.0
        ok = d.status == E.COMPLETED
        size = d.size if d.size and d.size > 0 else 0
        row = {"timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
               "link": self.link, "time_slot": time_slot(), "server": host,
               "file_mb": round(size / 1e6, 2), "rtt_ms": rtt, "loss_pct": loss, "note": self.note,
               "strategy": strategy, "conns": conns, "rep": rep,
               "completion_s": round(t, 3), "goodput_mbps": round(size * 8 / 1e6 / t, 3) if ok and t else "",
               "straggler_gap_s": round(gap, 3), "requests": st["requests"], "splits": st["splits"],
               "retries": st["retries"], "status": d.status if ok else f"{d.status}: {d.error}",
               "sha256": sha_file(d.path) if ok and os.path.exists(d.path) else ""}
        d.stop()
        eng.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
        return row
