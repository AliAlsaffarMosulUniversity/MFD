"""
JDM download engine.

- Multi-connection (segmented) downloads using HTTP Range requests
- Dynamic segment splitting: when a connection finishes, it helps the slowest part
- Pause / resume that survives app restarts (progress saved to JSON)
- Global speed limiter (token bucket)
- Download queue with a max number of simultaneous downloads
"""
import json
import os
import re
import threading
import time
import urllib.parse
import uuid

import requests

CHUNK = 64 * 1024
MIN_SPLIT = 1024 * 1024          # never split a part smaller than 2 x 1 MB
MAX_RETRIES = 8
TEMP_EXT = ".jdmpart"
DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

# statuses
QUEUED, DOWNLOADING, PAUSED, COMPLETED, ERROR, SCHEDULED = (
    "Queued", "Downloading", "Paused", "Completed", "Error", "Scheduled")


# ---------------------------------------------------------------- helpers
def human_size(n):
    if n is None or n < 0:
        return "Unknown"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1024.0


def human_time(sec):
    if sec is None or sec < 0 or sec == float("inf"):
        return ""
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name):
    name = _BAD.sub("_", name).strip().strip(".")
    return name[:200] or "download"


def filename_from_response(resp, url):
    cd = resp.headers.get("Content-Disposition", "")
    m = re.search(r"filename\*\s*=\s*([^']*)'[^']*'([^;]+)", cd, re.I)
    if m:
        enc = m.group(1) or "utf-8"
        try:
            return safe_filename(urllib.parse.unquote(m.group(2).strip().strip('"'), encoding=enc))
        except LookupError:
            return safe_filename(urllib.parse.unquote(m.group(2).strip().strip('"')))
    m = re.search(r'filename\s*=\s*"([^"]+)"', cd, re.I) or re.search(r"filename\s*=\s*([^;]+)", cd, re.I)
    if m:
        raw = m.group(1).strip()
        try:  # servers often send UTF-8 bytes decoded as latin-1
            raw = raw.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        return safe_filename(raw)
    path = urllib.parse.urlparse(url).path
    base = urllib.parse.unquote(os.path.basename(path))
    return safe_filename(base) if base else "download"


def unique_path(path):
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{root} ({i}){ext}"):
        i += 1
    return f"{root} ({i}){ext}"


# ---------------------------------------------------------------- video sites
QUALITIES = {                  # label -> yt-dlp format selector
    "Best quality": "bv*+ba/b",
    "1080p": "bv*[height<=1080]+ba/b[height<=1080]/b",
    "720p": "bv*[height<=720]+ba/b[height<=720]/b",
    "480p": "bv*[height<=480]+ba/b[height<=480]/b",
    "360p": "bv*[height<=360]+ba/b[height<=360]/b",
    "Audio only (M4A)": "ba[ext=m4a]/ba/b",
}
QUALITIES_NO_FFMPEG = {        # single-file formats that need no merging
    "Best quality": "b[ext=mp4]/b",
    "1080p": "b[height<=1080][ext=mp4]/b[height<=1080]/b",
    "720p": "b[height<=720][ext=mp4]/b[height<=720]/b",
    "480p": "b[height<=480][ext=mp4]/b[height<=480]/b",
    "360p": "b[height<=360][ext=mp4]/b[height<=360]/b",
    "Audio only (M4A)": "ba[ext=m4a]/ba/b",
}
_VIDEO_IES = None
_DIRECT_EXT = re.compile(r"\.(zip|rar|7z|exe|msi|iso|pdf|mp3|mp4|mkv|avi|apk|dmg|tar|gz|docx?|xlsx?|pptx?)$", re.I)


def is_video_url(url):
    """True when yt-dlp has a dedicated extractor for this page (YouTube, Facebook, ...)."""
    global _VIDEO_IES
    path = urllib.parse.urlparse(url).path
    if _DIRECT_EXT.search(path):
        return False
    try:
        if _VIDEO_IES is None:
            from yt_dlp.extractor import gen_extractor_classes
            _VIDEO_IES = [ie for ie in gen_extractor_classes()
                          if ie.ie_key() not in ("Generic", "GenericEmbed") and ie.working()]
        return any(ie.suitable(url) for ie in _VIDEO_IES)
    except Exception:  # noqa: BLE001
        return False


def video_hint(msg):
    """A plain-language hint for the most common video-site failures."""
    m = msg.lower()
    if "not a bot" in m or "sign in to confirm" in m or "429" in m or "too many requests" in m:
        return ("\n\nHINT: the video site is blocking this network address. This often happens with a VPN. "
                "Turn the VPN off, or in Settings choose a browser where you are signed in to the site "
                "(\"Video sites: use cookies from\").")
    if "proxy" in m or "tunnel" in m or "ssl" in m or "certificate" in m:
        return ("\n\nHINT: the connection was blocked or altered on the way (VPN, proxy or filter). "
                "Try again with the VPN off or with another VPN server.")
    if "could not copy" in m and "cookie" in m:
        return ("\n\nHINT: close the browser completely and try again, or choose another browser "
                "in Settings.")
    if "drm" in m:
        return "\n\nHINT: this video is DRM-protected and cannot be downloaded."
    return ""


# ---------------------------------------------------------------- limiter
class RateLimiter:
    """Global token bucket shared by every connection. rate = bytes/sec, 0 = unlimited."""

    def __init__(self, rate=0):
        self.lock = threading.Lock()
        self.rate = rate
        self.tokens = 0.0
        self.last = time.monotonic()

    def set_rate(self, rate):
        with self.lock:
            self.rate = max(0, int(rate))
            self.tokens = 0.0
            self.last = time.monotonic()

    def acquire(self, n):
        with self.lock:
            if self.rate <= 0:
                return
            now = time.monotonic()
            self.tokens = min(self.rate, self.tokens + (now - self.last) * self.rate)
            self.last = now
            self.tokens -= n
            deficit = -self.tokens
            rate = self.rate
        if deficit > 0:
            time.sleep(deficit / rate)


# ---------------------------------------------------------------- download
class Download:
    PERSIST = ("id", "url", "final_url", "save_dir", "filename", "temp_name", "size",
               "resumable", "segments", "status", "error", "connections", "headers",
               "added", "finished", "path", "filename_locked", "kind", "quality",
               "elapsed", "limit_kb")

    def __init__(self, engine, url, save_dir, filename=None, connections=8, headers=None):
        self.engine = engine
        self.id = uuid.uuid4().hex[:12]
        self.url = url
        self.final_url = ""
        self.save_dir = save_dir
        self.filename = safe_filename(filename) if filename else ""
        self.filename_locked = bool(filename)
        if not self.filename:
            self.filename = safe_filename(urllib.parse.unquote(
                os.path.basename(urllib.parse.urlparse(url).path)) or "download")
        self.temp_name = ""
        self.size = -1
        self.resumable = False
        self.segments = []            # [{"start", "end", "done"}]
        self.status = QUEUED
        self.error = ""
        self.connections = max(1, min(32, int(connections)))
        self.headers = dict(headers or {})
        self.kind = "file"            # "file" or "video" (YouTube & other sites via yt-dlp)
        # research instrumentation: "adaptive" (default) | "static" (never re-split)
        self.split_policy = "adaptive"
        self.stats = {"requests": 0, "splits": 0, "retries": 0, "worker_done": [],
                      "t_start": None, "t_end": None}
        self.quality = "best"
        self.elapsed = 0.0            # seconds actually spent downloading (pauses excluded)
        self.limit_kb = 0             # per-file speed limit in KB/s, 0 = none
        self.limiter = RateLimiter(0)
        self._run_since = None
        self.added = time.time()
        self.finished = 0
        self.path = ""
        # runtime only
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._fatal = None
        self._active = set()          # indexes of segments with a live worker
        self.speed = 0.0
        self._last_bytes = None
        self._last_t = None
        self.live_connections = 0

    # ---- persistence
    def to_dict(self):
        with self.lock:
            d = {k: getattr(self, k) for k in self.PERSIST}
            d["segments"] = [dict(s) for s in self.segments]
        return d

    @classmethod
    def from_dict(cls, engine, d):
        obj = cls(engine, d["url"], d["save_dir"])
        for k in cls.PERSIST:
            if k in d:
                setattr(obj, k, d[k])
        if obj.status == DOWNLOADING:
            obj.status = QUEUED      # was running when the app closed -> continue
        obj.elapsed = float(obj.elapsed or 0)
        obj.limit_kb = int(obj.limit_kb or 0)
        obj.limiter.set_rate(obj.limit_kb * 1024)
        return obj

    # ---- info
    @property
    def downloaded(self):
        with self.lock:
            return sum(s["done"] for s in self.segments)

    @property
    def temp_path(self):
        return os.path.join(self.save_dir, self.temp_name or (self.filename + TEMP_EXT))

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def progress(self):
        if self.status == COMPLETED:
            return 100.0
        if self.size and self.size > 0:
            return min(100.0, self.downloaded * 100.0 / self.size)
        return 0.0

    def elapsed_now(self):
        """Total download time so far, counting the current run."""
        since = self._run_since
        return self.elapsed + (time.monotonic() - since if since else 0.0)

    def set_limit_kb(self, kb):
        self.limit_kb = max(0, int(kb))
        self.limiter.set_rate(self.limit_kb * 1024)
        self.engine.request_save()

    def eta(self):
        if self.size <= 0 or self.speed <= 1:
            return None
        return (self.size - self.downloaded) / self.speed

    def update_speed(self):
        now = time.monotonic()
        cur = self.downloaded
        if self._last_bytes is None or self.status != DOWNLOADING:
            self._last_bytes, self._last_t = cur, now
            self.speed = 0.0
            return
        dt = now - self._last_t
        if dt >= 0.4:
            inst = max(0, cur - self._last_bytes) / dt
            self.speed = inst if self.speed == 0 else self.speed * 0.6 + inst * 0.4
            self._last_bytes, self._last_t = cur, now

    # ---- control
    def start(self):
        self.stats["t_start"] = self.stats["t_start"] or time.monotonic()
        if self.is_running() or self.status == COMPLETED:
            return
        self._stop.clear()
        self._fatal = None
        self.error = ""
        self.status = DOWNLOADING
        self._thread = threading.Thread(target=self._run_timed, daemon=True)
        self._thread.start()

    def stop(self, new_status=PAUSED):
        if self.status in (DOWNLOADING, QUEUED, SCHEDULED):
            self.status = new_status
        self._stop.set()

    # ---- network
    def _session(self):
        s = requests.Session()
        h = {"User-Agent": DEFAULT_UA, "Accept": "*/*"}
        h.update({k: v for k, v in self.headers.items() if v})
        s.headers.update(h)
        return s

    def _probe(self, session):
        r = session.get(self.url, headers={"Range": "bytes=0-"}, stream=True,
                        timeout=(15, 30), allow_redirects=True)
        try:
            if r.status_code == 206:
                m = re.search(r"/(\d+)\s*$", r.headers.get("Content-Range", ""))
                self.size = int(m.group(1)) if m else -1
                self.resumable = self.size > 0
            elif r.status_code == 200:
                cl = r.headers.get("Content-Length")
                self.size = int(cl) if cl and cl.isdigit() else -1
                self.resumable = (self.size > 0 and
                                  r.headers.get("Accept-Ranges", "").lower() == "bytes")
            else:
                r.raise_for_status()
                raise IOError(f"Unexpected server response {r.status_code}")
            self.final_url = r.url
            if not self.filename_locked:
                self.filename = filename_from_response(r, r.url)
            ctype = r.headers.get("Content-Type", "")
            if "text/html" in ctype and self.size < 200_000 and not os.path.splitext(self.filename)[1]:
                self.filename += ".html"
        finally:
            r.close()
        self.temp_name = self.filename + TEMP_EXT

    def _run_timed(self):
        self._run_since = time.monotonic()
        try:
            self._run()
        finally:
            self.elapsed += time.monotonic() - self._run_since
            self._run_since = None
            self.engine.request_save()

    def _run(self):
        if self.kind == "video":
            return self._run_video()
        session = self._session()
        try:
            os.makedirs(self.save_dir, exist_ok=True)
            fresh = not self.segments or not self.temp_name or not os.path.exists(self.temp_path)
            if fresh:
                self._probe(session)
                if os.path.exists(self.temp_path) and not self.segments:
                    os.remove(self.temp_path)
                with self.lock:
                    self.segments = []
            if self._stop.is_set():
                return
            if self.resumable and self.size > 0:
                self._run_segmented(session)
            else:
                self._run_single(session)
            if self._stop.is_set():
                return
            if self._fatal:
                raise IOError(self._fatal)
            # finished -> rename
            final = unique_path(os.path.join(self.save_dir, self.filename))
            os.replace(self.temp_path, final)
            self.path = final
            self.filename = os.path.basename(final)
            self.status = COMPLETED
            self.finished = time.time()
            self.stats["t_end"] = time.monotonic()
            self.speed = 0
        except Exception as e:  # noqa: BLE001
            if not self._stop.is_set():
                self.status = ERROR
                self.error = str(e)[:300]
        finally:
            session.close()
            self.speed = 0
            self.live_connections = 0
            self.engine.request_save()

    # video sites (YouTube, Facebook, X, TikTok, ...) through yt-dlp
    def _run_video(self):
        import yt_dlp
        from yt_dlp.utils import DownloadCancelled
        files = {}                    # file -> [downloaded, total]

        def hook(h):
            if self._stop.is_set():
                raise DownloadCancelled("paused")
            fn = h.get("filename") or ""
            total = h.get("total_bytes") or h.get("total_bytes_estimate") or 0
            if h.get("status") == "finished":
                total = total or h.get("downloaded_bytes") or 0
                files[fn] = [total, total]
            elif h.get("status") == "downloading":
                files[fn] = [h.get("downloaded_bytes") or 0, total]
            done = sum(v[0] for v in files.values())
            known = sum(v[1] for v in files.values())
            if self._expected > known:
                known = self._expected
            if known:
                self.size = int(known)
            with self.lock:
                self.segments = [{"start": 0, "end": max(0, self.size - 1), "done": int(done)}]
            self.live_connections = 1

        opts = self.engine.ytdl_options(self)
        opts["progress_hooks"] = [hook]
        self._expected = 0
        try:
            os.makedirs(self.save_dir, exist_ok=True)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if self._stop.is_set():
                    return
                if info.get("_type") == "playlist" and info.get("entries"):
                    info = next(e for e in info["entries"] if e)
                self.filename = safe_filename(f"{info.get('title') or 'video'}.{info.get('ext') or 'mp4'}")
                if opts.get("merge_output_format") and info.get("requested_formats"):
                    self.filename = os.path.splitext(self.filename)[0] + "." + opts["merge_output_format"]
                parts = info.get("requested_formats") or [info]
                self._expected = sum(int(f.get("filesize") or f.get("filesize_approx") or 0) for f in parts)
                if self._expected:
                    self.size = self._expected
                self.engine.request_save()
                res = ydl.process_ie_result(info, download=True)
            path = ""
            for rd in (res or {}).get("requested_downloads") or []:
                path = rd.get("filepath") or path
            path = path or (res or {}).get("filepath") or ""
            if path and os.path.exists(path):
                self.path = path
                self.filename = os.path.basename(path)
                self.size = os.path.getsize(path)
            with self.lock:
                self.segments = [{"start": 0, "end": max(0, self.size - 1), "done": max(0, self.size)}]
            self.status = COMPLETED
            self.finished = time.time()
            self.stats["t_end"] = time.monotonic()
        except DownloadCancelled:
            pass
        except Exception as e:  # noqa: BLE001
            if not self._stop.is_set():
                self.status = ERROR
                msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "")
                self.error = (msg[:400] + video_hint(msg))[:900]
        finally:
            self.speed = 0
            self.live_connections = 0
            self.engine.request_save()

    # single stream (server does not support ranges)
    def _run_single(self, session):
        with self.lock:
            self.segments = [{"start": 0, "end": self.size - 1, "done": 0}]
        seg = self.segments[0]
        self.live_connections = 1
        with session.get(self.final_url or self.url, stream=True, timeout=(15, 60)) as r:
            r.raise_for_status()
            with open(self.temp_path, "wb") as f:
                for chunk in r.iter_content(CHUNK):
                    if self._stop.is_set():
                        return
                    if not chunk:
                        continue
                    self.engine.limiter.acquire(len(chunk))
                    self.limiter.acquire(len(chunk))
                    f.write(chunk)
                    with self.lock:
                        seg["done"] += len(chunk)
        if self.size <= 0:
            self.size = seg["done"]
            seg["end"] = self.size - 1
        elif seg["done"] < self.size:
            raise IOError("Connection closed before the file was complete")

    # multi connection
    def _run_segmented(self, session):
        if not os.path.exists(self.temp_path):
            with open(self.temp_path, "wb") as f:
                f.truncate(self.size)
        with self.lock:
            if not self.segments:
                n = self.connections
                part = self.size // n
                if part < MIN_SPLIT:
                    n = max(1, self.size // MIN_SPLIT)
                    part = self.size // n
                for i in range(n):
                    start = i * part
                    end = self.size - 1 if i == n - 1 else start + part - 1
                    self.segments.append({"start": start, "end": end, "done": 0})
            self._active = set()
        self.engine.request_save()

        while True:
            if self._stop.is_set():
                break
            with self.lock:
                active = len(self._active)
                pending = [i for i, s in enumerate(self.segments)
                           if i not in self._active and s["start"] + s["done"] <= s["end"]]
                all_done = all(s["start"] + s["done"] > s["end"] for s in self.segments)
            if self._fatal and active == 0:
                break
            if all_done and active == 0:
                break
            if not self._fatal and active < self.connections:
                if pending:
                    self._spawn(pending[0], session)
                    continue
                idx = self._split_largest() if self.split_policy == "adaptive" else None
                if idx is not None:
                    self._spawn(idx, session)
                    continue
            self.live_connections = active
            time.sleep(0.15)
        # wait for workers to leave
        t0 = time.time()
        while self._active and time.time() - t0 < 45:
            time.sleep(0.05)

    def _spawn(self, idx, session):
        with self.lock:
            self._active.add(idx)
        threading.Thread(target=self._worker, args=(idx, session), daemon=True).start()

    def _split_largest(self):
        with self.lock:
            best, best_rem = None, 0
            for i in self._active:
                s = self.segments[i]
                rem = s["end"] - (s["start"] + s["done"]) + 1
                if rem > best_rem:
                    best, best_rem = s, rem
            if best is None or best_rem < 2 * MIN_SPLIT:
                return None
            pos = best["start"] + best["done"]
            mid = pos + best_rem // 2
            new = {"start": mid, "end": best["end"], "done": 0}
            best["end"] = mid - 1
            self.segments.append(new)
            self.stats["splits"] += 1
            return len(self.segments) - 1

    def _worker(self, idx, session):
        seg = self.segments[idx]
        retries = 0
        try:
            while not self._stop.is_set() and not self._fatal:
                with self.lock:
                    pos = seg["start"] + seg["done"]
                    end = seg["end"]
                if pos > end:
                    self.stats["worker_done"].append(time.monotonic())
                    return
                try:
                    self.stats["requests"] += 1
                    with session.get(self.final_url or self.url,
                                     headers={"Range": f"bytes={pos}-{end}"},
                                     stream=True, timeout=(15, 30)) as r:
                        if r.status_code != 206:
                            raise IOError(f"Server answered {r.status_code} to a range request")
                        with open(self.temp_path, "r+b") as f:
                            f.seek(pos)
                            for chunk in r.iter_content(CHUNK):
                                if self._stop.is_set():
                                    return
                                if not chunk:
                                    continue
                                self.engine.limiter.acquire(len(chunk))
                                self.limiter.acquire(len(chunk))
                                with self.lock:
                                    remaining = seg["end"] - (seg["start"] + seg["done"]) + 1
                                data = chunk[:max(0, remaining)]
                                if data:
                                    f.write(data)
                                    with self.lock:
                                        seg["done"] += len(data)
                                retries = 0
                                if len(data) < len(chunk):
                                    self.stats["worker_done"].append(time.monotonic())
                                    return   # our part was shortened by a split
                except (requests.RequestException, IOError, OSError) as e:
                    retries += 1
                    self.stats["retries"] += 1
                    if retries > MAX_RETRIES:
                        self._fatal = str(e)
                        return
                    self._stop.wait(min(2 ** retries, 30))
        finally:
            with self.lock:
                self._active.discard(idx)


# ---------------------------------------------------------------- engine
class Engine:
    def __init__(self, data_dir, settings):
        self.data_dir = data_dir
        self.settings = settings
        self.limiter = RateLimiter(int(settings.get("speed_limit_kb", 0)) * 1024)
        self.downloads = []
        self.lock = threading.RLock()
        self._dirty = False
        self._db = os.path.join(data_dir, "downloads.json")
        self.load()

    # ---- persistence
    def load(self):
        try:
            with open(self._db, "r", encoding="utf-8") as f:
                items = json.load(f)
            self.downloads = [Download.from_dict(self, d) for d in items]
        except (OSError, ValueError):
            self.downloads = []

    def save(self):
        with self.lock:
            data = [d.to_dict() for d in self.downloads]
            self._dirty = False
        tmp = self._db + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self._db)

    def request_save(self):
        self._dirty = True

    # ---- api
    def add(self, url, save_dir=None, filename=None, connections=None, headers=None,
            status=QUEUED, kind=None, quality="Best quality", limit_kb=0):
        d = Download(self, url, save_dir or self.settings["download_dir"], filename,
                     connections or self.settings.get("connections", 8), headers)
        d.status = status
        d.kind = kind or ("video" if is_video_url(url) else "file")
        d.quality = quality
        d.limit_kb = max(0, int(limit_kb or 0))
        d.limiter.set_rate(d.limit_kb * 1024)
        if d.kind == "video" and not filename:
            d.filename = "Video (reading info…)"
        with self.lock:
            self.downloads.append(d)
        self.request_save()
        return d

    def ytdl_options(self, d):
        ffmpeg = self.settings.get("ffmpeg_path") or ""
        deno = self.settings.get("deno_path") or ""
        table = QUALITIES if ffmpeg else QUALITIES_NO_FFMPEG
        opts = {
            "format": table.get(d.quality, table["Best quality"]),
            "format_sort": ["res", "ext:mp4:m4a"],
            "outtmpl": os.path.join(d.save_dir, "%(title).150B.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "continuedl": True,
            "retries": 10,
            "fragment_retries": 10,
            "concurrent_fragment_downloads": max(1, min(8, d.connections)),
            "windowsfilenames": True,
            "http_headers": {k: v for k, v in d.headers.items() if k in ("User-Agent", "Referer")},
        }
        if ffmpeg:
            opts["ffmpeg_location"] = ffmpeg
            if d.quality != "Audio only (M4A)":
                opts["merge_output_format"] = "mp4"
        if deno:
            opts["js_runtimes"] = {"deno": {"path": deno}}
        browser = (self.settings.get("video_cookies") or "").lower()
        if browser in ("firefox", "edge", "chrome", "brave", "opera"):
            opts["cookiesfrombrowser"] = (browser,)
        rates = [r for r in (self.limiter.rate, d.limiter.rate) if r > 0]
        if rates:
            opts["ratelimit"] = min(rates)
        return opts

    def get(self, did):
        for d in self.downloads:
            if d.id == did:
                return d
        return None

    def resume(self, d):
        if d.status in (PAUSED, ERROR, SCHEDULED):
            d.status = QUEUED
            self.request_save()

    def pause(self, d):
        d.stop(PAUSED)
        self.request_save()

    def remove(self, d, delete_files=False):
        d.stop(PAUSED)
        with self.lock:
            if d in self.downloads:
                self.downloads.remove(d)
        if delete_files:
            def later():
                t0 = time.time()
                while d.is_running() and time.time() - t0 < 10:
                    time.sleep(0.1)
                for p in (d.temp_path, d.path if d.status == COMPLETED else ""):
                    try:
                        if p and os.path.exists(p):
                            os.remove(p)
                    except OSError:
                        pass
            threading.Thread(target=later, daemon=True).start()
        else:
            if d.status != COMPLETED:
                pass  # keep the partial file, user may want it
        self.request_save()

    def redownload(self, d):
        d.stop(PAUSED)
        with d.lock:
            d.segments = []
        d.temp_name = ""
        d.path = ""
        d.elapsed = 0.0
        d.status = QUEUED
        self.request_save()

    def set_speed_limit_kb(self, kb):
        self.settings["speed_limit_kb"] = int(kb)
        self.limiter.set_rate(int(kb) * 1024)

    def start_scheduled(self):
        for d in self.downloads:
            if d.status == SCHEDULED:
                d.status = QUEUED
        self.request_save()

    def stop_all(self, to_status=PAUSED):
        for d in self.downloads:
            if d.status in (DOWNLOADING, QUEUED):
                d.stop(to_status)
        self.request_save()

    def tick(self):
        """Called by the UI every ~0.5s: queue management + speed calculation."""
        max_c = max(1, int(self.settings.get("max_concurrent", 3)))
        with self.lock:
            items = list(self.downloads)
        running = sum(1 for d in items if d.is_running())
        for d in items:
            if running >= max_c:
                break
            if d.status == QUEUED and not d.is_running():
                d.start()
                running += 1
        for d in items:
            d.update_speed()
        if self._dirty:
            try:
                self.save()
            except OSError:
                pass

    def total_speed(self):
        return sum(d.speed for d in self.downloads if d.status == DOWNLOADING)

    def shutdown(self):
        for d in self.downloads:
            if d.is_running():
                d._stop.set()          # keep status -> resumes next start
        t0 = time.time()
        while any(d.is_running() for d in self.downloads) and time.time() - t0 < 3:
            time.sleep(0.05)
        try:
            self.save()
        except OSError:
            pass
