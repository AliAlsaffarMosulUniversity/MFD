// JDM: modern "Download Now" pop-up that appears when the mouse is over a video
// (YouTube, Facebook, X, Instagram, Vimeo, TikTok and most other sites).
(() => {
  if (window.__jdmHover) return;
  window.__jdmHover = true;

  const QUALITIES = ["Best quality", "1080p", "720p", "480p", "360p", "Audio only (M4A)"];
  const MIN_W = 220, MIN_H = 130;
  let enabled = true;
  try {
    chrome.storage.local.get({ hoverButton: true }, (s) => { enabled = s.hoverButton; });
    chrome.storage.onChanged.addListener((c) => {
      if (c.hoverButton) { enabled = c.hoverButton.newValue; if (!enabled) hide(true); }
    });
  } catch (e) { /* extension reloaded */ }

  // ---------- UI (inside a shadow root so site styles can't break it)
  const host = document.createElement("div");
  host.style.cssText = "all:initial;position:fixed;z-index:2147483647;top:0;left:0;pointer-events:none;";
  const root = host.attachShadow({ mode: "closed" });
  root.innerHTML = `
  <style>
    :host { all: initial; }
    .wrap { position: fixed; display: flex; flex-direction: column; align-items: flex-end; gap: 6px;
            opacity: 0; transform: translateY(-6px) scale(.96); pointer-events: none;
            transition: opacity .18s ease, transform .18s ease; font-family: "Segoe UI", system-ui, sans-serif; }
    .wrap.show { opacity: 1; transform: none; pointer-events: auto; }
    .pill { display: flex; align-items: stretch; border-radius: 999px; overflow: hidden;
            background: rgba(12, 74, 92, .88); color: #fff; backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px); box-shadow: 0 6px 22px rgba(0,0,0,.38), inset 0 0 0 1px rgba(255,255,255,.14); }
    button { all: unset; cursor: pointer; display: flex; align-items: center; gap: 8px; color: #fff;
             font-size: 13.5px; font-weight: 600; letter-spacing: .2px; }
    .main { padding: 9px 14px 9px 12px; }
    .main:hover, .more:hover { background: rgba(255,255,255,.12); }
    .more { padding: 0 11px; border-left: 1px solid rgba(255,255,255,.18); }
    .more svg { transition: transform .18s ease; }
    .wrap.open .more svg { transform: rotate(180deg); }
    .icon { width: 22px; height: 22px; border-radius: 50%; background: #f5b83d; display: grid; place-items: center; }
    .menu { display: none; min-width: 170px; padding: 6px; border-radius: 14px; background: rgba(17, 24, 39, .94);
            backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
            box-shadow: 0 10px 28px rgba(0,0,0,.45), inset 0 0 0 1px rgba(255,255,255,.1); }
    .wrap.open .menu { display: block; }
    .menu button { display: flex; width: 100%; box-sizing: border-box; padding: 8px 10px; border-radius: 9px;
                   font-weight: 500; font-size: 13px; justify-content: space-between; }
    .menu button:hover { background: rgba(255,255,255,.1); }
    .menu small { color: #9ca3af; font-size: 11px; }
    .toast { padding: 8px 12px; border-radius: 10px; font-size: 12.5px; font-weight: 600; color: #fff;
             background: rgba(17,24,39,.94); box-shadow: 0 6px 18px rgba(0,0,0,.35); display: none; }
    .toast.ok { display: block; background: rgba(15, 118, 110, .95); }
    .toast.err { display: block; background: rgba(185, 28, 28, .95); }
  </style>
  <div class="wrap">
    <div class="pill">
      <button class="main" title="Download this video with Maria Free Download">
        <span class="icon"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#0c4a5c" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11"/><path d="M6.5 10.5 12 16l5.5-5.5"/><path d="M5 20h14"/></svg></span>
        Download Now
      </button>
      <button class="more" title="Choose quality"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"><path d="m6 9 6 6 6-6"/></svg></button>
    </div>
    <div class="menu"></div>
    <div class="toast"></div>
  </div>`;
  const wrap = root.querySelector(".wrap");
  const menu = root.querySelector(".menu");
  const toast = root.querySelector(".toast");
  QUALITIES.forEach((q) => {
    const b = document.createElement("button");
    b.innerHTML = `<span>${q === "Audio only (M4A)" ? "Audio only" : q}</span><small>${q === "Audio only (M4A)" ? "M4A" : q === "Best quality" ? "MP4" : ""}</small>`;
    b.addEventListener("click", (e) => { e.stopPropagation(); send(q); });
    menu.appendChild(b);
  });
  root.querySelector(".main").addEventListener("click", (e) => { e.stopPropagation(); send("Best quality"); });
  root.querySelector(".more").addEventListener("click", (e) => { e.stopPropagation(); wrap.classList.toggle("open"); });
  ["mouseenter"].forEach((ev) => wrap.addEventListener(ev, () => clearTimeout(hideTimer)));
  wrap.addEventListener("mouseleave", () => scheduleHide());

  function mount() { if (!host.isConnected) (document.body || document.documentElement).appendChild(host); }

  // ---------- which video is under the mouse?
  let current = null, hideTimer = null, lastMove = 0, busy = false;

  function videoAt(x, y) {
    for (const v of document.querySelectorAll("video")) {
      const r = v.getBoundingClientRect();
      if (r.width < MIN_W || r.height < MIN_H) continue;
      if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return v;
    }
    return null;
  }

  function place(v) {
    const r = v.getBoundingClientRect();
    const top = Math.max(8, r.top + 12);
    const right = Math.max(8, window.innerWidth - r.right + 12);
    wrap.style.top = top + "px";
    wrap.style.right = right + "px";
    wrap.style.left = "auto";
  }

  function show(v) {
    clearTimeout(hideTimer);
    mount();
    if (current !== v) { wrap.classList.remove("open"); toast.className = "toast"; }
    current = v;
    place(v);
    wrap.classList.add("show");
  }

  function hide(now) {
    clearTimeout(hideTimer);
    if (now) { wrap.classList.remove("show", "open"); current = null; return; }
  }

  function scheduleHide() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => { if (!busy) { wrap.classList.remove("show", "open"); current = null; } }, 900);
  }

  document.addEventListener("mousemove", (e) => {
    if (!enabled) return;
    const now = performance.now();
    if (now - lastMove < 60) return;
    lastMove = now;
    const v = videoAt(e.clientX, e.clientY);
    if (v) show(v);
    else if (current && !root.querySelector(".wrap:hover")) scheduleHide();
  }, { passive: true });

  window.addEventListener("scroll", () => { if (current) place(current); }, { passive: true, capture: true });
  window.addEventListener("resize", () => { if (current) place(current); }, { passive: true });
  document.addEventListener("fullscreenchange", () => {
    // keep the button visible inside fullscreen players
    const fs = document.fullscreenElement;
    (fs || document.body || document.documentElement).appendChild(host);
  });

  // ---------- the URL we send to JDM
  function videoUrl(v) {
    const src = v.currentSrc || v.src || "";
    const host = location.hostname;
    // pages whose video lives behind a blob: stream -> send a page URL that yt-dlp understands
    if (/facebook\.com$/.test(host) || /(^|\.)fb\.watch$/.test(host)) {
      const box = v.closest('[role="article"], [data-pagelet], [role="main"]') || document;
      const a = box.querySelector('a[href*="/videos/"], a[href*="/reel/"], a[href*="/watch/?v="], a[href*="/share/v/"], a[href*="/share/r/"]');
      if (a) return a.href.split("&__")[0];
      return location.href;
    }
    if (/(^|\.)instagram\.com$/.test(host)) {
      const art = v.closest("article");
      const a = art && art.querySelector('a[href*="/p/"], a[href*="/reel/"]');
      return a ? a.href : location.href;
    }
    if (/(^|\.)(x|twitter)\.com$/.test(host)) {
      const art = v.closest("article");
      const a = art && art.querySelector('a[href*="/status/"]');
      return a ? a.href.replace(/\/(photo|video|analytics).*$/, "") : location.href;
    }
    if (src && /^https?:/.test(src) && !/youtube\.com|googlevideo\.com/.test(src)) return src;  // plain <video src=...>
    return location.href;
  }

  function send(quality) {
    if (!current) return;
    const url = videoUrl(current);
    busy = true;
    wrap.classList.remove("open");
    toast.className = "toast ok";
    toast.textContent = "Sending to Maria…";
    try {
      chrome.runtime.sendMessage({ type: "jdm-video", url, quality, title: document.title }, (r) => {
        busy = false;
        if (chrome.runtime.lastError || !r || !r.ok) {
          toast.className = "toast err";
          toast.textContent = (r && r.reason) || "Open Maria Free Download first";
        } else {
          toast.className = "toast ok";
          toast.textContent = "✓ Added to Maria";
        }
        setTimeout(() => { toast.className = "toast"; scheduleHide(); }, 2200);
      });
    } catch (e) {
      busy = false;
      toast.className = "toast err";
      toast.textContent = "Reload this page";
    }
  }
})();
