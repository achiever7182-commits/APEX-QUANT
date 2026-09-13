import subprocess
import sys
import time

import signal

cmd = [sys.executable, "launch_all.py", "--with-cpp", "--port", "5002", "--no-browser", "--dry-run"]
print(f"Launching: {' '.join(cmd)}")

proc = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
)

start = time.time()
output_lines = []
try:
    while time.time() - start < 12.0:
        line = proc.stdout.readline()
        if line:
            print(line, end="", flush=True)
            output_lines.append(line)
        if proc.poll() is not None:
            break
finally:
    print("\nSending Ctrl+Break / SIGINT to launch_all.py...", flush=True)
    if sys.platform == "win32":
        proc.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# Check tasklist to confirm clean shutdown
print("\n--- CHECKING TASKLIST FOR ORPHANS ---")
tl = subprocess.check_output("tasklist /FI \"IMAGENAME eq binance_testnet_bot.exe\"", shell=True, text=True)
print(tl)
assert "binance_testnet_bot.exe" not in tl or "No tasks are running" in tl or "INFO:" in tl, "binance_testnet_bot.exe should not be running"
print("SUCCESS: Zero orphan processes found!")
