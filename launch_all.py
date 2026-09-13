#!/usr/bin/env python3
"""
launch_all.py — One-command unified launcher with process safety.

Starts the Python trading dashboard and optionally the compiled C++ bot.
Streams both outputs into a single terminal with distinct prefixes and
ensures clean, orphan-free termination on Ctrl+C.
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

# Load environment variables from .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT_DIR = Path(__file__).resolve().parent
CPP_EXE = ROOT_DIR / "cpp_trading_bot" / "build" / "Release" / "binance_testnet_bot.exe"
DASHBOARD_PORT = 5000
DASHBOARD_HOST = "127.0.0.1"


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a TCP port is currently occupied."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def get_pid_using_port(port: int) -> int | None:
    """Find the PID listening on the given port on Windows."""
    if sys.platform != "win32":
        return None
    try:
        output = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True)
        for line in output.strip().splitlines():
            if "LISTENING" in line:
                parts = line.strip().split()
                return int(parts[-1])
    except Exception:
        pass
    return None


def stream_reader(pipe, prefix: str, stop_event: threading.Event) -> None:
    """Read lines from a process pipe and print with an aligned prefix."""
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                break
            # Strip trailing newline and print prefixed
            text = line.rstrip("\r\n")
            if text:
                print(f"{prefix} {text}", flush=True)
            if stop_event.is_set():
                break
    except Exception:
        pass
    finally:
        pipe.close()


def stop_process(proc: subprocess.Popen, name: str, timeout: float = 3.0) -> None:
    """Terminate a subprocess cleanly, escalating to kill if needed."""
    if proc.poll() is not None:
        return
    print(f"\n[LAUNCHER] Terminating {name} (PID {proc.pid})...", flush=True)
    try:
        if sys.platform == "win32":
            # taskkill /T /F terminates the entire process tree reliably on Windows
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
    except Exception as err:
        print(f"[LAUNCHER] Error terminating {name}: {err}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unified Process Launcher for Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--with-cpp",
        action="store_true",
        help="Also launch the compiled C++ trading bot alongside Python",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open browser for the web dashboard",
    )
    parser.add_argument(
        "--strategy",
        "-s",
        default="tick",
        help="Strategy for the Python bot (default: tick)",
    )
    parser.add_argument(
        "--symbol",
        default="BTC/USDT",
        help="Trading pair symbol (default: BTC/USDT)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Web dashboard port (default: 5000)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run Python bot in dry-run mode (--no-trade)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    port = args.port

    print("=" * 78)
    print("   TRADING BOT UNIFIED LAUNCHER")
    print("=" * 78)

    # 1. Check if C++ is requested and verify its executable
    if args.with_cpp:
        if not CPP_EXE.is_file():
            print(f"\n[LAUNCHER ERROR] C++ executable not found at:")
            print(f"  {CPP_EXE}")
            print("\nTo build the C++ trading bot, run:")
            print("  cmake -B cpp_trading_bot/build -S cpp_trading_bot -DCMAKE_BUILD_TYPE=Release")
            print("  cmake --build cpp_trading_bot/build --config Release")
            print("\nExiting without starting Python bot.")
            sys.exit(1)

        print("\n" + "!" * 78)
        print("  WARNING: Python and C++ bots will trade independently on the SAME account")
        print("  with no coordination between them — this DOUBLES real order activity.")
        print("  This is for side-by-side comparison/observation only, NOT a combined strategy.")
        print("!" * 78 + "\n")

    # 2. Check if Dashboard Port is already in use
    if is_port_in_use(port, DASHBOARD_HOST):
        pid = get_pid_using_port(port)
        pid_msg = f" (PID {pid})" if pid else ""
        print(f"[LAUNCHER ERROR] Dashboard port {port} is already in use{pid_msg}!")
        print("  A previous dashboard instance is still running.")
        print(f"  Please terminate process {pid or ''} or close the running terminal first.")
        print("  Command on Windows: taskkill /F /PID <pid>")
        print(f"  Or specify a different port: python launch_all.py --port {port + 1}")
        sys.exit(1)

    # 3. Prepare environment and subprocess commands
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    py_cmd = [
        sys.executable,
        "-u",
        str(ROOT_DIR / "run.py"),
        "dashboard",
        "--strategy", args.strategy,
        "--symbol", args.symbol,
        "--port", str(port),
    ]
    if args.no_browser:
        py_cmd.append("--no-browser")
    if args.dry_run:
        py_cmd.append("--no-trade")

    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    stop_event = threading.Event()
    processes: list[tuple[str, subprocess.Popen]] = []

    def handle_signal(sig, frame):
        raise KeyboardInterrupt()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    if sys.platform == "win32" and hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, handle_signal)

    try:
        # Start Python dashboard process
        print(f"[LAUNCHER] Starting Python dashboard on http://{DASHBOARD_HOST}:{port}...")
        py_proc = subprocess.Popen(
            py_cmd,
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            creationflags=creationflags,
        )
        processes.append(("Python Bot", py_proc))

        py_thread = threading.Thread(
            target=stream_reader,
            args=(py_proc.stdout, "[PYTHON]", stop_event),
            daemon=True,
            name="python-stdout-reader",
        )
        py_thread.start()

        # Start C++ process if requested
        if args.with_cpp:
            print(f"[LAUNCHER] Starting C++ bot from {CPP_EXE.name}...")
            cpp_proc = subprocess.Popen(
                [str(CPP_EXE)],
                cwd=str(CPP_EXE.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                creationflags=creationflags,
            )
            processes.append(("C++ Bot   ", cpp_proc))

            cpp_thread = threading.Thread(
                target=stream_reader,
                args=(cpp_proc.stdout, "[CPP]   ", stop_event),
                daemon=True,
                name="cpp-stdout-reader",
            )
            cpp_thread.start()

        print("[LAUNCHER] All requested processes started. Press Ctrl+C to shut down cleanly.\n")

        # Monitor processes
        while True:
            time.sleep(0.5)
            for name, proc in processes:
                code = proc.poll()
                if code is not None:
                    print(f"\n[LAUNCHER ALERT] {name.strip()} terminated unexpectedly (exit code: {code})!", flush=True)
                    stop_event.set()
                    return

    except KeyboardInterrupt:
        print("\n[LAUNCHER] Shutdown signal received (Ctrl+C).", flush=True)
    finally:
        stop_event.set()
        for name, proc in reversed(processes):
            stop_process(proc, name)

        # Give processes a moment to fully release sockets/handles
        time.sleep(0.5)
        print("[LAUNCHER] All processes terminated. Clean exit.", flush=True)


if __name__ == "__main__":
    main()
