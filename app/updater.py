"""
Update check for Maria Free Download.

Reads the latest (non pre-release) GitHub release of UPDATE_REPO, compares its tag
with the running version and, when it is newer, returns the installer download link.
"""
import os
import re
import tempfile

import requests

# repository whose Releases hold MariaFreeDownload-Setup-X.Y.Z.exe
# NOTE: releases of a PRIVATE repository cannot be downloaded without a token, so auto-update only works with a
# public releases repository. Set this to the repo you publish installers to.
UPDATE_REPO = "AliAlsaffarMosulUniversity/measures"
API = "https://api.github.com/repos/{repo}/releases/latest"


def parse_version(text):
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def check_latest(current, repo=UPDATE_REPO, timeout=10):
    """Returns {"version", "notes", "page", "asset_url", "asset_name", "size"} if newer, else None."""
    r = requests.get(API.format(repo=repo), timeout=timeout,
                     headers={"Accept": "application/vnd.github+json",
                              "User-Agent": "MariaFreeDownload-updater"})
    r.raise_for_status()
    rel = r.json()
    tag = rel.get("tag_name", "")
    if rel.get("prerelease") or rel.get("draft") or parse_version(tag) <= parse_version(current):
        return None
    asset = next((a for a in rel.get("assets", [])
                  if a.get("name", "").lower().endswith(".exe") and "setup" in a.get("name", "").lower()),
                 None)
    return {"version": tag.lstrip("vV"), "notes": (rel.get("body") or "").strip(),
            "page": rel.get("html_url", ""),
            "asset_url": asset.get("browser_download_url") if asset else "",
            "asset_name": asset.get("name") if asset else "",
            "size": int(asset.get("size") or 0) if asset else 0}


def download_installer(info, progress=None, cancelled=lambda: False):
    """Downloads the installer to the temp folder; returns its path or None if cancelled."""
    path = os.path.join(tempfile.gettempdir(), info["asset_name"] or "MariaFreeDownload-Setup.exe")
    part = path + ".part"
    with requests.get(info["asset_url"], stream=True, timeout=(15, 60),
                      headers={"User-Agent": "MariaFreeDownload-updater"}) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or info.get("size") or 0)
        done = 0
        with open(part, "wb") as f:
            for chunk in r.iter_content(256 * 1024):
                if cancelled():
                    f.close()
                    os.remove(part)
                    return None
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    os.replace(part, path)
    return path
