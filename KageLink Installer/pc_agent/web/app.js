const state = {
  token: localStorage.getItem('shinobi_remote_token') || '',
  ws: null,
  reconnectTimer: null,
  reconnectDelay: 1000,
  messages: new Map(),
  deferredInstall: null,
  authenticated: false,
};

const $ = (selector) => document.querySelector(selector);
const loginScreen = $('#login-screen');
const appShell = $('#app-shell');
const tokenInput = $('#token-input');
const loginButton = $('#login-button');
const loginError = $('#login-error');
const chatList = $('#chat-list');
const composer = $('#composer');
const messageInput = $('#message-input');
const sendButton = $('#send-button');
const connectionDot = $('#connection-dot');
const connectionLabel = $('#connection-label');
const gameLabel = $('#game-label');
const jumpBottom = $('#jump-bottom');
const settingsDialog = $('#settings-dialog');
const candidateList = $('#candidate-list');
const installButton = $('#install-button');
const toast = $('#toast');

function showToast(message, type = '') {
  toast.textContent = message;
  toast.className = `toast ${type}`.trim();
  toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { toast.hidden = true; }, 3600);
}

function apiHeaders() {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${state.token}`,
  };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...apiHeaders(), ...(options.headers || {}) },
  });

  let payload = {};
  try { payload = await response.json(); } catch (_) {}

  if (response.status === 401) {
    logout(false);
    throw new Error('Token inválido ou sessão expirada.');
  }
  if (!response.ok) {
    throw new Error(payload.detail || `Erro HTTP ${response.status}`);
  }
  return payload;
}

async function authenticate(token) {
  const response = await fetch('/api/auth', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });
  if (!response.ok) throw new Error('Token inválido.');
}

async function login() {
  const token = tokenInput.value.trim();
  loginError.hidden = true;
  loginButton.disabled = true;
  try {
    await authenticate(token);
    state.token = token;
    state.authenticated = true;
    localStorage.setItem('shinobi_remote_token', token);
    loginScreen.hidden = true;
    appShell.hidden = false;
    await loadHistory();
    connectWebSocket();
    await refreshStatus();
  } catch (error) {
    loginError.textContent = error.message;
    loginError.hidden = false;
  } finally {
    loginButton.disabled = false;
  }
}

function logout(showMessage = true) {
  state.authenticated = false;
  state.token = '';
  localStorage.removeItem('shinobi_remote_token');
  if (state.ws) state.ws.close();
  clearTimeout(state.reconnectTimer);
  appShell.hidden = true;
  loginScreen.hidden = false;
  tokenInput.value = '';
  if (settingsDialog.open) settingsDialog.close();
  if (showMessage) showToast('Sessão encerrada.');
}

function isNearBottom() {
  return chatList.scrollHeight - chatList.scrollTop - chatList.clientHeight < 110;
}

function scrollToBottom(force = false) {
  if (force || isNearBottom()) {
    chatList.scrollTop = chatList.scrollHeight;
    jumpBottom.hidden = true;
  } else {
    jumpBottom.hidden = false;
  }
}

function scrollToBottomAfterLayout() {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => scrollToBottom(true));
  });
}

function formatTime(isoString) {
  try {
    return new Intl.DateTimeFormat('pt-BR', {
      hour: '2-digit', minute: '2-digit',
    }).format(new Date(isoString));
  } catch (_) {
    return '';
  }
}

function renderEmptyState() {
  if (state.messages.size !== 0) return;
  chatList.innerHTML = '<div class="empty-state"><div><strong>Nenhuma mensagem armazenada.</strong><br>As novas linhas do chat aparecerão aqui.</div></div>';
}

function appendMessage(message, forceBottom = false) {
  if (!message || state.messages.has(message.id)) return;
  const wasNearBottom = isNearBottom();
  state.messages.set(message.id, message);

  const empty = chatList.querySelector('.empty-state');
  if (empty) empty.remove();

  const row = document.createElement('article');
  row.className = `message-row ${message.direction === 'outgoing' ? 'outgoing' : 'incoming'}`;
  row.dataset.id = String(message.id);

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';

  const text = document.createElement('div');
  text.className = 'message-text';
  text.textContent = message.text;

  const meta = document.createElement('div');
  meta.className = 'message-meta';
  meta.textContent = `${message.direction === 'outgoing' ? 'Enviado' : 'Recebido'} · ${formatTime(message.timestamp)}`;

  bubble.append(text, meta);
  row.appendChild(bubble);
  chatList.appendChild(row);

  if (forceBottom || wasNearBottom) scrollToBottom(true);
  else jumpBottom.hidden = false;
}

async function loadHistory() {
  state.messages.clear();
  chatList.innerHTML = '';
  const payload = await api('/api/history?limit=800');
  for (const message of payload.messages) appendMessage(message, false);
  renderEmptyState();
  scrollToBottomAfterLayout();
}

function updateStatus(status) {
  if (!status) return;
  if (!navigator.onLine || !state.ws || state.ws.readyState !== WebSocket.OPEN) {
    connectionDot.className = 'status-dot offline';
    connectionLabel.textContent = 'Desconectado';
  } else if (status.game_online && status.chat_found && status.input_found) {
    connectionDot.className = 'status-dot online';
    connectionLabel.textContent = 'Conectado';
  } else {
    connectionDot.className = 'status-dot warning';
    connectionLabel.textContent = 'Atenção';
  }

  if (!status.game_online) gameLabel.textContent = 'Jogo não localizado';
  else if (!status.chat_found) gameLabel.textContent = 'Chat não localizado';
  else if (!status.input_found) gameLabel.textContent = 'Campo de envio não localizado';
  else gameLabel.textContent = 'Leitura e envio disponíveis';
}

async function refreshStatus() {
  try {
    const status = await api('/api/status');
    updateStatus(status);
  } catch (error) {
    showToast(error.message, 'error');
  }
}

function connectWebSocket() {
  if (!state.authenticated) return;
  clearTimeout(state.reconnectTimer);
  if (state.ws) {
    state.ws.onclose = null;
    state.ws.close();
  }

  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${location.host}/ws?token=${encodeURIComponent(state.token)}`;
  state.ws = new WebSocket(url);

  state.ws.onopen = () => {
    state.reconnectDelay = 1000;
    connectionDot.className = 'status-dot online';
    connectionLabel.textContent = 'Conectado';
    state.ws.pingTimer = setInterval(() => {
      if (state.ws?.readyState === WebSocket.OPEN) state.ws.send('ping');
    }, 20000);
  };

  state.ws.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === 'message') appendMessage(payload.message);
    if (payload.type === 'status') updateStatus(payload.status);
    if (payload.type === 'error') showToast(payload.message, 'error');
  };

  state.ws.onclose = () => {
    clearInterval(state.ws?.pingTimer);
    connectionDot.className = 'status-dot offline';
    connectionLabel.textContent = 'Reconectando…';
    if (state.authenticated) {
      state.reconnectTimer = setTimeout(connectWebSocket, state.reconnectDelay);
      state.reconnectDelay = Math.min(state.reconnectDelay * 1.7, 15000);
    }
  };
}

async function sendMessage(event) {
  event.preventDefault();
  const message = messageInput.value.replace(/\s+/g, ' ').trim();
  if (!message) return;

  sendButton.disabled = true;
  messageInput.disabled = true;
  try {
    const payload = await api('/api/send', {
      method: 'POST',
      body: JSON.stringify({ message }),
    });
    appendMessage(payload.message, true);
    messageInput.value = '';
    autoResizeComposer();
    scrollToBottom(true);
  } catch (error) {
    showToast(error.message, 'error');
  } finally {
    sendButton.disabled = false;
    messageInput.disabled = false;
    messageInput.focus();
  }
}

function autoResizeComposer() {
  messageInput.style.height = 'auto';
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 130)}px`;
}

async function refreshCandidates() {
  candidateList.innerHTML = '<div class="candidate-meta">Buscando controles Edit…</div>';
  try {
    const payload = await api('/api/input-candidates');
    candidateList.innerHTML = '';
    if (!payload.candidates.length) {
      candidateList.innerHTML = '<div class="candidate-meta">Nenhum campo Edit visível foi encontrado.</div>';
      return;
    }

    for (const candidate of payload.candidates) {
      const selected = candidate.width === payload.preferred_width && candidate.height === payload.preferred_height;
      const card = document.createElement('div');
      card.className = `candidate-card ${selected ? 'selected' : ''}`;
      card.innerHTML = `
        <div>
          <div class="candidate-title">${candidate.width} × ${candidate.height}</div>
          <div class="candidate-meta">HWND ${candidate.hwnd} · posição ${candidate.left}, ${candidate.top}</div>
        </div>
      `;
      const button = document.createElement('button');
      button.className = 'candidate-select';
      button.textContent = selected ? 'Selecionado' : 'Usar';
      button.disabled = selected;
      button.addEventListener('click', async () => {
        try {
          await api('/api/input-preference', {
            method: 'POST',
            body: JSON.stringify({ width: candidate.width, height: candidate.height }),
          });
          showToast(`Campo ${candidate.width}×${candidate.height} selecionado.`, 'success');
          await refreshCandidates();
          await refreshStatus();
        } catch (error) {
          showToast(error.message, 'error');
        }
      });
      card.appendChild(button);
      candidateList.appendChild(card);
    }
  } catch (error) {
    candidateList.innerHTML = `<div class="error-text">${error.message}</div>`;
  }
}

window.addEventListener('beforeinstallprompt', (event) => {
  event.preventDefault();
  state.deferredInstall = event;
  installButton.hidden = false;
});

installButton.addEventListener('click', async () => {
  if (!state.deferredInstall) return;
  state.deferredInstall.prompt();
  await state.deferredInstall.userChoice;
  state.deferredInstall = null;
  installButton.hidden = true;
});

loginButton.addEventListener('click', login);
tokenInput.addEventListener('keydown', (event) => { if (event.key === 'Enter') login(); });
composer.addEventListener('submit', sendMessage);
messageInput.addEventListener('input', autoResizeComposer);
messageInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    composer.requestSubmit();
  }
});
chatList.addEventListener('scroll', () => { if (isNearBottom()) jumpBottom.hidden = true; });
jumpBottom.addEventListener('click', () => scrollToBottom(true));
$('#settings-button').addEventListener('click', async () => {
  settingsDialog.showModal();
  await refreshCandidates();
});
$('#close-settings').addEventListener('click', () => settingsDialog.close());
$('#refresh-candidates').addEventListener('click', refreshCandidates);
$('#logout-button').addEventListener('click', () => logout());

window.addEventListener('online', connectWebSocket);
window.addEventListener('offline', () => updateStatus({}));

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/service-worker.js').catch(() => {}));
}

(async function boot() {
  tokenInput.value = state.token;
  if (!state.token) return;
  try {
    await authenticate(state.token);
    state.authenticated = true;
    loginScreen.hidden = true;
    appShell.hidden = false;
    await loadHistory();
    connectWebSocket();
    await refreshStatus();
  } catch (_) {
    logout(false);
  }
})();
