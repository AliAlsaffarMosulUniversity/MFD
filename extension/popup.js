const DEFAULTS = { enabled: true, minSizeKB: 0, skipExt: "", hoverButton: true };

(async () => {
  const s = Object.assign({}, DEFAULTS, await chrome.storage.local.get(Object.keys(DEFAULTS)));
  const en = document.getElementById("enabled");
  const min = document.getElementById("minSizeKB");
  const skip = document.getElementById("skipExt");
  en.checked = s.enabled;
  min.value = s.minSizeKB;
  skip.value = s.skipExt;
  const hb = document.getElementById("hoverButton");
  hb.checked = s.hoverButton;
  hb.onchange = () => chrome.storage.local.set({ hoverButton: hb.checked });
  en.onchange = () => chrome.storage.local.set({ enabled: en.checked });
  min.onchange = () => chrome.storage.local.set({ minSizeKB: Math.max(0, parseInt(min.value) || 0) });
  skip.onchange = () => chrome.storage.local.set({ skipExt: skip.value });

  const st = document.getElementById("status");
  try {
    const r = await fetch("http://127.0.0.1:9614/ping", { signal: AbortSignal.timeout(800) });
    const j = await r.json();
    if (j.app !== "JDM") throw new Error();
    st.innerHTML = '<span class="on">●</span> Maria Free Download is running';
  } catch (e) {
    st.innerHTML = '<span class="off">●</span> Maria Free Download is not running';
  }
})();
