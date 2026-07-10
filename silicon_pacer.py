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

Software Requirements:
This runs [iSMC CLI](https://github.com/dkorunic/iSMC) to read the SoC sensors.
The iSMC utility can be installed via the Homebrew package manager.
- brew tap dkorunic/tap
- brew trust dkorunic/tap
- brew install ismc

LEGAL DISCLAIMER & LIABILITY LIMITATION
---------------------------------------
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

import os
import shutil
import sys

# --- OS ENFORCEMENT GUARD AND SOFTWARE REQUIREMENT ---
if sys.platform != "darwin":
    print("❌ Error: SiliconPacer is designed exclusively for macOS (Apple Silicon).")
    print(f"   Detected platform '{sys.platform}' is not supported.")
    print("")
    sys.exit(1)

if shutil.which("iSMC") is None:
    print("❌ Error: Required command 'iSMC' is not installed.")
    print("   Install 'ismc' via Homebrew package manager and try again.")
    print("")
    print("     brew tap dkorunic/tap")
    print("     brew trust dkorunic/tap")
    print("     brew install ismc")
    print("")
    sys.exit(1)

# --- AUTOMATIC QoS POLICY CHANGE (taskpolicy -c utility wrapper) ---
if os.environ.get("THROTTLE_BACKGROUNDED") != "1":
    os.environ["THROTTLE_BACKGROUNDED"] = "1"
    os.execvp("taskpolicy", ["taskpolicy", "-c", "utility", sys.executable] + sys.argv)

PROC_NAME = sys.argv[1] if len(sys.argv) > 1 else "llama-server"
PROC_PIDPATHINFO_MAXSIZE = 1024

import ctypes
import math
import signal
import time

import json
import subprocess
import multiprocessing as mp

# This application is fork-safe, not using threads before forking.
# Explicitly set the multiprocessing start method to fork.
mp.set_start_method("fork", force=True)

# --- CONFIGURATION & GRACE FACTOR ---
ACTIVE_MS = 138       # Base active execution window (92.0% active duty cycle)
MIN_PAUSE_MS = 12     # Best-case cool-down window (8.0% cool-down window)
MAX_PAUSE_MS = 48     # Worst-case cool-down window if reaching 85°C

active_sec = ACTIVE_MS / 1000.0
pause_sec = MIN_PAUSE_MS / 1000.0  # Starts at base level

print("SiliconPacer v1.0.1")
print(f"QoS policy applied automatically, re-launched via 'taskpolicy -c utility'")
print(f"Duty-cycling '{PROC_NAME}': {ACTIVE_MS}ms RUN / {MIN_PAUSE_MS}ms PAUSE")
print("Press Ctrl+C to stop the throttle and restore normal process execution.")

def read_thermal_sensors():
    """
    Returns the max average temperature of the CPU cores / GPU clusters.
    """
    cpu_current_average = 65.0
    gpu_current_average = 65.0

    try:
        result = subprocess.run(
            ["iSMC", "temp", "-o", "json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            cpu_core_temps = []
            gpu_cluster_temps = []

            for name, details in data.items():
                name_lower = name.lower()

                # Display the SoC Regulator V, W, and X data
                # SoC Regulator V (TSVR): This is your primary core voltage rail feeding the
                #   intensive matrix math engines inside the GPU clusters
                # SoC Regulator W / X (TSWR / TSXR): These power the low-power efficiency cores,
                #   media engines, or peripheral I/O blocks
                """
                if "soc regulator" in name_lower:
                    quantity = details.get("quantity")
                    if quantity is not None:
                        print(f"{name}:  {quantity:10.6f} °C", flush=True)
                        continue
                """

                # Target explicit CPU core entries (e.g., CPU Performance / Super Core N)
                if "cpu" in name_lower and "core" in name_lower:
                    quantity = details.get("quantity")
                    if quantity is not None:
                        try:
                            cpu_core_temps.append(float(quantity))
                        except ValueError:
                            continue

                # Target explicit GPU cluster entries (e.g., "GPU 1", "GPU 42")
                if "gpu" in name_lower:
                    # Strict exclusion filter to skip static rails, fabric blocks, heatsinks,
                    # and probes
                    if not any(x in name_lower for x in ["max", "fabric", "heatsink", "probe"]):
                        quantity = details.get("quantity")
                        if quantity is not None:
                            try:
                                gpu_cluster_temps.append(float(quantity))
                            except ValueError:
                                continue

            if cpu_core_temps or gpu_cluster_temps:
                print("", flush=True)

            if cpu_core_temps:
                # Calculate the live mathematical average of your active processing cores
                cpu_current_average = sum(cpu_core_temps) / len(cpu_core_temps)
                print(f"CPU Core Average: {cpu_current_average:10.6f} °C", flush=True)

            if gpu_cluster_temps:
                # Calculate the live mathematical average of your active processing clusters
                gpu_current_average = sum(gpu_cluster_temps) / len(gpu_cluster_temps)
                print(f"GPU Core Average: {gpu_current_average:10.6f} °C", flush=True)

    except Exception:
        pass

    return max(cpu_current_average, gpu_current_average)

def bg_thermal_sensor_worker(shared_float):
    """
    Ensures the duty-cycler reacts strictly to CPU / GPU load dynamically.
    """
    # 1. Get the background process's own PID
    my_pid = os.getpid()

    # 2. Call taskpolicy to enforce background execution (E-cores only)
    try:
        subprocess.run(["taskpolicy", "-b", "-p", str(my_pid)], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"[Child Process {my_pid}] Failed to set taskpolicy: {e}")

    try:
        while True:
            max_celsius = read_thermal_sensors()
            with shared_float.get_lock():
                shared_float.value = max_celsius
            # Reading sensors via iSMC takes 0.34s or 13.6m in an 8-hour period.
            # Refreshing in 12s interval keeps background overhead near 0%.
            time.sleep(12.0)
    except KeyboardInterrupt:
        pass

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

# Spawn the background process
shared_val = mp.Value('d', 65.0)  # Safe default baseline
bg_worker = mp.Process(target=bg_thermal_sensor_worker, args=(shared_val,))
bg_worker.start()

time.sleep(0.5) # Give time for the bg process to report the first time.

# Initialize the cache once at startup
target_pids = get_target_pids(PROC_NAME)
last_pause_sec = 0.0

try:
    while True:
        # If a process was closed or hasn't started yet, look for it calmly
        if not target_pids:
            target_pids = get_target_pids(PROC_NAME)
            if not target_pids:
                time.sleep(1.5) # Don't burn CPU spinning if the process is missing
                continue

        # Celsius evaluation - Adjusts pause_sec dynamically
        with shared_val.get_lock():
            max_celsius = shared_val.value

        if max_celsius >= 72.0:
            clamped_temp = min(85.0, max_celsius)

            # Linear scaling calculation
            thermal_strain = (clamped_temp - 72.0) / (85.0 - 72.0)
            dynamic_pause_ms = MIN_PAUSE_MS + (thermal_strain * (MAX_PAUSE_MS - MIN_PAUSE_MS))
            pause_sec = dynamic_pause_ms / 1000.0
        else:
            pause_sec = MIN_PAUSE_MS / 1000.0

        if not math.isclose(pause_sec, last_pause_sec, abs_tol=1e-9):
            last_pause_sec = pause_sec
            print(f"   Pause Seconds: {pause_sec:10.6f}", flush=True)

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
    print("Cleaning up background process...")
    bg_worker.terminate()
    bg_worker.join()
    print("Done.")

