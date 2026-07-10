# Changelog

## - 2026-07-09 v1.0.1

### ✨ Key Features
*   **Precision Hardware Gating:** Stabilizes the SoC at an optimal **~75°C** ~ **~85°C** by executing a low-latency **138ms RUN / 12ms PAUSE** loop (92.0% active duty cycle).
*   **Dynamic Pause:** Further throttles the process upon reaching **72°C** by pausing **12ms, 72°C** ~ **48ms, 85°C+**.
*   **Software Requirement:** Uses [iSMC CLI](https://github.com/dkorunic/iSMC) to read/decode temperature.

## - 2026-07-09 v1.0.0

### 🚀 SiliconPacer Launch
Initial production release of **SiliconPacer**, a lean, zero-dependency background thermal pacing utility tailored for Apple Silicon MacBooks running sustained local AI matrix workloads (such as `llama-server`). 

This release focuses entirely on ultra-low overhead by interacting with process execution states directly via native memory space, dropping chassis and keyboard temperatures without requiring `sudo` privileges or relying on heavy external polling loops.

### ✨ Key Features
*   **Precision Hardware Gating:** Stabilizes the SoC at an optimal **~75°C** ~ **~85°C** by executing a low-latency **138ms RUN / 16ms PAUSE** loop (89.6% active duty cycle).
*   **Zero-Fork Architecture:** Bypasses expensive subprocess forks (`ps`, `grep`, `kill`), utilizing direct in-process `ctypes` system calls for immediate PID discovery and tracking.
*   **Automatic QoS Wrapping:** Automatically wrapper-boots itself into the macOS `utility` background tier via `taskpolicy -c utility` to ensure zero runtime impact on frontend tasks.
*   **Speculative Decoding Friendly:** Keeps request latencies down to high-power baselines, eliminating the up to 5x prompt processing and 2x token generation slowdowns caused by native system-wide Low Power modes.

