// Maria Free Download - browser integration (hands downloads to the desktop app).
const APP = "http://127.0.0.1:9614";
const bypass = new Set();   // URLs the browser should download itself (fallback)

const DEFAULTS = {
  enabled: true,
  minSizeKB: 0,
  skipExt: "",               // e.g. "jpg,png,gif"
};

async function getSettings() {
  return Object.assign({}, DEFAULTS, await chrome.storage.local.get(Object.keys(DEFAULTS)));
}

async function appAlive() {
  try {
    const r = await fetch(APP + "/ping", { signal: AbortSignal.timeout(800) });
    const j = await r.json();
    return j.app === "JDM";
  } catch (e) {
    return false;
  }
}

async function sendToApp(url, filename, referrer, quality) {
  let cookies = "";
  try {
    const list = await chrome.cookies.getAll({ url });
    cookies = list.map(c => `${c.name}=${c.value}`).join("; ");
  } catch (e) { /* ignore */ }
  try {
    const r = await fetch(APP + "/add", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-JDM": "1" },
      body: JSON.stringify({ url, filename, referrer, cookies, userAgent: navigator.userAgent, quality: quality || "" }),
    });
    return r.ok;
  } catch (e) {
    return false;
  }
}

function extOf(name) {
  const m = /\.([a-z0-9]{1,6})(?:$|[?#])/i.exec(name || "");
  return m ? m[1].toLowerCase() : "";
}

chrome.downloads.onCreated.addListener(async (item) => {
  const url = item.finalUrl || item.url;
  if (!/^https?:/i.test(url)) return;              // blob:, data: stay in the browser
  if (bypass.has(url)) { bypass.delete(url); return; }

  const s = await getSettings();
  if (!s.enabled) return;
  const name = (item.filename || "").split(/[\\/]/).pop();
  const skip = s.skipExt.split(",").map(x => x.trim().toLowerCase()).filter(Boolean);
  if (skip.includes(extOf(name || url))) return;
  if (s.minSizeKB > 0 && item.totalBytes > 0 && item.totalBytes < s.minSizeKB * 1024) return;
  if (!(await appAlive())) return;                  // JDM closed -> normal browser download

  try {
    await chrome.downloads.cancel(item.id);
    await chrome.downloads.erase({ id: item.id });
  } catch (e) { /* already finished */ }

  const ok = await sendToApp(url, name, item.referrer || "");
  if (!ok) {
    bypass.add(url);
    chrome.downloads.download({ url });
  }
});

// Right-click menu
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "jdm-link",
    title: "Download with Maria Free Download",
    contexts: ["link", "video", "audio", "image"],
  });
  chrome.contextMenus.create({
    id: "jdm-page",
    title: "Download this page's video with Maria Free Download",
    contexts: ["page"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  let url = info.menuItemId === "jdm-page" ? info.pageUrl : (info.linkUrl || info.srcUrl);
  if (url && url.startsWith("blob:")) url = info.pageUrl;   // streamed video -> send the page
  if (!url) return;
  if (!(await sendToApp(url, "", info.pageUrl || ""))) {
    chrome.downloads.download({ url });
  }
});

// Button injected on YouTube pages
chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg && msg.type === "jdm-video") {
    (async () => {
      if (!(await appAlive())) return reply({ ok: false, reason: "Maria Free Download is not running" });
      reply({ ok: await sendToApp(msg.url, "", (sender.tab && sender.tab.url) || msg.url, msg.quality) });
    })();
    return true;
  }
});
