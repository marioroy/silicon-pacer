# SiliconPacer

<a href="https://opensource.org"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>

> Thermal regulator and low-overhead GPU duty-cycler for local LLM workloads on Apple Silicon.

An advanced, zero-dependency Python thermal regulator designed to stabilize system temperatures on Apple Silicon MacBooks running sustained local AI/LLM matrix workloads. By forcing a low-overhead hardware duty cycle at the kernel level, SiliconPacer prevents chassis and keyboard overheating while retaining the vast majority of your hardware's high-power inference performance.

---

## 💻 The Problem: Chassis Heat vs. High Power Mode
Sustaining matrix operations on a **14" MacBook Pro (M5 Max, 32-core GPU)** under High Power Mode quickly pushes the aluminum enclosure to uncomfortable temperatures. The keyboard and top chassis become hot to the touch, and the SoC baseline hovers at thermal thresholds. 

Standard macOS power management does not offer granular, application-specific process duty-cycling. Manually toggling system-wide low-power modes severely multi-throttles the GPU, dropping prompt processing speeds by up to 5x and token generation speeds by up to 2x.

---

## ⚡ The Solution: Low-Overhead Kernel Gating
SiliconPacer hooks directly into native macOS kernel signals (`SIGSTOP` and `SIGCONT`) using direct `ctypes` system calls. It completely bypasses expensive shell forks (`ps`, `grep`, `kill`) to dynamically cycle target processes on the fly:

*   **⏱️ Optimized Execution Ratio:** Cycles target PIDs through a strict **138ms RUN / 16ms PAUSE** duty-cycle window.
*   **🌡️ Thermal Stabilization:** Forces a precise **89.6% execution ceiling**, stabilizing the SoC at a cool **~75°C** (with fans manually configured to 5,200 RPM). Note: A low RPM will not rid of the heat buildup at the center of the keyboard with prolong AI tasks. Try 3,800 ~ 6,200 RPM.
*   **🛠️ QoS Downgrading:** Automatically wrapper-boots itself into the macOS `utility` Quality of Service tier via `taskpolicy -c utility` to optimize background efficiency.
*   **🧠 Real-Time PID Tracking:** Safely catches model reloads and `llama-server` restarts via direct, in-process C-buffer lookups.

---

## 📊 Empirical Benchmarks

The following benchmarks demonstrate actual performance across three heavy architectural configurations evaluated on an **M5 Max (32-core GPU variant)** running Unsloth GGUF binaries.

### 1. Gemma-4-26B-A4B-it
*   **Base:** `gemma-4-26B-A4B-it-UD-Q4_K_XL.gguf` | **Draft:** `Q8_0-MTP.gguf`

| Metric | High-Power Mode | High-Power + SiliconPacer | Low-Power Mode |
| :--- | :--- | :--- | :--- |
| **Prompt Eval Speed** | 1662.63 t/s | 1445.38 t/s | 753.18 t/s |
| **Gen Eval Speed** | 116.87 t/s | 82.65 t/s | 60.92 t/s |
| **Draft Acceptance** | 86.38% | 80.15% | 85.77% |
| **Total Latency** | 3.38 seconds | 4.26 seconds | 5.96 seconds |

### 2. Gemma-4-31B-it-qat
*   **Base:** `gemma-4-31B-it-qat-UD-Q4_K_XL.gguf` | **Draft:** `Q8_0-MTP.gguf`

| Metric | High-Power Mode | High-Power + SiliconPacer | Low-Power Mode |
| :--- | :--- | :--- | :--- |
| **Prompt Eval Speed** | 393.44 t/s | 373.60 t/s | 193.42 t/s |
| **Gen Eval Speed** | 38.01 t/s | 31.27 t/s | 16.69 t/s |
| **Draft Acceptance** | 88.07% | 83.15% | 82.84% |
| **Total Latency** | 10.02 seconds | 12.34 seconds | 68.86 seconds |

### 3. Qwen3.6-35B-A3B-MTP
*   **Unified Base:** `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf`

| Metric | High-Power Mode | High-Power + SiliconPacer | Low-Power Mode |
| :--- | :--- | :--- | :--- |
| **Prompt Eval Speed** | 1410.44 t/s | 1274.54 t/s | 655.07 t/s |
| **Gen Eval Speed** | 112.57 t/s | 82.58 t/s | 59.40 t/s |
| **Draft Acceptance** | 78.46% | 83.97% | 86.19% |
| **Total Latency** | 4.46 seconds | 5.08 seconds | 7.25 seconds |

---

## 🔍 Key Performance Insights

*   **The Low-Power Choke Hazard:** Relying on basic native Low-Power modes to control thermals introduces catastrophic bottlenecks. On the 31B parameter model, dropping to standard low-power mode drags a request out to **68.8 seconds**. SiliconPacer maintains high-power execution pathways, dispatching that same request in just **12.3 seconds**—a **457% performance advantage** while keeping the laptop cool to the touch.
*   **Minimal "Performance Tax":** Averaging performance across all models, the script limits raw token generation speeds by **only ~21%** overall compared to wide-open High Power mode, entirely eliminating thermal throttling degradation.

---

## 🛠️ Usage & Deployment

SiliconPacer requires no external pip packages, relying exclusively on standard library modules (`ctypes`, `signal`, `os`). 

### 📋 System Requirements
*   **Operating System:** macOS 12.0 (Monterey) or higher (OS check enforced at runtime).
*   **Hardware Dependency:** Designed for Apple Silicon MacBooks (M-Series Max/Pro/Base).

### 1. Make the Script Executable
```bash
chmod +x silicon_pacer.py
```

### 2. Standard Launch (Targeting llama-server)
By default, the script scans, captures, and applies the duty cycle to `llama-server` instances:
```bash
./silicon_pacer.py
```

### 3. Target Custom Workloads
You can specify any alternative compute-heavy process name as an optional positional argument (e.g., `llama-bench`):
```bash
./silicon_pacer.py llama-bench
```

### 4. Safe Termination
Press `Ctrl+C` inside the terminal window to quit. The script captures the exit sequence to issue an immediate `SIGCONT` fail-safe, ensuring all target processes are left in an active, unfrozen state. Run `killall llama-server` to stop the server.

---

## 🤝 Attribution & Contributors

*   **Empirical Benchmarking & Optimization:** [Mario Roy](https://github.com/marioroy) – Architected the hardware grace ratios and empirical pacing calculations.
*   **AI Development Co-Pilot:** Gemini (Google) – Architected the automated QoS taskpolicy wrapper and repository deployment structure.

---

## 📄 License & Disclaimer

This project is licensed under the terms of the **MIT License**.

**Disclaimer:** This utility manipulates hardware process states using low-level kernel signals. By running this software, you acknowledge that you are doing so entirely at your own risk. The authors are not responsible for any hardware degradation, battery wear, system instability, or thermal issues resulting from the use or misuse of this script.

