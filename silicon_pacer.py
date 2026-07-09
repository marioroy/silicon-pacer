#!/usr/bin/env python3
"""
SiliconPacer: Thermal Regulator & GPU Duty-Cycler
-------------------------------------------------
Purpose:
Solves the severe keyboard and chassis overheating issues on the 14" MacBook Pro 
running sustained local AI/LLM matrix workloads in High Power Mode. 

Target Hardware: 
MacBook Pro 14" (M5 Max, 32-core GPU variant)

Usage:
  silicon_pacer.py                 -> Targets 'llama-server' (Default)
  silicon_pacer.py <process_name>  -> Targets a custom process (e.g., llama-bench)

⚠️  LEGAL DISCLAIMER & LIABILITY LIMITATION
------------------------------------------
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR 
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. 

IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, 
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, 
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER 
DEALINGS IN THE SOFTWARE. 

THIS UTILITY MANIPULATES PROCESS EXECUTION STATES AT THE OS KERNEL LEVEL. USE AT 
YOUR OWN RISK. THE AUTHORS ASSUME ABSOLUTE ZERO LIABILITY FOR HARDWARE DAMAGE, 
THERMAL DEGRADATION, SYSTEM UNSTABILITY, DATA LOSS, OR KERNEL PANICS.

Authors & Attribution:
- Grace Factor: Mario Roy (Empirical benchmarking and ratio optimization)
- AI Development Co-Pilot: Gemini (Architected the QoS policy change script wrapper)
"""

import ctypes
import os
import signal
import sys
import time

PROC_PIDPATHINFO_MAXSIZE = 1024

# --- OS ENFORCEMENT GUARD ---
if sys.platform != "darwin":
    print("❌ Error: SiliconPacer is designed exclusively for macOS (Apple Silicon).")
    print(f"   Detected platform '{sys.platform}' is not supported.")
    sys.exit(1)

# --- AUTOMATIC QoS POLICY CHANGE (taskpolicy -c utility wrapper) ---
if os.environ.get("THROTTLE_BACKGROUNDED") != "1":
    os.environ["THROTTLE_BACKGROUNDED"] = "1"
    os.execvp("taskpolicy", ["taskpolicy", "-c", "utility", sys.executable] + sys.argv)

PROC_NAME = sys.argv[1] if len(sys.argv) > 1 else "llama-server"

# --- CONFIGURATION & GRACE FACTOR ---
ACTIVE_MS = 138   # Base active execution window (89.61% active duty cycle)
PAUSE_MS = 16     # Best-case cool-down window (10.39% cool-down window)

active_sec = ACTIVE_MS / 1000.0
pause_sec = PAUSE_MS / 1000.0

print(f"QoS policy applied automatically, re-launched via 'taskpolicy -c utility'")
print(f"Duty-cycling '{PROC_NAME}': {ACTIVE_MS}ms RUN / {PAUSE_MS}ms PAUSE")
print("Press Ctrl+C to stop the throttle and restore normal process execution.")

def get_target_pids(name):
    """Makes an in-process, direct system call to pull matching PIDs."""
    libc = ctypes.CDLL(None)

    # Explicitly declare the argtypes and restype profiles. This prevents any strange
    # memory alignment or type-casting issues across different macOS updates.
    libc.proc_listallpids.argtypes = [ctypes.c_void_p, ctypes.c_int]
    libc.proc_listallpids.restype = ctypes.c_int

    libc.proc_name.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    libc.proc_name.restype = ctypes.c_int

    num_pids = libc.proc_listallpids(None, 0)
    if num_pids <= 0:
        return []

    pid_array_type = ctypes.c_int32 * num_pids
    pid_buffer = pid_array_type()
    num_pids = libc.proc_listallpids(pid_buffer, ctypes.sizeof(pid_buffer))

    matches = []
    name_buffer = ctypes.create_string_buffer(PROC_PIDPATHINFO_MAXSIZE)

    for pid in pid_buffer[:num_pids]:
        pid = int(pid)
        length = libc.proc_name(pid, name_buffer, ctypes.sizeof(name_buffer))
        if length > 0:
            proc_name = name_buffer.value.decode('utf-8', errors='ignore')
            if name.lower() == proc_name.lower():
                matches.append(int(pid))

    return matches

# Initialize the cache once at startup
target_pids = get_target_pids(PROC_NAME)

try:
    while True:
        # If a process was closed or hasn't started yet, look for it calmly
        if not target_pids:
            target_pids = get_target_pids(PROC_NAME)
            if not target_pids:
                time.sleep(1.5) # Don't burn CPU spinning if the process is missing
                continue

        # 1. Resume Execution (SIGCONT) - Direct kernel communication
        try:
            for pid in target_pids:
                os.kill(pid, signal.SIGCONT)
        except ProcessLookupError:
            target_pids = [] # Process changed/died; trigger a lookup next loop pass
            continue

        time.sleep(active_sec)

        # 2. Freeze Execution (SIGSTOP) - Prevents massive heat spike
        try:
            for pid in target_pids:
                os.kill(pid, signal.SIGSTOP)
        except ProcessLookupError:
            target_pids = [] # Process changed/died; trigger a lookup next loop pass
            continue

        time.sleep(pause_sec)

except KeyboardInterrupt:
    # Fail-safe: Always unfreeze remaining targets upon script exit
    for pid in get_target_pids(PROC_NAME):
        try:
            os.kill(pid, signal.SIGCONT)
        except ProcessLookupError:
            pass
    print(f"\nThrottling stopped. All '{PROC_NAME}' instances safely unfrozen.")

