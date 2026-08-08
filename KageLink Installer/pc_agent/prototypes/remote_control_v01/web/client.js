"use strict";

const $ = (id) => document.getElementById(id);
const els = {
  video: $("remoteVideo"), stage: $("videoStage"), transform: $("videoTransform"),
  dot: $("connectionDot"), connectionText: $("connectionText"), rolePill: $("rolePill"), modePill: $("modePill"),
  deviceName: $("deviceName"), requestedRole: $("requestedRole"), pairButton: $("pairButton"), disconnectButton: $("disconnectButton"),
  message: $("message"), keyboardButton: $("keyboardButton"), ime: $("imeCapture"), releaseButton: $("releaseButton"),
  zoomOut: $("zoomOutButton"), zoomFit: $("zoomFitButton"), zoomIn: $("zoomInButton"), languageButton: $("languageButton"),
  rttBadge: $("rttBadge"), fpsBadge: $("fpsBadge"), bitrateBadge: $("bitrateBadge"), lossBadge: $("lossBadge"),
  rttValue: $("rttValue"), fpsValue: $("fpsValue"), bitrateValue: $("bitrateValue"), lossValue: $("lossValue"),
};

const I18N = {
  "pt-BR": {
    disconnected: "Desconectado", requesting: "Solicitando…", waiting: "Aguardando aprovação no PC host…",
    approved: "Aprovado. Criando sessão WebRTC…", connected: "Conectado", reconnect: "Reconectar",
    request: "Solicitar conexão", disconnect: "Desconectar", denied: "Conexão negada no PC host.",
    expired: "A solicitação expirou. Solicite novamente.", failed: "Falha de conexão",
    controlDisabled: "O host desativou o controle remoto.", viewOnly: "Sessão somente para visualização.",
    pairTitle: "Conectar", deviceLabel: "Nome deste dispositivo", roleLabel: "Permissão solicitada",
    qualityTitle: "Qualidade", keyboard: "Teclado", fit: "Ajustar", release: "Soltar",
    securityNote: "A sessão fica somente na memória e precisa ser aprovada no PC host.",
  },
  "en-US": {
    disconnected: "Disconnected", requesting: "Requesting…", waiting: "Waiting for approval on the host PC…",
    approved: "Approved. Creating WebRTC session…", connected: "Connected", reconnect: "Reconnect",
    request: "Request connection", disconnect: "Disconnect", denied: "Connection denied on the host PC.",
    expired: "The request expired. Request again.", failed: "Connection failed",
    controlDisabled: "The host disabled remote control.", viewOnly: "View-only session.",
    pairTitle: "Connect", deviceLabel: "This device name", roleLabel: "Requested permission",
    qualityTitle: "Quality", keyboard: "Keyboard", fit: "Fit", release: "Release",
    securityNote: "The session stays in memory only and must be approved on the host PC.",
  },
};

let lang = (navigator.language || "pt-BR").toLowerCase().startsWith("pt") ? "pt-BR" : "en-US";
let pc = null;
let dc = null;
let sessionToken = "";
let sessionRole = "view";
let requestId = "";
let clientNonce = "";
let pairPollTimer = null;
let heartbeatTimer = null;
let pingTimer = null;
let statsTimer = null;
let lastStatsBytes = 0;
let lastStatsAt = 0;
let connected = false;
let composing = false;
const stickyModifiers = new Set();

let zoom = 1;
let panX = 0;
let panY = 0;
const pointers = new Map();
let touchGesture = null;
let longPressTimer = null;
let longPressFired = false;

function t(key) { return I18N[lang][key] || key; }

function applyLanguage() {
  document.documentElement.lang = lang;
  $("pairTitle").textContent = t("pairTitle");
  $("deviceLabel").textContent = t("deviceLabel");
  $("roleLabel").textContent = t("roleLabel");
  $("qualityTitle").textContent = t("qualityTitle");
  $("securityNote").textContent = t("securityNote");
  els.keyboardButton.textContent = t("keyboard");
  els.zoomFit.textContent = t("fit");
  els.releaseButton.textContent = t("release");
  els.disconnectButton.textContent = t("disconnect");
  els.languageButton.textContent = lang === "pt-BR" ? "EN" : "PT";
  if (!connected && !requestId) els.connectionText.textContent = t("disconnected");
  els.pairButton.textContent = sessionToken ? t("reconnect") : t("request");
}

function setStatus(text, level = "") {
  els.connectionText.textContent = text;
  els.dot.className = `status-dot ${level}`.trim();
}

function setMessage(text) { els.message.textContent = text; }

function setControlUi() {
  const canControl = connected && sessionRole === "control" && dc && dc.readyState === "open";
  document.querySelectorAll("#controlToolbar button[data-key], #keyboardButton, #releaseButton").forEach((button) => {
    button.disabled = !canControl;
  });
  els.rolePill.textContent = sessionRole === "control" ? "CONTROL" : "VIEW";
}

function randomToken(bytes = 24) {
  const data = new Uint8Array(bytes);
  crypto.getRandomValues(data);
  let binary = "";
  for (const value of data) binary += String.fromCharCode(value);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

async function jsonFetch(path, { method = "POST", body = null, token = "" } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers,
    body: body === null ? null : JSON.stringify(body),
  });
  let payload = {};
  try { payload = await response.json(); } catch (_) { payload = {}; }
  if (!response.ok || payload.ok === false) {
    const error = new Error(payload.error || `HTTP_${response.status}`);
    error.code = payload.error || `HTTP_${response.status}`;
    throw error;
  }
  return payload;
}

function defaultDeviceName() {
  const touch = navigator.maxTouchPoints > 0;
  const platform = navigator.userAgentData?.platform || navigator.platform || (touch ? "Mobile" : "Browser");
  return `${platform} ${touch ? "Mobile" : "Browser"}`.slice(0, 64);
}

async function startPairing() {
  await closePeer(false);
  sessionToken = "";
  sessionRole = "view";
  requestId = "";
  clientNonce = randomToken(24);
  setStatus(t("requesting"), "warn");
  setMessage(t("requesting"));
  els.pairButton.disabled = true;
  try {
    const result = await jsonFetch("/api/pair", {
      body: {
        client_name: els.deviceName.value.trim() || defaultDeviceName(),
        role: els.requestedRole.value,
        client_nonce: clientNonce,
      },
    });
    requestId = result.request_id;
    setStatus(t("waiting"), "warn");
    setMessage(t("waiting"));
    pairPollTimer = setInterval(pollPairing, 1000);
    await pollPairing();
  } catch (error) {
    pairFailure(error);
  }
}

async function pollPairing() {
  if (!requestId || !clientNonce) return;
  try {
    const result = await jsonFetch("/api/pair/status", {
      body: { request_id: requestId, client_nonce: clientNonce },
    });
    if (result.status === "pending") return;
    clearInterval(pairPollTimer); pairPollTimer = null;
    if (result.status === "denied") {
      requestId = "";
      setStatus(t("disconnected"), "bad");
      setMessage(t("denied"));
      els.pairButton.disabled = false;
      return;
    }
    if (result.status === "approved") {
      requestId = "";
      sessionToken = result.session_token;
      sessionRole = result.role || "view";
      els.rolePill.textContent = sessionRole === "control" ? "CONTROL" : "VIEW";
      setStatus(t("approved"), "warn");
      setMessage(sessionRole === "control" ? t("approved") : `${t("approved")} ${t("viewOnly")}`);
      await connectRtc();
    }
  } catch (error) {
    if (error.code === "PAIR_REQUEST_NOT_FOUND" || error.code === "PAIR_REQUEST_EXPIRED") {
      clearInterval(pairPollTimer); pairPollTimer = null;
      requestId = "";
      setStatus(t("disconnected"), "bad");
      setMessage(t("expired"));
      els.pairButton.disabled = false;
    } else if (error.code === "RATE_LIMITED") {
      // Keep the existing polling interval. The host already applies a bounded
      // rate; this branch intentionally avoids an aggressive retry loop.
    } else {
      pairFailure(error);
    }
  }
}

function pairFailure(error) {
  if (pairPollTimer) clearInterval(pairPollTimer);
  pairPollTimer = null;
  requestId = "";
  setStatus(t("failed"), "bad");
  setMessage(`${t("failed")}: ${error?.code || error?.message || "UNKNOWN"}`);
  els.pairButton.disabled = false;
}

function waitForIceGatheringComplete(peer, timeoutMs = 8000) {
  if (peer.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    let finished = false;
    const done = () => {
      if (finished) return;
      finished = true;
      peer.removeEventListener("icegatheringstatechange", onChange);
      clearTimeout(timer);
      resolve();
    };
    const onChange = () => { if (peer.iceGatheringState === "complete") done(); };
    const timer = setTimeout(done, timeoutMs);
    peer.addEventListener("icegatheringstatechange", onChange);
  });
}

async function connectRtc() {
  if (!sessionToken) throw new Error("NO_SESSION");
  await closePeer(true);
  const grant = await jsonFetch("/api/peer-grant", { token: sessionToken });
  sessionRole = grant.role || sessionRole;
  els.modePill.textContent = String(grant.mode || "game").toUpperCase();
  pc = new RTCPeerConnection({
    iceServers: grant.iceServers || [],
    bundlePolicy: "max-bundle",
  });
  dc = pc.createDataChannel("kagelink-control", { ordered: true });
  pc.addTransceiver("video", { direction: "recvonly" });

  pc.addEventListener("track", (event) => {
    const stream = event.streams?.[0] || new MediaStream([event.track]);
    els.video.srcObject = stream;
  });
  pc.addEventListener("connectionstatechange", () => {
    const state = pc?.connectionState || "closed";
    if (state === "connected") {
      connected = true;
      setStatus(t("connected"), "ok");
      setMessage(sessionRole === "control" ? t("connected") : `${t("connected")} — ${t("viewOnly")}`);
      els.disconnectButton.disabled = false;
      els.pairButton.disabled = true;
      startTimers();
      setControlUi();
      els.stage.focus({ preventScroll: true });
    } else if (["failed", "closed"].includes(state)) {
      connected = false;
      stopTimers();
      setControlUi();
      if (sessionToken) {
        setStatus(t("failed"), "bad");
        els.pairButton.disabled = false;
        els.pairButton.textContent = t("reconnect");
      }
    } else if (state === "disconnected") {
      setStatus("Reconnecting…", "warn");
    }
  });

  dc.addEventListener("open", () => {
    send({ type: "heartbeat" });
    setControlUi();
  });
  dc.addEventListener("close", () => setControlUi());
  dc.addEventListener("message", (event) => {
    if (typeof event.data !== "string" || event.data.length > 4096) return;
    let payload;
    try { payload = JSON.parse(event.data); } catch (_) { return; }
    if (payload.type === "pong" && Number.isFinite(payload.t)) {
      const rtt = Math.max(0, performance.now() - payload.t);
      updateRtt(rtt);
    } else if (payload.type === "error") {
      if (payload.error === "CONTROL_DISABLED_BY_HOST") setMessage(t("controlDisabled"));
      else setMessage(`Host: ${String(payload.error || "ERROR").slice(0, 80)}`);
    }
  });

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  await waitForIceGatheringComplete(pc);
  const local = pc.localDescription;
  const answer = await jsonFetch("/api/rtc/offer", {
    body: { peer_grant: grant.peer_grant, sdp: local.sdp, type: local.type },
  });
  await pc.setRemoteDescription({ type: answer.type, sdp: answer.sdp });
  els.pairButton.textContent = t("reconnect");
}

async function reconnectExistingSession() {
  if (!sessionToken) return startPairing();
  els.pairButton.disabled = true;
  setStatus("Reconnecting…", "warn");
  try {
    await connectRtc();
  } catch (error) {
    if (["INVALID_SESSION", "SESSION_EXPIRED"].includes(error.code)) {
      sessionToken = "";
      await startPairing();
    } else {
      pairFailure(error);
    }
  }
}

function send(payload) {
  if (!dc || dc.readyState !== "open") return false;
  const raw = JSON.stringify(payload);
  if (raw.length > 4096) return false;
  dc.send(raw);
  return true;
}

function startTimers() {
  stopTimers();
  heartbeatTimer = setInterval(() => send({ type: "heartbeat" }), 2000);
  pingTimer = setInterval(() => send({ type: "ping", t: performance.now() }), 3000);
  statsTimer = setInterval(updateStats, 2000);
  send({ type: "heartbeat" });
}

function stopTimers() {
  for (const timer of [heartbeatTimer, pingTimer, statsTimer]) if (timer) clearInterval(timer);
  heartbeatTimer = pingTimer = statsTimer = null;
  lastStatsBytes = 0;
  lastStatsAt = 0;
}

async function closePeer(keepSession = false) {
  stopTimers();
  try { send({ type: "release_all" }); } catch (_) {}
  stickyModifiers.clear();
  document.querySelectorAll(".modifier").forEach((b) => b.classList.remove("active"));
  try { dc?.close(); } catch (_) {}
  try { pc?.close(); } catch (_) {}
  dc = null; pc = null; connected = false;
  els.video.srcObject = null;
  els.disconnectButton.disabled = true;
  setControlUi();
  if (!keepSession) {
    sessionToken = "";
    sessionRole = "view";
    els.pairButton.textContent = t("request");
    els.pairButton.disabled = false;
    setStatus(t("disconnected"), "");
    setMessage(t("disconnected"));
  }
}

function canonicalKey(event) {
  if (event.code === "Space") return "space";
  const key = String(event.key || "");
  if (/^[a-zA-Z]$/.test(key)) return key.toLowerCase();
  if (/^[0-9]$/.test(key)) return key;
  const map = {
    Enter: "enter", Escape: "escape", Tab: "tab", Shift: "shift", Control: "ctrl", Alt: "alt", Meta: "win",
    Backspace: "backspace", Insert: "insert", Delete: "delete", Home: "home", End: "end",
    PageUp: "pageup", PageDown: "pagedown", ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right",
  };
  if (map[key]) return map[key];
  if (/^F([1-9]|1[0-2])$/.test(key)) return key.toLowerCase();
  return "";
}

function canControl() { return connected && sessionRole === "control" && dc?.readyState === "open"; }

els.stage.addEventListener("keydown", (event) => {
  if (!canControl() || event.isComposing) return;
  const key = canonicalKey(event);
  if (!key) return;
  event.preventDefault();
  if (!event.repeat) send({ type: "key", key, down: true });
});
els.stage.addEventListener("keyup", (event) => {
  if (!canControl() || event.isComposing) return;
  const key = canonicalKey(event);
  if (!key) return;
  event.preventDefault();
  send({ type: "key", key, down: false });
});

function tapKey(key) {
  if (!canControl()) return;
  send({ type: "key", key, down: true });
  setTimeout(() => send({ type: "key", key, down: false }), 55);
}

document.querySelectorAll("#controlToolbar button[data-key]").forEach((button) => {
  button.addEventListener("click", () => {
    const key = button.dataset.key;
    if (!canControl()) return;
    if (button.classList.contains("modifier")) {
      if (stickyModifiers.has(key)) {
        stickyModifiers.delete(key);
        button.classList.remove("active");
        send({ type: "key", key, down: false });
      } else {
        stickyModifiers.add(key);
        button.classList.add("active");
        send({ type: "key", key, down: true });
      }
    } else {
      tapKey(key);
    }
  });
});

els.releaseButton.addEventListener("click", () => {
  stickyModifiers.clear();
  document.querySelectorAll(".modifier").forEach((b) => b.classList.remove("active"));
  send({ type: "release_all" });
});

els.keyboardButton.addEventListener("click", () => {
  if (!canControl()) return;
  els.ime.value = "";
  els.ime.focus({ preventScroll: true });
});
els.ime.addEventListener("compositionstart", () => { composing = true; });
els.ime.addEventListener("compositionend", (event) => {
  composing = false;
  if (event.data) send({ type: "text", text: event.data });
  els.ime.value = "";
});
els.ime.addEventListener("beforeinput", (event) => {
  if (!canControl() || composing) return;
  if (event.inputType === "deleteContentBackward") {
    event.preventDefault(); tapKey("backspace"); return;
  }
  if (event.inputType === "deleteContentForward") {
    event.preventDefault(); tapKey("delete"); return;
  }
  if (event.inputType?.startsWith("insert") && event.data) {
    event.preventDefault(); send({ type: "text", text: event.data }); els.ime.value = "";
  }
});
els.ime.addEventListener("input", () => {
  if (!canControl() || composing) return;
  const value = els.ime.value;
  if (value) send({ type: "text", text: value });
  els.ime.value = "";
});

function videoNormalizedPoint(clientX, clientY) {
  const rect = els.video.getBoundingClientRect();
  const sourceW = els.video.videoWidth || 16;
  const sourceH = els.video.videoHeight || 9;
  if (rect.width <= 0 || rect.height <= 0) return null;
  const scale = Math.min(rect.width / sourceW, rect.height / sourceH);
  const contentW = sourceW * scale;
  const contentH = sourceH * scale;
  const left = rect.left + (rect.width - contentW) / 2;
  const top = rect.top + (rect.height - contentH) / 2;
  const x = (clientX - left) / contentW;
  const y = (clientY - top) / contentH;
  if (x < 0 || x > 1 || y < 0 || y > 1) return null;
  return { x, y };
}

function pointerSend(clientX, clientY, action, button = "left") {
  if (!canControl()) return;
  const point = videoNormalizedPoint(clientX, clientY);
  if (!point) return;
  send({ type: "pointer", x: point.x, y: point.y, action, button });
}

function buttonName(event) {
  return event.button === 2 ? "right" : event.button === 1 ? "middle" : "left";
}

function cancelLongPress() {
  if (longPressTimer) clearTimeout(longPressTimer);
  longPressTimer = null;
}

function distance(a, b) { return Math.hypot(a.x - b.x, a.y - b.y); }
function midpoint(a, b) { return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }; }

function applyZoom() {
  zoom = Math.min(4, Math.max(1, zoom));
  if (zoom === 1) { panX = 0; panY = 0; }
  const maxX = els.stage.clientWidth * (zoom - 1) / 2;
  const maxY = els.stage.clientHeight * (zoom - 1) / 2;
  panX = Math.max(-maxX, Math.min(maxX, panX));
  panY = Math.max(-maxY, Math.min(maxY, panY));
  els.transform.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom})`;
}

els.stage.addEventListener("contextmenu", (event) => event.preventDefault());
els.stage.addEventListener("pointerdown", (event) => {
  els.stage.focus({ preventScroll: true });
  els.stage.setPointerCapture?.(event.pointerId);
  pointers.set(event.pointerId, { x: event.clientX, y: event.clientY, startX: event.clientX, startY: event.clientY, type: event.pointerType, moved: false });
  if (event.pointerType === "mouse") {
    event.preventDefault();
    pointerSend(event.clientX, event.clientY, "down", buttonName(event));
    return;
  }
  if (pointers.size === 1) {
    longPressFired = false;
    cancelLongPress();
    longPressTimer = setTimeout(() => {
      const current = pointers.get(event.pointerId);
      if (!current || current.moved || pointers.size !== 1) return;
      longPressFired = true;
      pointerSend(current.x, current.y, "down", "right");
      setTimeout(() => pointerSend(current.x, current.y, "up", "right"), 45);
    }, 600);
  } else if (pointers.size === 2) {
    cancelLongPress();
    const values = [...pointers.values()];
    touchGesture = {
      distance: Math.max(1, distance(values[0], values[1])),
      zoom,
      midpoint: midpoint(values[0], values[1]),
      panX,
      panY,
    };
  }
});

els.stage.addEventListener("pointermove", (event) => {
  const current = pointers.get(event.pointerId);
  if (!current) return;
  current.x = event.clientX; current.y = event.clientY;
  if (Math.hypot(current.x - current.startX, current.y - current.startY) > 5) {
    current.moved = true; cancelLongPress();
  }
  if (event.pointerType === "mouse") {
    event.preventDefault(); pointerSend(event.clientX, event.clientY, "move", buttonName(event)); return;
  }
  if (pointers.size >= 2 && touchGesture) {
    event.preventDefault();
    const values = [...pointers.values()].slice(0, 2);
    const currentDistance = Math.max(1, distance(values[0], values[1]));
    const currentMid = midpoint(values[0], values[1]);
    zoom = touchGesture.zoom * (currentDistance / touchGesture.distance);
    panX = touchGesture.panX + (currentMid.x - touchGesture.midpoint.x);
    panY = touchGesture.panY + (currentMid.y - touchGesture.midpoint.y);
    applyZoom();
    return;
  }
  if (pointers.size === 1 && current.moved) pointerSend(event.clientX, event.clientY, "move", "left");
});

function finishPointer(event) {
  const current = pointers.get(event.pointerId);
  if (!current) return;
  if (event.pointerType === "mouse") {
    event.preventDefault(); pointerSend(event.clientX, event.clientY, "up", buttonName(event));
  } else if (pointers.size === 1 && !current.moved && !longPressFired) {
    pointerSend(event.clientX, event.clientY, "down", "left");
    setTimeout(() => pointerSend(event.clientX, event.clientY, "up", "left"), 45);
  }
  pointers.delete(event.pointerId);
  cancelLongPress();
  longPressFired = false;
  if (pointers.size < 2) touchGesture = null;
}
els.stage.addEventListener("pointerup", finishPointer);
els.stage.addEventListener("pointercancel", finishPointer);

els.zoomOut.addEventListener("click", () => { zoom /= 1.25; applyZoom(); });
els.zoomIn.addEventListener("click", () => { zoom *= 1.25; applyZoom(); });
els.zoomFit.addEventListener("click", () => { zoom = 1; panX = 0; panY = 0; applyZoom(); });

function updateRtt(value) {
  const text = `${Math.round(value)} ms`;
  els.rttValue.textContent = text; els.rttBadge.textContent = `RTT ${text}`;
}

async function updateStats() {
  if (!pc) return;
  try {
    const reports = await pc.getStats();
    let video = null;
    reports.forEach((report) => {
      if (report.type === "inbound-rtp" && report.kind === "video" && !report.isRemote) video = report;
    });
    if (!video) return;
    const now = performance.now();
    const fps = Number(video.framesPerSecond || 0);
    const bytes = Number(video.bytesReceived || 0);
    let bitrate = 0;
    if (lastStatsAt && bytes >= lastStatsBytes) bitrate = ((bytes - lastStatsBytes) * 8) / ((now - lastStatsAt) / 1000) / 1_000_000;
    lastStatsBytes = bytes; lastStatsAt = now;
    const lost = Math.max(0, Number(video.packetsLost || 0));
    const received = Math.max(0, Number(video.packetsReceived || 0));
    const loss = (lost + received) > 0 ? (lost / (lost + received)) * 100 : 0;
    els.fpsValue.textContent = fps ? fps.toFixed(0) : "—";
    els.bitrateValue.textContent = bitrate ? `${bitrate.toFixed(2)} Mbps` : "—";
    els.lossValue.textContent = `${loss.toFixed(2)}%`;
    els.fpsBadge.textContent = `FPS ${fps ? fps.toFixed(0) : "—"}`;
    els.bitrateBadge.textContent = bitrate ? `${bitrate.toFixed(2)} Mbps` : "0 Mbps";
    els.lossBadge.textContent = `Loss ${loss.toFixed(2)}%`;
  } catch (_) {}
}

els.pairButton.addEventListener("click", () => sessionToken ? reconnectExistingSession() : startPairing());
els.disconnectButton.addEventListener("click", () => closePeer(false));
els.languageButton.addEventListener("click", () => { lang = lang === "pt-BR" ? "en-US" : "pt-BR"; applyLanguage(); });
window.addEventListener("beforeunload", () => { try { send({ type: "release_all" }); } catch (_) {} });

els.deviceName.value = defaultDeviceName();
applyLanguage();
applyZoom();
setControlUi();
