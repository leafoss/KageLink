from __future__ import annotations

import ctypes
import hashlib
import importlib
import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import traceback
import time
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, BooleanVar, Button, Entry, Frame, Label, Menu, StringVar, Tk, Toplevel, messagebox, ttk

from pc_agent.config import CONFIG_PATH, PROJECT_DIR, ensure_config, load_config, update_server_port, update_user_settings
from pc_agent.logging_setup import configure_logging


APP_TITLE = "KageLink PC Agent"
MUTEX_NAME = "Local\\KageLinkPcAgent_v3"
CLOUDFLARED_VERSION = "2026.7.2"
CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/download/2026.7.2/cloudflared-windows-amd64.exe"
CLOUDFLARED_SHA256 = "cdb5d4432f6ae1595654a692a51308b69d2bf7af961f5578d9391837cf072df9"
URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)
_MUTEX_HANDLE: int | None = None



def _ensure_standard_streams() -> None:
    """Provide safe streams when PyInstaller runs without a console."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8", buffering=1)
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8", buffering=1)

TEXT = {
    "pt-BR": {
        "agent": "AGENTE", "game": "JOGO", "chat": "CHAT", "input": "ENTRADA", "tunnel": "CONEXÃO EXTERNA",
        "starting": "INICIANDO", "active": "ATIVO", "located": "LOCALIZADO", "not_located": "NÃO LOCALIZADO",
        "ready": "PRONTA", "unavailable": "INDISPONÍVEL", "connected": "ATIVA", "error": "ERRO",
        "external": "Endereço externo recomendado", "local": "Endereço local", "token": "Chave de acesso",
        "copy_address": "Copiar endereço", "copy_token": "Copiar chave", "copy_both": "Copiar ambos",
        "open_file": "Abrir informações", "restart_tunnel": "Reiniciar conexão", "settings": "Configurações",
        "open_folder": "Abrir pasta", "close": "Encerrar KageLink", "waiting": "Aguardando conexão segura...",
        "download": "Baixando o conector seguro da Cloudflare...", "server_error": "Não foi possível iniciar o servidor local.",
        "tunnel_error": "Não foi possível criar a conexão externa. Consulte logs\\kagelink.log.",
        "close_confirm": "Encerrar o KageLink e a conexão externa?", "copied": "Copiado para a área de transferência.",
        "restart_needed": "As configurações foram salvas. O KageLink será reiniciado.",
        "open_logs": "Abrir logs", "retry": "Tentar novamente",
        "port_changed": "A porta {old} estava ocupada. O KageLink mudou automaticamente para {new}.",
        "backend_starting": "Iniciando servidor interno...",
        "backend_active_game_missing": "Agente ativo. Abra o Shinobi Story Online. Se ele já estiver aberto, consulte logs\\kagelink.log.",
        "backend_failed": "O servidor interno falhou. Use Abrir logs e envie o arquivo kagelink.log.",
    },
    "en-US": {
        "agent": "AGENT", "game": "GAME", "chat": "CHAT", "input": "INPUT", "tunnel": "EXTERNAL CONNECTION",
        "starting": "STARTING", "active": "ACTIVE", "located": "LOCATED", "not_located": "NOT LOCATED",
        "ready": "READY", "unavailable": "UNAVAILABLE", "connected": "ACTIVE", "error": "ERROR",
        "external": "Recommended external address", "local": "Local address", "token": "Access key",
        "copy_address": "Copy address", "copy_token": "Copy key", "copy_both": "Copy both",
        "open_file": "Open connection info", "restart_tunnel": "Restart connection", "settings": "Settings",
        "open_folder": "Open folder", "close": "Exit KageLink", "waiting": "Waiting for secure connection...",
        "download": "Downloading the secure Cloudflare connector...", "server_error": "The local server could not be started.",
        "tunnel_error": "The external connection could not be created. Check logs\\kagelink.log.",
        "close_confirm": "Exit KageLink and close the external connection?", "copied": "Copied to the clipboard.",
        "restart_needed": "Settings were saved. KageLink will restart.",
        "open_logs": "Open logs", "retry": "Try again",
        "port_changed": "Port {old} was occupied. KageLink automatically changed to {new}.",
        "backend_starting": "Starting internal server...",
        "backend_active_game_missing": "Agent active. Open Shinobi Story Online. If it is already open, check logs\\kagelink.log.",
        "backend_failed": "The internal server failed. Use Open logs and send kagelink.log.",
    },
}


def already_running() -> bool:
    global _MUTEX_HANDLE
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _MUTEX_HANDLE = int(kernel32.CreateMutexW(None, False, MUTEX_NAME) or 0)
    if ctypes.get_last_error() != 183:
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        hwnd = user32.FindWindowW(None, APP_TITLE)
        if hwnd:
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
    release_mutex()
    return True


def release_mutex() -> None:
    global _MUTEX_HANDLE
    if not _MUTEX_HANDLE:
        return
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle(ctypes.c_void_p(_MUTEX_HANDLE))
    except Exception:
        pass
    _MUTEX_HANDLE = None


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


class FirstRunWizard:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.result: tuple[str, int] | None = None
        self.window = Toplevel(root)
        self.window.title("KageLink — First Run / Primeira execução")
        self.window.geometry("560x390")
        self.window.resizable(False, False)
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)

        # Do not make the wizard transient to a withdrawn root window.
        # On some Windows systems that makes the first-run wizard invisible.
        self.window.update_idletasks()
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        x = max(0, (screen_width - 560) // 2)
        y = max(0, (screen_height - 390) // 2)
        self.window.geometry(f"560x390+{x}+{y}")
        self.window.deiconify()
        self.window.lift()
        try:
            self.window.attributes("-topmost", True)
            self.window.after(900, lambda: self.window.attributes("-topmost", False))
        except Exception:
            pass
        self.window.after(120, self.window.focus_force)
        self.window.grab_set()
        self.language = StringVar(value="pt-BR")
        self.port = StringVar(value="8765")
        self.page = 0
        self.content = Frame(self.window, bg="#101621")
        self.content.pack(fill=BOTH, expand=True, padx=18, pady=18)
        nav = Frame(self.window, bg="#0b0e12")
        nav.pack(fill=X, side="bottom")
        self.back = Button(nav, text="◀", width=8, command=self.previous)
        self.back.pack(side=LEFT, padx=12, pady=10)
        self.next = Button(nav, text="Continuar / Continue", command=self.advance)
        self.next.pack(side=RIGHT, padx=12, pady=10)
        self.render()

    def tr(self, pt: str, en: str) -> str:
        return pt if self.language.get() == "pt-BR" else en

    def render(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()
        self.back.configure(state="normal" if self.page > 0 else "disabled")
        pages = [self.page_language, self.page_port, self.page_security, self.page_tunnel, self.page_finish]
        pages[self.page]()
        self.next.configure(text=self.tr("Concluir", "Finish") if self.page == 4 else self.tr("Continuar", "Continue"))

    def title(self, text: str) -> None:
        Label(self.content, text=text, bg="#101621", fg="#41d9e8", font=("Segoe UI", 19, "bold")).pack(pady=(15, 18))

    def paragraph(self, text: str) -> None:
        Label(self.content, text=text, bg="#101621", fg="#f3eee5", font=("Segoe UI", 11), wraplength=480, justify="left").pack(padx=18, pady=8, anchor="w")

    def page_language(self) -> None:
        self.title("Idioma / Language")
        self.paragraph("Escolha o idioma da interface do agente. / Choose the PC agent interface language.")
        ttk.Radiobutton(self.content, text="Português do Brasil", variable=self.language, value="pt-BR", command=self.render).pack(anchor="w", padx=36, pady=8)
        ttk.Radiobutton(self.content, text="English", variable=self.language, value="en-US", command=self.render).pack(anchor="w", padx=36, pady=8)

    def page_port(self) -> None:
        self.title(self.tr("Porta do servidor", "Server port"))
        self.paragraph(self.tr("A porta padrão 8765 funciona para a maioria dos usuários.", "The default port 8765 works for most users."))
        Entry(self.content, textvariable=self.port, justify="center", font=("Consolas", 16), width=10).pack(pady=18)

    def page_security(self) -> None:
        self.title(self.tr("Segurança", "Security"))
        self.paragraph(self.tr("Uma chave de acesso única e criptograficamente segura será criada automaticamente e preservada nas próximas atualizações.", "A unique, cryptographically secure access key will be created automatically and preserved during future updates."))

    def page_tunnel(self) -> None:
        self.title(self.tr("Conexão externa segura", "Secure external connection"))
        self.paragraph(self.tr("Ao abrir o KageLink, o servidor local e um túnel HTTPS da Cloudflare serão iniciados automaticamente. Nenhuma porta pública será aberta no roteador.", "When KageLink starts, the local server and a Cloudflare HTTPS tunnel will start automatically. No public router port will be opened."))

    def page_finish(self) -> None:
        self.title(self.tr("Tudo pronto", "Ready"))
        self.paragraph(self.tr("Clique em Concluir. O KageLink criará a configuração, iniciará o agente e mostrará o endereço e a chave para o aplicativo.", "Click Finish. KageLink will create its configuration, start the agent, and show the address and key for the mobile app."))

    def previous(self) -> None:
        self.page = max(0, self.page - 1)
        self.render()

    def advance(self) -> None:
        if self.page == 1:
            try:
                value = int(self.port.get().strip())
                if not 1024 <= value <= 65535:
                    raise ValueError
            except ValueError:
                messagebox.showerror("KageLink", self.tr("Informe uma porta entre 1024 e 65535.", "Enter a port between 1024 and 65535."), parent=self.window)
                return
        if self.page < 4:
            self.page += 1
            self.render()
            return
        self.result = (self.language.get(), int(self.port.get()))
        self.window.destroy()

    def cancel(self) -> None:
        self.result = None
        self.window.destroy()

    def show(self) -> tuple[str, int] | None:
        self.root.wait_window(self.window)
        return self.result


class KageLinkAgentUI:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("760x590")
        self.root.minsize(680, 540)
        self.root.configure(bg="#0b0e12")
        self.root.protocol("WM_DELETE_WINDOW", self.request_close)
        self.logger = configure_logging()
        self.config = load_config()
        self.lang = self.config.ui_language
        self.t = TEXT[self.lang]
        self.server = None
        self.server_thread: threading.Thread | None = None
        self.tunnel_process: subprocess.Popen[str] | None = None
        self.tunnel_thread: threading.Thread | None = None
        self.external_url = ""
        self.local_url = f"http://{local_ip()}:{self.config.port}"
        self.stopping = False
        self.runtime_status = None

        self.agent_var = StringVar(value=self.t["starting"])
        self.game_var = StringVar(value=self.t["not_located"])
        self.chat_var = StringVar(value=self.t["not_located"])
        self.input_var = StringVar(value=self.t["unavailable"])
        self.tunnel_var = StringVar(value=self.t["starting"])
        self.external_var = StringVar(value=self.t["waiting"])
        self.local_var = StringVar(value=self.local_url)
        self.token_var = StringVar(value=self.config.access_token)
        self.message_var = StringVar(value="")
        self._build_ui()
        self._write_connection_file()
        self.root.after(300, self._poll_runtime)
        threading.Thread(target=self._startup_sequence, name="Startup", daemon=True).start()

    def _build_ui(self) -> None:
        header = Frame(self.root, bg="#141922", padx=22, pady=18)
        header.pack(fill=X)
        Label(header, text="KageLink", bg="#141922", fg="#41d9e8", font=("Segoe UI", 25, "bold")).pack(side=LEFT)
        Label(header, text="PC Agent", bg="#141922", fg="#e8d6b3", font=("Segoe UI", 13, "bold")).pack(side=LEFT, padx=(10, 0), pady=(8, 0))

        statuses = Frame(self.root, bg="#0b0e12", padx=18, pady=15)
        statuses.pack(fill=X)
        for key, variable in [("agent", self.agent_var), ("game", self.game_var), ("chat", self.chat_var), ("input", self.input_var), ("tunnel", self.tunnel_var)]:
            box = Frame(statuses, bg="#1b2430", padx=10, pady=8, highlightbackground="#2b3b4f", highlightthickness=1)
            box.pack(side=LEFT, expand=True, fill=X, padx=4)
            Label(box, text=self.t[key], bg="#1b2430", fg="#b7bcc6", font=("Segoe UI", 8, "bold")).pack()
            Label(box, textvariable=variable, bg="#1b2430", fg="#41d9e8", font=("Segoe UI", 9, "bold"), wraplength=120).pack(pady=(4, 0))

        panel = Frame(self.root, bg="#141922", padx=22, pady=18, highlightbackground="#39485d", highlightthickness=1)
        panel.pack(fill=BOTH, expand=True, padx=22, pady=(4, 12))
        self._field(panel, self.t["external"], self.external_var, True)
        self._field(panel, self.t["local"], self.local_var, False)
        self._field(panel, self.t["token"], self.token_var, False)

        actions = Frame(panel, bg="#141922")
        actions.pack(fill=X, pady=(16, 4))
        for label, command in [
            (self.t["copy_address"], lambda: self.copy(self.external_url)),
            (self.t["copy_token"], lambda: self.copy(self.config.access_token)),
            (self.t["copy_both"], self.copy_both),
            (self.t["open_file"], self.open_connection_file),
        ]:
            Button(actions, text=label, command=command, bg="#1b4d80", fg="white", activebackground="#3188d8", relief="flat", padx=12, pady=8).pack(side=LEFT, padx=4)

        secondary = Frame(panel, bg="#141922")
        secondary.pack(fill=X, pady=8)
        for label, command in [
            (self.t["restart_tunnel"], self.restart_tunnel),
            (self.t["retry"], self.retry_startup),
            (self.t["open_logs"], self.open_logs),
            (self.t["settings"], self.open_settings),
            (self.t["open_folder"], lambda: os.startfile(PROJECT_DIR)),
            (self.t["close"], self.request_close),
        ]:
            Button(
                secondary,
                text=label,
                command=command,
                bg="#2a303a",
                fg="#f3eee5",
                activebackground="#3b4655",
                relief="flat",
                padx=10,
                pady=7,
            ).pack(side=LEFT, padx=3)

        diagnostic = Frame(
            panel,
            bg="#261b16",
            padx=12,
            pady=9,
            highlightbackground="#8b5e34",
            highlightthickness=1,
        )
        diagnostic.pack(fill=X, pady=(9, 0))
        Label(
            diagnostic,
            textvariable=self.message_var,
            bg="#261b16",
            fg="#f2b66d",
            font=("Segoe UI", 9, "bold"),
            wraplength=650,
            justify="left",
            anchor="w",
        ).pack(fill=X)

    def _field(self, parent: Frame, title: str, variable: StringVar, highlight: bool) -> None:
        Label(parent, text=title, bg="#141922", fg="#b7bcc6", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 3))
        Entry(parent, textvariable=variable, state="readonly", readonlybackground="#0f1620", fg="#41d9e8" if highlight else "#f3eee5", relief="flat", font=("Consolas", 11)).pack(fill=X, ipady=9, pady=(0, 8))

    def ui(self, function) -> None:
        if not self.stopping:
            self.root.after(0, function)

    def _startup_sequence(self) -> None:
        try:
            self.ui(lambda: self.message_var.set(self.t["backend_starting"]))
            self._start_server()
            self.ui(lambda: self.agent_var.set(self.t["active"]))
        except Exception as error:
            self.logger.exception("Internal agent startup failed: %s", error)
            message = f"{self.t['backend_failed']}\n{type(error).__name__}: {error}"
            self.ui(lambda: self.message_var.set(message))
            self.ui(lambda: self.agent_var.set(self.t["error"]))
            return

        if not self.config.external_enabled:
            self.ui(lambda: self.tunnel_var.set(self.t["unavailable"]))
            return

        try:
            self._ensure_cloudflared()
            self._start_tunnel()
        except Exception as error:
            self.logger.exception("External connection startup failed: %s", error)
            message = f"{type(error).__name__}: {error}"
            self.ui(lambda: self.message_var.set(message))
            self.ui(lambda: self.tunnel_var.set(self.t["error"]))
            self.ui(lambda: self.external_var.set(self.t["tunnel_error"]))

    @staticmethod
    def _is_port_available(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            return sock.connect_ex(("127.0.0.1", port)) != 0

    def _find_available_port(self, preferred: int) -> int:
        if self._is_port_available(preferred):
            return preferred

        for candidate in range(max(1024, preferred + 1), min(65535, preferred + 100) + 1):
            if self._is_port_available(candidate):
                return candidate

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _apply_runtime_port(self, port: int) -> None:
        old_port = self.config.port
        if port == old_port:
            return

        update_server_port(port)
        self.config = load_config()
        self.local_url = f"http://{local_ip()}:{self.config.port}"
        self.ui(lambda: self.local_var.set(self.local_url))
        self.ui(
            lambda: self.message_var.set(
                self.t["port_changed"].format(old=old_port, new=self.config.port)
            )
        )
        self.logger.warning(
            "Configured port %s was occupied; automatically changed to %s",
            old_port,
            self.config.port,
        )
        self._write_connection_file()

    def _server_is_healthy(self, port: int | None = None) -> bool:
        target_port = port or self.config.port
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{target_port}/api/health",
                timeout=1.2,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return payload.get("ok") is True
        except Exception:
            return False

    def _start_server(self) -> None:
        if self._server_is_healthy(self.config.port):
            self.logger.info("Internal server is already healthy on port %s", self.config.port)
            try:
                agent_app = importlib.import_module("app")
                self.runtime_status = agent_app.runtime_status
            except Exception:
                pass
            return

        if self.server_thread and self.server_thread.is_alive():
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                if self._server_is_healthy(self.config.port):
                    return
                time.sleep(0.25)
            raise RuntimeError("BACKEND_THREAD_RUNNING_WITHOUT_HEALTH")

        selected_port = self._find_available_port(self.config.port)
        self._apply_runtime_port(selected_port)

        self.logger.info(
            "Starting internal server on %s:%s",
            self.config.host,
            self.config.port,
        )

        try:
            import uvicorn
            agent_app = importlib.import_module("app")
            fastapi_app = agent_app.app
            self.runtime_status = agent_app.runtime_status
        except Exception as error:
            raise RuntimeError(f"BACKEND_IMPORT_FAILED: {error}") from error

        uv_config = uvicorn.Config(
            fastapi_app,
            host=self.config.host,
            port=self.config.port,
            log_level="warning",
            access_log=False,
            log_config=None,
            use_colors=False,
            loop="asyncio",
            http="h11",
            ws="websockets",
        )
        self.server = uvicorn.Server(uv_config)
        self.server_thread = threading.Thread(
            target=self.server.run,
            name="FastAPI",
            daemon=True,
        )
        self.server_thread.start()

        health_url = f"http://127.0.0.1:{self.config.port}/api/health"
        deadline = time.monotonic() + 35
        last_error: Exception | None = None

        while time.monotonic() < deadline:
            if not self.server_thread.is_alive():
                raise RuntimeError("BACKEND_THREAD_STOPPED")

            try:
                with urllib.request.urlopen(health_url, timeout=1.5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    if payload.get("ok") is True:
                        self.logger.info("Internal server health check succeeded")
                        return
            except Exception as error:
                last_error = error
                time.sleep(0.3)

        detail = f": {last_error}" if last_error else ""
        raise RuntimeError(self.t["server_error"] + detail)

    @property
    def cloudflared_path(self) -> Path:
        return PROJECT_DIR / "tools" / "cloudflared.exe"

    def _ensure_cloudflared(self) -> None:
        path = self.cloudflared_path
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest().lower() == CLOUDFLARED_SHA256:
            return
        self.ui(lambda: self.message_var.set(self.t["download"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".download")
        if temp.exists():
            temp.unlink()
        request = urllib.request.Request(CLOUDFLARED_URL, headers={"User-Agent": "KageLink/3.3.0"})
        with urllib.request.urlopen(request, timeout=120) as response, temp.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        payload = temp.read_bytes()
        digest = hashlib.sha256(payload).hexdigest().lower()
        if digest != CLOUDFLARED_SHA256:
            temp.unlink(missing_ok=True)
            raise RuntimeError(
                f"Cloudflared SHA-256 verification failed: expected "
                f"{CLOUDFLARED_SHA256}, received {digest}"
            )
        if not payload.startswith(b"MZ"):
            temp.unlink(missing_ok=True)
            raise RuntimeError("Downloaded cloudflared file is not a valid Windows executable")

        try:
            version_result = subprocess.run(
                [str(temp), "--version"],
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            version_text = (version_result.stdout + version_result.stderr).strip()
            if version_result.returncode != 0 or CLOUDFLARED_VERSION not in version_text:
                temp.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Unexpected cloudflared version: {version_text or 'unknown'}"
                )
        except OSError as error:
            temp.unlink(missing_ok=True)
            raise RuntimeError(f"Could not validate cloudflared version: {error}") from error

        temp.replace(path)
        self.logger.info("cloudflared %s installed and verified", CLOUDFLARED_VERSION)

    def _start_tunnel(self) -> None:
        if self.tunnel_process and self.tunnel_process.poll() is None:
            return
        self.external_url = ""
        self.ui(lambda: self.external_var.set(self.t["waiting"]))
        self.ui(lambda: self.tunnel_var.set(self.t["starting"]))
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.tunnel_process = subprocess.Popen(
            [str(self.cloudflared_path), "tunnel", "--no-autoupdate", "--protocol", "http2", "--url", f"http://127.0.0.1:{self.config.port}", "--loglevel", "info"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
        self.tunnel_thread = threading.Thread(target=self._read_tunnel, name="Cloudflare", daemon=True)
        self.tunnel_thread.start()

    def _read_tunnel(self) -> None:
        process = self.tunnel_process
        if not process or not process.stdout:
            return
        log_path = PROJECT_DIR / "logs" / "tunnel.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log:
            for line in process.stdout:
                log.write(line)
                log.flush()
                match = URL_PATTERN.search(line)
                if match and not self.external_url:
                    self.external_url = match.group(0)
                    self.ui(lambda: self.external_var.set(self.external_url))
                    self.ui(lambda: self.tunnel_var.set(self.t["connected"]))
                    self.ui(
                        lambda: self.message_var.set("")
                        if self.agent_var.get() != self.t["error"]
                        else None
                    )
                    self._write_connection_file()
        if not self.stopping and not self.external_url:
            self.ui(lambda: self.tunnel_var.set(self.t["error"]))
            self.ui(lambda: self.message_var.set(self.t["tunnel_error"]))

    def _write_connection_file(self) -> None:
        path = PROJECT_DIR / "KAGELINK_CONNECTION.txt"
        external_value = self.external_url or self.t["waiting"]
        if self.lang == "pt-BR":
            content = f"""KageLink — Informações de conexão\n\nEndereço externo:\n{external_value}\n\nEndereço local:\n{self.local_url}\n\nChave de acesso:\n{self.config.access_token}\n\nAbra o aplicativo KageLink e cadastre o endereço externo e a chave acima.\n"""
        else:
            content = f"""KageLink — Connection information\n\nExternal address:\n{external_value}\n\nLocal address:\n{self.local_url}\n\nAccess key:\n{self.config.access_token}\n\nOpen the KageLink app and enter the external address and key above.\n"""
        path.write_text(content, encoding="utf-8")

    def _poll_runtime(self) -> None:
        if self.stopping:
            return

        backend_healthy = self._server_is_healthy()
        if backend_healthy:
            self.agent_var.set(self.t["active"])
        elif self.server_thread is not None and not self.server_thread.is_alive():
            self.agent_var.set(self.t["error"])

        status = self.runtime_status
        if status is not None and backend_healthy:
            self.game_var.set(
                self.t["located"] if status.game_online else self.t["not_located"]
            )
            self.chat_var.set(
                self.t["located"] if status.chat_found else self.t["not_located"]
            )
            self.input_var.set(
                self.t["ready"] if status.ooc_input_found else self.t["unavailable"]
            )
            if (
                not status.game_online
                and not self.external_url == ""
                and not self.message_var.get()
            ):
                self.message_var.set(self.t["backend_active_game_missing"])

        self.root.after(1200, self._poll_runtime)

    def copy(self, value: str) -> None:
        if not value:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.message_var.set(self.t["copied"])

    def copy_both(self) -> None:
        self.copy(f"{self.external_url}\n{self.config.access_token}")

    def open_connection_file(self) -> None:
        path = PROJECT_DIR / "KAGELINK_CONNECTION.txt"
        if path.exists():
            os.startfile(path)

    def restart_tunnel(self) -> None:
        threading.Thread(target=self._restart_tunnel_worker, name="TunnelRestart", daemon=True).start()

    def _restart_tunnel_worker(self) -> None:
        self._stop_tunnel()
        time.sleep(0.5)
        try:
            self._start_tunnel()
        except Exception as error:
            self.logger.exception("Tunnel restart failed: %s", error)
            self.ui(lambda: self.message_var.set(str(error)))

    def _stop_tunnel(self) -> None:
        process = self.tunnel_process
        self.tunnel_process = None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    def open_logs(self) -> None:
        log_dir = PROJECT_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(log_dir)

    def retry_startup(self) -> None:
        if self._server_is_healthy():
            self.agent_var.set(self.t["active"])
            if not self.external_url:
                self.restart_tunnel()
            return

        if self.server_thread and self.server_thread.is_alive():
            self.message_var.set(self.t["backend_starting"])
            return

        self.agent_var.set(self.t["starting"])
        self.message_var.set(self.t["backend_starting"])
        threading.Thread(
            target=self._startup_sequence,
            name="StartupRetry",
            daemon=True,
        ).start()

    def open_settings(self) -> None:
        window = Toplevel(self.root)
        window.title(self.t["settings"])
        window.geometry("430x300")
        window.transient(self.root)
        window.grab_set()
        language = StringVar(value=self.lang)
        port = StringVar(value=str(self.config.port))
        regenerate = BooleanVar(value=False)
        Label(window, text="Idioma / Language").pack(anchor="w", padx=24, pady=(24, 5))
        ttk.Combobox(window, textvariable=language, values=["pt-BR", "en-US"], state="readonly").pack(fill=X, padx=24)
        Label(window, text="Porta / Port").pack(anchor="w", padx=24, pady=(18, 5))
        Entry(window, textvariable=port).pack(fill=X, padx=24)
        ttk.Checkbutton(window, text="Gerar nova chave / Generate new key", variable=regenerate).pack(anchor="w", padx=24, pady=18)

        def save() -> None:
            try:
                value = int(port.get())
                if not 1024 <= value <= 65535:
                    raise ValueError
            except ValueError:
                messagebox.showerror("KageLink", "Porta inválida / Invalid port", parent=window)
                return
            if regenerate.get() and not messagebox.askyesno("KageLink", "Gerar uma nova chave desconectará os perfis atuais. Continuar?\nGenerating a new key will disconnect current profiles. Continue?", parent=window):
                return
            update_user_settings(language=language.get(), port=value, regenerate_token=regenerate.get())
            messagebox.showinfo("KageLink", self.t["restart_needed"], parent=window)
            self._restart_application()

        Button(window, text="Salvar / Save", command=save).pack(pady=10)

    def _restart_application(self) -> None:
        executable = [sys.executable]
        if not getattr(sys, "frozen", False):
            executable.append(str(Path(__file__).resolve()))
        self.shutdown(prompt=False)
        subprocess.Popen(executable, cwd=PROJECT_DIR)
        self.root.destroy()

    def request_close(self) -> None:
        if messagebox.askyesno("KageLink", self.t["close_confirm"], parent=self.root):
            self.shutdown(prompt=False)
            self.root.destroy()

    def shutdown(self, prompt: bool = False) -> None:
        if self.stopping:
            return
        self.stopping = True
        self._stop_tunnel()
        if self.server is not None:
            self.server.should_exit = True
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=5)
        release_mutex()


def main() -> None:
    _ensure_standard_streams()
    if os.name != "nt":
        raise SystemExit("KageLink PC Agent is available only for Windows.")
    if already_running():
        return

    root: Tk | None = None
    try:
        root = Tk()
        root.title(APP_TITLE)
        root.withdraw()

        first_run = not CONFIG_PATH.exists()
        if first_run:
            # Use the installer's language as a suggestion, when available.
            suggestion = PROJECT_DIR / "install_language.txt"
            wizard = FirstRunWizard(root)
            if suggestion.exists():
                value = suggestion.read_text(encoding="utf-8-sig").strip()
                if value in {"pt-BR", "en-US"}:
                    wizard.language.set(value)
                    wizard.render()
            result = wizard.show()
            if result is None:
                root.destroy()
                release_mutex()
                return
            ensure_config(language=result[0], port=result[1])
        else:
            ensure_config()

        root.deiconify()
        root.lift()
        try:
            root.attributes("-topmost", True)
            root.after(700, lambda: root.attributes("-topmost", False))
        except Exception:
            pass
        root.after(100, root.focus_force)

        KageLinkAgentUI(root)
        root.mainloop()
    finally:
        release_mutex()




def _startup_log_path() -> Path:
    return PROJECT_DIR / "logs" / "startup_error.log"


def _write_startup_error(error: BaseException) -> Path:
    path = _startup_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        details = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        path.write_text(
            "KageLink PC Agent startup failure\n"
            "=================================\n\n"
            + details,
            encoding="utf-8",
        )
    except Exception:
        pass
    return path


def _show_native_error(message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            message,
            "KageLink PC Agent",
            0x00000010 | 0x00001000,
        )
    except Exception:
        pass


def run_with_crash_reporting() -> None:
    try:
        main()
    except SystemExit:
        raise
    except BaseException as error:
        path = _write_startup_error(error)
        _show_native_error(
            "KageLink could not start.\n\n"
            "KageLink não pôde iniciar.\n\n"
            f"Diagnostic log / Log de diagnóstico:\n{path}"
        )

if __name__ == "__main__":
    run_with_crash_reporting()
