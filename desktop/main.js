// Veyro desktop shell: starts the bundled Python backend on 127.0.0.1 and shows the app.
// Portable: nothing is installed; data lives next to the app (Veyro-Data folder).
const { app, BrowserWindow, Tray, Menu, shell, nativeImage, Notification } = require("electron");
const { spawn, execFile } = require("child_process");
const path = require("path");
const fs = require("fs");
const net = require("net");
const http = require("http");

const IS_PACKED = app.isPackaged;
const RES = IS_PACKED ? process.resourcesPath : path.join(__dirname, "..");
const PY = IS_PACKED ? path.join(RES, "python", "python.exe") : path.join(__dirname, "runtime", "python", "python.exe");
const BACKEND = path.join(RES, "backend");
// Data folder: installed app -> the user's app-data folder (survives updates and uninstall);
// portable exe / unpacked folder -> "Veyro-Data" next to it (an existing folder there is always kept).
const BASE_DIR = process.env.PORTABLE_EXECUTABLE_DIR || path.dirname(process.execPath);
const INSTALLED = IS_PACKED && !process.env.PORTABLE_EXECUTABLE_DIR && fs.existsSync(path.join(BASE_DIR, "Uninstall Veyro.exe"));
const DATA = !IS_PACKED ? path.join(__dirname, "..", "data")
  : INSTALLED && !fs.existsSync(path.join(BASE_DIR, "Veyro-Data")) ? path.join(app.getPath("appData"), "Veyro", "Veyro-Data")
  : path.join(BASE_DIR, "Veyro-Data");
const ICON = path.join(__dirname, "build", "icon.png");

let win = null, splash = null, tray = null, backend = null, port = 8765, quitting = false, toldTray = false;

const GOT_LOCK = app.requestSingleInstanceLock();
if (!GOT_LOCK) { app.quit(); }
app.on("second-instance", () => { if (win) { win.show(); win.focus(); } });
app.setAppUserModelId("com.veyro.app");   // Windows notifications come from "Veyro"

function freePort(start) {
  return new Promise((resolve) => {
    const tryPort = (p) => {
      const s = net.createServer();
      s.once("error", () => tryPort(p + 1));
      s.once("listening", () => s.close(() => resolve(p)));
      s.listen(p, "127.0.0.1");
    };
    tryPort(start);
  });
}

function healthy() {
  return new Promise((resolve) => {
    const req = http.get({ host: "127.0.0.1", port, path: "/api/health", timeout: 1500 }, (r) => { r.resume(); resolve(r.statusCode === 200); });
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

async function startBackend() {
  fs.mkdirSync(DATA, { recursive: true });
  port = await freePort(8765);
  const log = fs.createWriteStream(path.join(DATA, "veyro-server.log"), { flags: "a" });
  backend = spawn(PY, ["-m", "veyro"], {
    cwd: BACKEND, windowsHide: true,
    // Bytecode ships precompiled (tools/build_desktop.py); never try to write .pyc into the install folder.
    env: { ...process.env, VEYRO_PORT: String(port), VEYRO_DATA_DIR: DATA, PYTHONUTF8: "1", PYTHONNOUSERSITE: "1", PYTHONIOENCODING: "utf-8",
           PYTHONDONTWRITEBYTECODE: "1" },
  });
  backend.stdout.pipe(log); backend.stderr.pipe(log);
  backend.on("exit", (code) => { if (!quitting) showFatal(code); });
  for (let i = 0; i < 600; i++) {            // check often (open the window the moment it's ready), up to ~90 s
    if (await healthy()) return true;
    await new Promise((r) => setTimeout(r, 150));
  }
  return false;
}

function stopBackend() {
  if (backend && !backend.killed) {
    try { execFile("taskkill", ["/PID", String(backend.pid), "/T", "/F"], { windowsHide: true }); } catch { /* already gone */ }
  }
}

function splashHtml() {
  return "data:text/html;charset=utf-8," + encodeURIComponent(`<!doctype html><html dir="rtl"><body style="margin:0;display:flex;align-items:center;justify-content:center;height:100vh;background:#FBF6E9;font-family:Tahoma,sans-serif;color:#5C4331">
  <div style="text-align:center"><div style="font-size:40px;font-weight:800;color:#3E9A68">فيرو · Veyro</div>
  <div style="margin-top:10px;font-size:18px">الفريق يجهّز المكتب… · The team is opening the office…</div>
  <div style="margin:18px auto 0;width:160px;height:10px;border-radius:5px;background:#EAD6AE;overflow:hidden"><div style="width:40%;height:100%;background:#F2A43A;animation:m 1.2s steps(6) infinite"></div></div></div>
  <style>@keyframes m{from{transform:translateX(-120%)}to{transform:translateX(300%)}}</style></body></html>`);
}

function showFatal(code) {
  const html = "data:text/html;charset=utf-8," + encodeURIComponent(`<!doctype html><html dir="rtl"><body style="margin:0;display:flex;align-items:center;justify-content:center;height:100vh;background:#FBF6E9;font-family:Tahoma,sans-serif;color:#5C4331;text-align:center">
  <div><div style="font-size:28px;font-weight:800">صار خلل في تشغيل المكتب</div><div style="margin-top:8px">Veyro's engine stopped (${code}). Close and open Veyro again.</div>
  <div style="margin-top:8px;font-size:13px;color:#7A6147">Veyro-Data/veyro-server.log</div></div></body></html>`);
  if (win) win.loadURL(html); else if (splash) splash.loadURL(html);
}

function createTray() {
  tray = new Tray(nativeImage.createFromPath(ICON).resize({ width: 16, height: 16 }));
  tray.setToolTip("Veyro · فيرو");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "فتح فيرو · Open Veyro", click: () => { win.show(); win.focus(); } },
    { type: "separator" },
    { label: "خروج · Quit", click: () => { quitting = true; app.quit(); } },
  ]));
  tray.on("click", () => { win.show(); win.focus(); });
}

async function boot() {
  splash = new BrowserWindow({ width: 520, height: 300, frame: false, resizable: false, backgroundColor: "#FBF6E9", icon: ICON, show: true });
  splash.loadURL(splashHtml());
  const ok = await backendReady;
  if (!ok) { showFatal("timeout"); return; }

  win = new BrowserWindow({
    width: 1440, height: 900, minWidth: 980, minHeight: 680, show: false, backgroundColor: "#FBF6E9", title: "Veyro", icon: ICON,
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  const origin = `http://127.0.0.1:${port}`;
  // News links and anything outside the app open in the normal browser.
  win.webContents.setWindowOpenHandler(({ url }) => { if (/^https?:\/\//.test(url)) shell.openExternal(url); return { action: "deny" }; });
  win.webContents.on("will-navigate", (e, url) => { if (!url.startsWith(origin)) { e.preventDefault(); if (/^https?:\/\//.test(url)) shell.openExternal(url); } });
  win.webContents.session.setPermissionRequestHandler((_wc, perm, cb) => cb(perm === "notifications"));
  await win.loadURL(origin);
  splash.destroy(); splash = null;
  win.show();
  createTray();
  // Closing the window keeps Veyro in the tray so alerts and the morning report keep working.
  win.on("close", (e) => {
    if (quitting) return;
    e.preventDefault(); win.hide();
    if (!toldTray && Notification.isSupported()) {
      toldTray = true;
      new Notification({ title: "Veyro · فيرو", body: "فيرو شغّال في الخلفية للتنبيهات. للخروج: زر فيرو في شريط المهام ← خروج.", icon: ICON }).show();
    }
  });
}

// Start Python straight away, in parallel with Electron's own start-up (the slowest part of launching).
const backendReady = GOT_LOCK ? startBackend() : Promise.resolve(false);
if (GOT_LOCK) app.whenReady().then(boot);
app.on("before-quit", () => { quitting = true; stopBackend(); });
app.on("window-all-closed", () => { /* stay in tray */ });
