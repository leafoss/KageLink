"use strict";

const $ = (id) => document.getElementById(id);
let lang = (navigator.language || "pt-BR").toLowerCase().startsWith("pt") ? "pt-BR" : "en-US";
let adminToken = "";
let lastState = null;

const I18N = {
  "pt-BR": {
    loading: "Carregando…", online: "Host ativo", unauthorized: "Admin local não autorizado. Abra esta página pelo link mostrado no console do Host.",
    pendingTitle: "Solicitações pendentes", pendingHelp: "Aprove apenas dispositivos que você reconhece. Controle e visualização são permissões separadas.",
    sessionsTitle: "Sessões ativas", sessionsHelp: "Apenas um controlador pode existir por vez. Sessões expiram automaticamente.",
    connectionTitle: "Conexão", localLabel: "Endereço local", externalLabel: "Endereço externo", pairingNote: "Não existe chave permanente. O navegador remoto cria uma solicitação que precisa ser aprovada aqui.",
    diagTitle: "Diagnóstico", enable: "Habilitar controle", emergency: "PARAR CONTROLE", stopped: "Controle remoto bloqueado localmente.",
    noPending: "Nenhuma solicitação pendente.", noSessions: "Nenhuma sessão ativa.", approveControl: "Aprovar controle", approveView: "Aprovar visualização", deny: "Negar", disconnect: "Desconectar",
    requested: "Solicitado", expires: "expira em", role: "Permissão", idle: "inativo", externalWaiting: "Aguardando túnel…", view: "visualização", control: "controle",
  },
  "en-US": {
    loading: "Loading…", online: "Host active", unauthorized: "Local Admin is not authorized. Open this page using the link shown by the Host console.",
    pendingTitle: "Pending requests", pendingHelp: "Approve only devices you recognize. Control and view are separate permissions.",
    sessionsTitle: "Active sessions", sessionsHelp: "Only one controller can exist at a time. Sessions expire automatically.",
    connectionTitle: "Connection", localLabel: "Local address", externalLabel: "External address", pairingNote: "There is no permanent access key. The remote browser creates a request that must be approved here.",
    diagTitle: "Diagnostics", enable: "Enable control", emergency: "STOP CONTROL", stopped: "Remote control is locally blocked.",
    noPending: "No pending requests.", noSessions: "No active sessions.", approveControl: "Approve control", approveView: "Approve view", deny: "Deny", disconnect: "Disconnect",
    requested: "Requested", expires: "expires in", role: "Role", idle: "idle", externalWaiting: "Waiting for tunnel…", view: "view", control: "control",
  },
};
const t = (key) => I18N[lang][key] || key;

function applyLanguage() {
  document.documentElement.lang = lang;
  $("languageButton").textContent = lang === "pt-BR" ? "EN" : "PT";
  $("pendingTitle").textContent = t("pendingTitle");
  $("pendingHelp").textContent = t("pendingHelp");
  $("sessionsTitle").textContent = t("sessionsTitle");
  $("sessionsHelp").textContent = t("sessionsHelp");
  $("connectionTitle").textContent = t("connectionTitle");
  $("localLabel").textContent = t("localLabel");
  $("externalLabel").textContent = t("externalLabel");
  $("pairingNote").textContent = t("pairingNote");
  $("diagTitle").textContent = t("diagTitle");
  $("enableInputButton").textContent = t("enable");
  $("emergencyButton").textContent = t("emergency");
  $("emergencyBanner").textContent = t("stopped");
  if (lastState) render(lastState);
}

function extractAdminToken() {
  adminToken = decodeURIComponent((location.hash || "").replace(/^#/, ""));
  if (adminToken) history.replaceState(null, "", location.pathname + location.search);
}

async function api(path, { method = "GET", body = null } = {}) {
  const headers = { "X-KageLink-Admin": adminToken };
  if (body !== null) headers["Content-Type"] = "application/json";
  const response = await fetch(path, {
    method,
    cache: "no-store",
    credentials: "same-origin",
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

function textNode(tag, text, className = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = text;
  return node;
}

function button(text, className, onClick, disabled = false) {
  const node = document.createElement("button");
  node.type = "button";
  node.textContent = text;
  node.className = className;
  node.disabled = disabled;
  node.addEventListener("click", onClick);
  return node;
}

function renderPending(state) {
  const list = $("pendingList");
  list.replaceChildren();
  if (!state.pending?.length) {
    list.append(textNode("div", t("noPending"), "message muted"));
    return;
  }
  for (const item of state.pending) {
    const card = document.createElement("div"); card.className = "list-item";
    card.append(textNode("div", item.client_name || "Browser", "title"));
    card.append(textNode("div", `${item.ip || "?"} · ${t("requested")}: ${t(item.requested_role)} · ${t("expires")} ${item.expires_in}s`, "meta"));
    card.append(textNode("div", item.user_agent || "", "meta"));
    const actions = document.createElement("div"); actions.className = "actions";
    actions.append(
      button(t("approveControl"), "good", () => decide("/api/approve", { request_id: item.request_id, role: "control" }), !state.control_allowed_by_cli),
      button(t("approveView"), "primary", () => decide("/api/approve", { request_id: item.request_id, role: "view" })),
      button(t("deny"), "danger", () => decide("/api/deny", { request_id: item.request_id })),
    );
    card.append(actions); list.append(card);
  }
}

function renderSessions(state) {
  const list = $("sessionList");
  list.replaceChildren();
  if (!state.sessions?.length) {
    list.append(textNode("div", t("noSessions"), "message muted"));
    return;
  }
  for (const session of state.sessions) {
    const card = document.createElement("div"); card.className = "list-item";
    card.append(textNode("div", `${session.client_name || "Browser"} — ${t(session.role)}`, "title"));
    card.append(textNode("div", `${session.ip || "?"} · ${t("idle")}: ${session.idle_seconds}s · TTL ${session.idle_expires_in}s`, "meta"));
    const actions = document.createElement("div"); actions.className = "actions";
    actions.append(button(t("disconnect"), "danger", () => decide("/api/disconnect", { session_id: session.session_id })));
    card.append(actions); list.append(card);
  }
}

function render(state) {
  lastState = state;
  $("hostStatus").textContent = t("online");
  $("hostDot").className = "status-dot ok";
  $("hostMode").textContent = `${String(state.mode || "?").toUpperCase()} · ${state.control_enabled ? "CONTROL ON" : "CONTROL OFF"}`;
  $("localUrl").textContent = state.local_url || "—";
  $("externalUrl").textContent = state.external_url || t("externalWaiting");
  $("captureFps").textContent = state.capture?.fps ?? "—";
  $("captureMs").textContent = Number.isFinite(state.capture?.capture_ms) ? `${state.capture.capture_ms} ms` : "—";
  $("frameAge").textContent = Number.isFinite(state.capture?.frame_age_ms) ? `${state.capture.frame_age_ms} ms` : "—";
  $("captureState").textContent = state.capture?.state || "—";
  $("emergencyBanner").classList.toggle("visible", Boolean(state.emergency_latched));
  $("enableInputButton").disabled = !state.control_allowed_by_cli || state.control_enabled;
  renderPending(state); renderSessions(state);
}

async function decide(path, body) {
  try {
    await api(path, { method: "POST", body });
    await refresh();
  } catch (error) {
    alert(`KageLink: ${error.code || error.message}`);
  }
}

async function refresh() {
  if (!adminToken) {
    $("hostStatus").textContent = t("unauthorized");
    $("hostDot").className = "status-dot bad";
    return;
  }
  try {
    const state = await api("/api/state");
    render(state);
  } catch (error) {
    $("hostStatus").textContent = error.code === "ADMIN_UNAUTHORIZED" ? t("unauthorized") : String(error.code || error.message);
    $("hostDot").className = "status-dot bad";
  }
}

$("emergencyButton").addEventListener("click", () => decide("/api/emergency-stop", {}));
$("enableInputButton").addEventListener("click", () => decide("/api/enable-input", {}));
$("languageButton").addEventListener("click", () => { lang = lang === "pt-BR" ? "en-US" : "pt-BR"; applyLanguage(); });

extractAdminToken();
applyLanguage();
refresh();
setInterval(refresh, 1000);
