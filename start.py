"""
SilverShade Dev Starter
Starts and monitors all project servers with colour-coded output.

Usage:
  python start.py                  — start all four servers
  python start.py --no-fivem       — skip FivemDummy
  python start.py api website      — start specific servers only
"""

import os
import shutil
import signal
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))

# ── ANSI colours ──────────────────────────────────────────────────────────────
RESET   = "\x1b[0m"
BOLD    = "\x1b[1m"
DIM     = "\x1b[2m"
RED     = "\x1b[31m"
GREEN   = "\x1b[32m"
CYAN    = "\x1b[96m"
MAGENTA = "\x1b[95m"
YELLOW  = "\x1b[93m"
LIME    = "\x1b[92m"

# Enable ANSI on Windows (Python 3.12+ does this automatically, but be safe)
if sys.platform == "win32":
    os.system("")


def _find_node() -> str:
    """Return the absolute path to node.exe, or raise if not found."""
    found = shutil.which("node")
    if found:
        return found
    fallback = r"C:\Program Files\nodejs\node.exe"
    if os.path.exists(fallback):
        return fallback
    raise FileNotFoundError(
        "node.exe not found. Add Node.js to PATH or install it."
    )


# ── Port cleanup ─────────────────────────────────────────────────────────────
def _free_port(port: int) -> None:
    """Kill any process listening on *port* so we can bind to it cleanly."""
    if sys.platform != "win32":
        return
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return  # port is already free
        # Port is in use — find and kill the owner via netstat + taskkill
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                subprocess.run(["taskkill", "/F", "/PID", pid],
                               capture_output=True, timeout=5)
                break
    except Exception:
        pass


# ── Server definitions ────────────────────────────────────────────────────────
def _build_servers() -> list[dict]:
    node = None  # resolved lazily; only error if a node server is actually used

    def get_node():
        nonlocal node
        if node is None:
            node = _find_node()
        return node

    return [
        {
            "name":  "API",
            "color": CYAN,
            "cwd":   os.path.join(ROOT, "API"),
            "cmd":   os.path.join(ROOT, "API", ".venv", "Scripts", "uvicorn.exe"),
            "args":  ["main:app", "--reload", "--host", "127.0.0.1", "--port", "8000"],
            "url":   "http://127.0.0.1:8000",
        },
        {
            "name":  "Website",
            "color": MAGENTA,
            "cwd":   os.path.join(ROOT, "Website"),
            "cmd":   os.path.join(ROOT, "Website", ".venv", "Scripts", "uvicorn.exe"),
            "args":  ["serve:app", "--reload", "--host", "127.0.0.1", "--port", "8080"],
            "url":   "http://127.0.0.1:8080",
        },
        {
            "name":  "DiscordBot",
            "color": YELLOW,
            "cwd":   os.path.join(ROOT, "DiscordBot"),
            "cmd":   os.path.join(ROOT, "DiscordBot", ".venv", "Scripts", "python.exe"),
            "args":  ["bot.py"],
            "url":   None,
        },
        {
            "name":     "FivemDummy",
            "color":    LIME,
            "cwd":      os.path.join(ROOT, "FivemDummy"),
            "cmd":      None,
            "cmd_fn":   get_node,
            "args":     ["server.js"],
            "url":      "http://127.0.0.1:3000",
            "optional": True,
        },
    ]


# ── CLI argument parsing ──────────────────────────────────────────────────────
def parse_args(servers: list[dict]) -> list[dict]:
    args       = sys.argv[1:]
    no_fivem   = "--no-fivem" in args
    name_filter = [a.lower() for a in args if not a.startswith("--")]

    result = []
    for srv in servers:
        if no_fivem and srv.get("optional"):
            continue
        if name_filter and srv["name"].lower() not in name_filter:
            continue
        result.append(srv)

    if not result:
        print("No matching servers. Valid names: api  website  discordbot  fivemdummy")
        sys.exit(1)
    return result


# ── Logging ───────────────────────────────────────────────────────────────────
PAD = 11
_print_lock = threading.Lock()

# Pinned status bar state
_status_shown:   bool  = False
_status_height:  int   = 0
_status_servers: list  = []


def _label(srv: dict) -> str:
    name = srv["name"].ljust(PAD)
    return f"{srv['color']}{BOLD}[{name}]{RESET}"


def _build_status_text(servers: list[dict]) -> tuple[str, int]:
    """Build the status block string and return (text, line_count)."""
    rule = "─" * 54
    rows: list[str] = []
    rows.append(f"{DIM}  {rule}{RESET}")
    rows.append(f"{BOLD}  Status{RESET}")
    for srv in servers:
        state = registry.get(srv["name"])
        if not state:
            continue
        alive   = state["alive"]
        color   = GREEN if alive else RED
        dot     = f"{color}{'●' if alive else '✗'}{RESET}"
        label   = f"{color}{'running' if alive else 'stopped'}{RESET}"
        url     = f"  {DIM}{srv['url']}{RESET}" if srv.get("url") else ""
        retries = f"  {DIM}(restarts: {state['restarts']}){RESET}" if state["restarts"] else ""
        rows.append(f"  {_label(srv)} {dot} {label}{url}{retries}")
    rows.append(f"{DIM}  {rule}{RESET}")
    return "\n".join(rows) + "\n", len(rows)


def _draw_status(servers: list[dict]) -> None:
    """Draw (or redraw) the pinned status block. Caller must hold _print_lock."""
    global _status_shown, _status_height
    text, height = _build_status_text(servers)
    _status_height = height
    _status_shown  = True
    sys.stdout.write(text)


def log(srv: dict, line: str, dim: bool = False) -> None:
    text = f"{DIM}{line}{RESET}" if dim else line
    with _print_lock:
        if _status_shown and _status_height:
            # Retract the status block, print the log line, redraw the block
            sys.stdout.write(f"\x1b[{_status_height}A\x1b[0J")
        sys.stdout.write(f"{_label(srv)} {text}\n")
        if _status_shown:
            _draw_status(_status_servers)
        sys.stdout.flush()


# ── Process state ─────────────────────────────────────────────────────────────
# name -> {"proc": Popen | None, "alive": bool, "restarts": int}
registry: dict[str, dict] = {}
shutdown_event = threading.Event()


# ── Stream reader ─────────────────────────────────────────────────────────────
def _pipe_reader(srv: dict, stream, dim: bool) -> None:
    """Read lines from a stream and print them with the server label."""
    try:
        for raw in iter(stream.readline, b""):
            if shutdown_event.is_set():
                break
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                log(srv, line, dim=dim)
    except Exception:
        pass


# ── Start / restart a server ──────────────────────────────────────────────────
def start_server(srv: dict) -> None:
    if shutdown_event.is_set():
        return

    # Resolve node lazily
    cmd = srv.get("cmd") or srv["cmd_fn"]()

    if not os.path.isdir(srv["cwd"]):
        log(srv, f"{RED}Directory not found: {srv['cwd']}{RESET}")
        return

    if cmd != shutil.which("node") and not os.path.isfile(cmd):
        log(srv, f"{RED}Executable not found: {cmd}{RESET}")
        if ".venv" in cmd:
            log(srv, f"{DIM}Run: cd {srv['cwd']} && python -m venv .venv && pip install -r requirements.txt{RESET}")
        return

    log(srv, f"{DIM}Starting…{RESET}")

    # Free the port if something stale is still listening
    if srv.get("url"):
        try:
            port = int(srv["url"].rsplit(":", 1)[-1])
            _free_port(port)
        except (ValueError, IndexError):
            pass

    try:
        proc = subprocess.Popen(
            [cmd, *srv["args"]],
            cwd=srv["cwd"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
    except Exception as exc:
        log(srv, f"{RED}Spawn error: {exc}{RESET}")
        return

    state = registry.setdefault(srv["name"], {"proc": None, "alive": False, "restarts": 0})
    state["proc"]  = proc
    state["alive"] = True

    # Pipe stdout and stderr in background threads
    threading.Thread(target=_pipe_reader, args=(srv, proc.stdout, False), daemon=True).start()
    threading.Thread(target=_pipe_reader, args=(srv, proc.stderr, True),  daemon=True).start()

    # Watcher thread — handles exit and auto-restart
    def _watcher():
        proc.wait()
        state["alive"] = False
        if shutdown_event.is_set():
            return
        code = proc.returncode
        state["restarts"] += 1
        log(srv, f"{RED}Exited (code {code}). Restarting in 3 s… [restart #{state['restarts']}]{RESET}")
        time.sleep(3)
        start_server(srv)

    threading.Thread(target=_watcher, daemon=True).start()


# ── Graceful shutdown ─────────────────────────────────────────────────────────
def shutdown(*_) -> None:
    global _status_shown
    if shutdown_event.is_set():
        return
    shutdown_event.set()
    with _print_lock:
        if _status_shown and _status_height:
            sys.stdout.write(f"\x1b[{_status_height}A\x1b[0J")
        _status_shown = False   # prevent log() from repositioning during teardown
        sys.stdout.write(f"\n{DIM}Shutting down all servers…{RESET}\n")
        sys.stdout.flush()
    for state in registry.values():
        proc = state.get("proc")
        if proc and state.get("alive"):
            try:
                proc.terminate()
            except Exception:
                pass
    # Give processes 2 s, print final status, then exit
    time.sleep(2)
    for state in registry.values():
        state["alive"] = False
    with _print_lock:
        _draw_status(_status_servers)
        sys.stdout.flush()
    sys.exit(0)


signal.signal(signal.SIGINT,  shutdown)
signal.signal(signal.SIGTERM, shutdown)


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    global _status_servers
    servers = parse_args(_build_servers())
    _status_servers = servers

    line = "─" * 54
    print(f"\n{BOLD}  SilverShade Dev Starter{RESET}  {DIM}Ctrl+C to stop all{RESET}")
    print(f"{DIM}  {line}{RESET}\n")

    for srv in servers:
        start_server(srv)

    # Pin the status bar after servers have had time to boot
    def _initial_draw():
        with _print_lock:
            _draw_status(servers)
            sys.stdout.flush()

    t = threading.Timer(4.0, _initial_draw)
    t.daemon = True
    t.start()

    # Keep main thread alive
    while not shutdown_event.is_set():
        time.sleep(0.5)


if __name__ == "__main__":
    main()
