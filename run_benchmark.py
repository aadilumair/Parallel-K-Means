#!/usr/bin/env python3
"""
run_benchmark.py — System Information + K-Means Benchmark Runner
================================================================
Collects detailed system information (CPU, RAM, GPU, OS, environment)
then builds and runs both sequential and parallel K-Means C++ programs
via g++ + OpenMP inside WSL, captures timing output, generates a gnuplot
PNG comparison chart, and saves a full Markdown report to working/.

Usage (Windows PowerShell):
    wsl bash -c "cd /mnt/c/.../Parallel-K-Means && python3 run_benchmark.py"
Usage (inside WSL directly):
    python3 run_benchmark.py

The script always runs inside WSL. System info is collected purely from
Linux /proc, /sys, and standard Linux tools (no wmic/powershell).
"""

import subprocess
import sys
import os
import platform
import datetime
import json
import re
import time

# ──────────────────────────────────────────────────────────────────────────────
# Paths (all Linux paths since we are in WSL)
# ──────────────────────────────────────────────────────────────────────────────

ROOT_DIR   = os.path.dirname(os.path.abspath(__file__))
WORKING    = os.path.join(ROOT_DIR, "working")
REPORT_OUT = os.path.join(WORKING, "benchmark_results.md")

os.makedirs(WORKING, exist_ok=True)

DIVIDER   = "─" * 70
SEPARATOR = "=" * 70

# ──────────────────────────────────────────────────────────────────────────────
# Shell helpers
# ──────────────────────────────────────────────────────────────────────────────

def sh(cmd: str, timeout: int = 60) -> str:
    """Run a bash command and return stdout+stderr (never raises)."""
    try:
        r = subprocess.run(
            ["bash", "-c", cmd],
            capture_output=True, text=True, timeout=timeout
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        return out if out else err
    except Exception as e:
        return f"(error: {e})"

def sh_lines(cmd: str, timeout: int = 60) -> list[str]:
    return [l for l in sh(cmd, timeout).splitlines() if l.strip()]

def header(title: str) -> None:
    print(f"\n{SEPARATOR}\n  {title}\n{SEPARATOR}", flush=True)

def subheader(title: str) -> None:
    print(f"\n{DIVIDER}\n  {title}\n{DIVIDER}", flush=True)

# ──────────────────────────────────────────────────────────────────────────────
# 1. System Information  (all via /proc, /sys, standard Linux tools)
# ──────────────────────────────────────────────────────────────────────────────

class SystemInfo:

    # ── OS ────────────────────────────────────────────────────────────────────
    def collect_os(self) -> dict:
        d = {}
        d["kernel"]         = sh("uname -r")
        d["arch"]           = sh("uname -m")
        d["hostname"]       = sh("hostname")
        d["distro"]         = sh("lsb_release -ds 2>/dev/null || grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '\"'")
        d["distro_version"] = sh("lsb_release -rs 2>/dev/null || grep VERSION_ID /etc/os-release | cut -d= -f2 | tr -d '\"'")
        d["wsl_version"]    = "WSL2" if "microsoft" in sh("uname -r").lower() else "Native Linux"
        d["python_version"] = sys.version.split("\n")[0]
        d["python_impl"]    = platform.python_implementation()
        # Windows host info via /proc/version
        d["windows_host"]   = sh("grep -oP '(?<=Microsoft ).*' /proc/version 2>/dev/null || cat /proc/version | head -c 200")
        return d

    # ── CPU ───────────────────────────────────────────────────────────────────
    def collect_cpu(self) -> dict:
        d = {}
        d["model"]            = sh("grep 'model name' /proc/cpuinfo | head -1 | cut -d: -f2").strip()
        d["physical_cores"]   = sh("grep '^cpu cores' /proc/cpuinfo | head -1 | awk '{print $4}'") or \
                                sh("lscpu | grep 'Core(s) per socket' | awk '{print $NF}'")
        d["logical_cpus"]     = sh("nproc")
        d["sockets"]          = sh("lscpu | grep '^Socket(s)' | awk '{print $2}'")
        d["threads_per_core"] = sh("lscpu | grep 'Thread(s) per core' | awk '{print $NF}'")
        d["cpu_mhz"]          = sh("grep 'cpu MHz' /proc/cpuinfo | head -1 | awk '{print $4}'")

        # lscpu on Intel hybrid CPUs outputs e.g. "2611.200 MHz" or is blank —
        # fall back to /proc/cpuinfo-based max across all cores.
        def _lscpu_mhz(field: str) -> str:
            """Extract numeric MHz value from lscpu field (handles multi-instance output)."""
            raw = sh(f"lscpu | grep '{field}' | head -1")
            m = re.search(r"([\d.]+)\s*MHz", raw)
            return m.group(1) if m else ""

        def _lscpu_cache(field: str) -> str:
            """
            Extract cache size from lscpu field.
            Handles both '384 KiB' and '16x48K (16 instances)' formats.
            Returns a clean string like '48K' or '384 KiB' or '' if not found.
            """
            raw = sh(f"lscpu | grep -i '{field}' | head -1")
            if not raw:
                return ""
            # Format: "16x48K (16 instances)" — grab the size per instance (after 'x')
            m = re.search(r"\d+x(\S+)", raw)
            if m:
                return m.group(1)
            # Format: "384 KiB" or "24 MiB"
            m = re.search(r"([\d.]+\s*[KMG]i?B)", raw)
            if m:
                return m.group(1)
            # Format: plain number like "32768"
            m = re.search(r"([\d]+)", raw.split(":")[-1])
            return m.group(1) + " K" if m else ""

        cpu_max = _lscpu_mhz("CPU max MHz")
        if not cpu_max:
            # Hybrid CPUs (e.g. i5-13420H) don't expose max MHz in lscpu;
            # use the highest observed frequency across all cores from /proc/cpuinfo.
            cpu_max = sh(
                "grep 'cpu MHz' /proc/cpuinfo | awk '{print $4}' | sort -rn | head -1"
            )
        d["cpu_max_mhz"] = cpu_max

        cpu_min = _lscpu_mhz("CPU min MHz")
        if not cpu_min:
            cpu_min = sh(
                "grep 'cpu MHz' /proc/cpuinfo | awk '{print $4}' | sort -n | head -1"
            )
        d["cpu_min_mhz"] = cpu_min

        d["cache_l1d"]        = _lscpu_cache("L1d cache")
        d["cache_l1i"]        = _lscpu_cache("L1i cache")
        d["cache_l2"]         = _lscpu_cache("L2 cache")
        d["cache_l3"]         = _lscpu_cache("L3 cache")
        d["flags_avx"]        = "yes" if "avx" in sh("grep flags /proc/cpuinfo | head -1") else "no"
        d["flags_avx2"]       = "yes" if "avx2" in sh("grep flags /proc/cpuinfo | head -1") else "no"
        d["flags_sse4"]       = "yes" if "sse4" in sh("grep flags /proc/cpuinfo | head -1") else "no"

        # OpenMP max threads (compile tiny program)
        omp_src = r"""#include <omp.h>
#include <stdio.h>
int main(){ printf("%d\n", omp_get_max_threads()); return 0; }"""
        src_path = "/tmp/_omp_probe.c"
        with open(src_path, "w") as f:
            f.write(omp_src)
        omp_out = sh(f"gcc -fopenmp {src_path} -o /tmp/_omp_probe && /tmp/_omp_probe")
        d["omp_max_threads"] = omp_out if omp_out.isdigit() else "N/A"
        return d

    # ── RAM ───────────────────────────────────────────────────────────────────
    def collect_ram(self) -> dict:
        d = {}
        meminfo = {}
        for line in sh_lines("cat /proc/meminfo"):
            parts = line.split(":")
            if len(parts) == 2:
                key = parts[0].strip()
                val = parts[1].strip().split()[0]  # kB value
                try:
                    meminfo[key] = int(val)
                except ValueError:
                    meminfo[key] = parts[1].strip()

        def kb_to_gib(kb):
            try:
                return f"{int(kb) / (1024**2):.2f} GiB"
            except Exception:
                return "N/A"

        d["total"]          = kb_to_gib(meminfo.get("MemTotal",  0))
        d["available"]      = kb_to_gib(meminfo.get("MemAvailable", 0))
        d["free"]           = kb_to_gib(meminfo.get("MemFree",   0))
        d["buffers"]        = kb_to_gib(meminfo.get("Buffers",   0))
        d["cached"]         = kb_to_gib(meminfo.get("Cached",    0))
        d["swap_total"]     = kb_to_gib(meminfo.get("SwapTotal", 0))
        d["swap_free"]      = kb_to_gib(meminfo.get("SwapFree",  0))
        d["free_output"]    = sh("free -h")
        return d

    # ── GPU ───────────────────────────────────────────────────────────────────
    def collect_gpu(self) -> dict:
        d = {}
        # NVIDIA
        nv = sh("nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version,"
                "temperature.gpu,utilization.gpu,clocks.current.graphics,clocks.max.graphics "
                "--format=csv,noheader,nounits 2>/dev/null")
        if nv and "not found" not in nv.lower() and "error" not in nv.lower() and "N/A" not in nv[:5]:
            d["nvidia_smi_raw"] = nv
            gpus = []
            for line in nv.splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    gpu = {
                        "name"            : parts[0] if len(parts) > 0 else "N/A",
                        "vram_total_mib"  : parts[1] if len(parts) > 1 else "N/A",
                        "vram_free_mib"   : parts[2] if len(parts) > 2 else "N/A",
                        "driver_version"  : parts[3] if len(parts) > 3 else "N/A",
                        "temperature_c"   : parts[4] if len(parts) > 4 else "N/A",
                        "utilization_pct" : parts[5] if len(parts) > 5 else "N/A",
                        "clock_mhz"       : parts[6] if len(parts) > 6 else "N/A",
                        "clock_max_mhz"   : parts[7] if len(parts) > 7 else "N/A",
                    }
                    gpus.append(gpu)
            d["gpus"] = gpus
        else:
            d["gpus"] = []
            d["nvidia_smi_raw"] = "nvidia-smi not available or no NVIDIA GPU"

        # Generic GPU via lspci
        d["lspci_vga"] = sh("lspci 2>/dev/null | grep -i 'vga\\|3d\\|display' || echo 'lspci not available'")

        return d

    # ── Storage ───────────────────────────────────────────────────────────────
    def collect_storage(self) -> dict:
        d = {}
        d["df_human"]   = sh("df -h")
        d["lsblk"]      = sh("lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT 2>/dev/null | head -30")

        # Windows drives visible from WSL /mnt/
        mnt_drives = sh_lines("df -h /mnt/c /mnt/d /mnt/e 2>/dev/null")
        d["windows_drives"] = "\n".join(mnt_drives) if mnt_drives else "N/A"
        return d

    # ── Environment & Tools ───────────────────────────────────────────────────
    def collect_environment(self) -> dict:
        d = {}
        tools = {
            "gcc"    : "gcc --version 2>/dev/null | head -1",
            "g++"    : "g++ --version 2>/dev/null | head -1",
            "clang"  : "clang --version 2>/dev/null | head -1",
            "cmake"  : "cmake --version 2>/dev/null | head -1",
            "make"   : "make --version 2>/dev/null | head -1",
            "gnuplot": "gnuplot --version 2>/dev/null",
            "python3": "python3 --version 2>/dev/null",
            "git"    : "git --version 2>/dev/null",
        }
        tool_versions = {k: sh(v) or "(not found)" for k, v in tools.items()}
        d["tools"] = tool_versions

        # Key env vars
        d["env"] = {k: os.environ.get(k, "N/A")
                    for k in ["HOME", "USER", "SHELL", "LANG", "PATH", "WSL_DISTRO_NAME",
                               "WSLENV", "TERM", "LOGNAME"]}
        d["env"]["PATH"] = "<see WSL PATH above>"  # too long, skip inline

        # WSL version
        d["wsl_interop"] = sh("cat /proc/version | grep -o 'microsoft.*' | head -c 120")
        return d

    # ── Collect All ───────────────────────────────────────────────────────────
    def collect_all(self) -> dict:
        header("Collecting System Information")
        steps = [
            ("os",          "Operating System",   self.collect_os),
            ("cpu",         "CPU",                self.collect_cpu),
            ("ram",         "Memory (RAM)",        self.collect_ram),
            ("gpu",         "GPU",                self.collect_gpu),
            ("storage",     "Storage",            self.collect_storage),
            ("environment", "Environment & Tools",self.collect_environment),
        ]
        results = {}
        for key, label, fn in steps:
            subheader(label)
            try:
                data = fn()
                results[key] = data
                print(json.dumps(data, indent=2))
            except Exception as e:
                results[key] = {"error": str(e)}
                print(f"  [ERROR] {e}")
        return results


# ──────────────────────────────────────────────────────────────────────────────
# 2. Build & Run C++ Benchmarks
# ──────────────────────────────────────────────────────────────────────────────

class CppBenchmark:
    """Compile and run both K-Means variants; generate gnuplot chart."""

    def __init__(self, root: str, working: str):
        self.root    = root     # project root (Linux path)
        self.working = working  # output dir  (Linux path)

    # ── Compile ───────────────────────────────────────────────────────────────
    def _compile(self, src: str, out_name: str) -> tuple[bool, str]:
        """
        Compile by copying sources to /tmp (native Linux FS) first.
        This avoids the severe NTFS overhead of compiling directly from /mnt/c/.
        """
        tmp_dir = f"/tmp/kmeans_build_{out_name}"
        # Copy project sources to a native Linux temp dir
        copy_cmd = (
            f"rm -rf '{tmp_dir}' && mkdir -p '{tmp_dir}' && "
            f"cp '{self.root}/{src}' '{self.root}/Point.h' '{self.root}/Cluster.h' '{tmp_dir}/' 2>&1"
        )
        copy_result = sh(copy_cmd, timeout=30)

        out_path = os.path.join(self.working, out_name)
        compile_cmd = (
            f"cd '{tmp_dir}' && "
            f"g++ -O2 -fopenmp -I. '{src}' -o '{out_path}' 2>&1"
        )
        r = sh(compile_cmd, timeout=120)
        success = os.path.exists(out_path)
        return success, r

    # ── Run ───────────────────────────────────────────────────────────────────
    def _run_binary(self, name: str) -> tuple[str, float]:
        path = os.path.join(self.working, name)
        t0   = time.monotonic()
        # Run from /tmp to avoid NTFS issues with data.txt written by draw_chart_gnu()
        raw  = sh(f"cd /tmp && '{path}' 2>&1", timeout=900)
        wall = time.monotonic() - t0
        # Strip spurious "gnuplot: Permission denied" lines (Windows gnuplot.exe in PATH)
        out = "\n".join(
            line for line in raw.splitlines()
            if not ("gnuplot" in line.lower() and "permission denied" in line.lower())
        )
        return out, wall

    # ── Parse timing from C++ stdout ──────────────────────────────────────────
    @staticmethod
    def _parse(output: str) -> dict:
        t = {k: None for k in [
            "num_points", "num_clusters", "num_processors",
            "init_time_s", "total_time_s", "iter_time_s", "num_iterations"
        ]}
        for line in output.splitlines():
            if m := re.search(r"Number of points\s+(\d+)", line):
                t["num_points"] = int(m.group(1))
            if m := re.search(r"Number of clusters\s+(\d+)", line):
                t["num_clusters"] = int(m.group(1))
            if m := re.search(r"Number of processors:\s*(\d+)", line):
                t["num_processors"] = int(m.group(1))
            if "generated in:" in line:
                if m := re.search(r"([\d.]+)\s*seconds", line):
                    t["init_time_s"] = float(m.group(1))
            if "total time:" in line:
                if m := re.search(r"total time:\s*([\d.]+)\s*seconds", line):
                    t["total_time_s"] = float(m.group(1))
                if m := re.search(r"time per iteration:\s*([\d.]+)\s*seconds", line):
                    t["iter_time_s"] = float(m.group(1))
                if m := re.search(r"Number of iterations:\s*(\d+)", line):
                    t["num_iterations"] = int(m.group(1))
        return t

    # ── Gnuplot PNG ───────────────────────────────────────────────────────────
    def _gnuplot(self, seq_t: float, par_t: float,
                 points: int, clusters: int) -> str | None:
        if seq_t is None or par_t is None:
            return None

        speedup  = seq_t / par_t if par_t > 0 else 0
        png_path = os.path.join(self.working, "speedup_comparison.png")
        dat_path = os.path.join(self.working, "timing_data.dat")
        gnu_path = os.path.join(self.working, "plot_script.gnu")

        # Data file
        with open(dat_path, "w") as f:
            f.write("# label time\n")
            f.write(f"'Sequential' {seq_t:.6f}\n")
            f.write(f"'Parallel'   {par_t:.6f}\n")

        ymax = max(seq_t, par_t) * 1.4
        yoff = max(seq_t, par_t) * 0.05

        script = f"""set terminal png size 1000,650 enhanced font 'Helvetica,13'
set output '{png_path}'
set title 'K-Means: Sequential vs Parallel Total Time\\n({points:,} points, {clusters} clusters)' font ',15'
set ylabel 'Time (seconds)'
set xlabel 'Version'
set yrange [0:{ymax:.4f}]
set grid y lw 1 lt 0
set key off
set style data histograms
set style histogram cluster gap 3
set style fill solid 0.85 border -1
set boxwidth 0.6
set xtics rotate by 0
set label 1 sprintf('%.3f s', {seq_t:.4f}) at first 0, first {seq_t:.4f}+{yoff:.4f} center font ',12' textcolor rgb '#1a1a2e'
set label 2 sprintf('%.3f s', {par_t:.4f}) at first 1, first {par_t:.4f}+{yoff:.4f} center font ',12' textcolor rgb '#1a1a2e'
set label 3 sprintf('Speedup: {speedup:.2f}x', {speedup:.2f}) at first 0.5, {ymax*0.88:.4f} center font ',14' textcolor rgb '#c0392b'
plot '{dat_path}' using 2:xtic(1) lc rgb '#2980b9' notitle, \
     '' using 2 lc rgb '#e74c3c' notitle
"""
        with open(gnu_path, "w") as f:
            f.write(script)

        result = sh(f"gnuplot '{gnu_path}' 2>&1", timeout=30)
        if os.path.exists(png_path):
            return png_path
        else:
            print(f"  [gnuplot] {result}")
            return None

    # ── Main ──────────────────────────────────────────────────────────────────
    def run(self) -> dict:
        result = {
            "sequential": {"compile_ok": False, "compile_log": "", "output": "", "timing": {}, "wall_time": 0},
            "parallel"  : {"compile_ok": False, "compile_log": "", "output": "", "timing": {}, "wall_time": 0},
            "gnuplot_png": None,
        }

        header("Building & Running C++ Benchmarks")

        # Verify g++
        subheader("Compiler Check")
        print(f"  {sh('g++ --version | head -1')}")
        print(f"  OpenMP: {sh('echo | g++ -fopenmp -x c++ - -dM -E 2>/dev/null | grep _OPENMP || echo present')}")

        # ── Compile sequential
        subheader("Compiling main_sequential.cpp")
        ok, log = self._compile("main_sequential.cpp", "kmeans_sequential")
        result["sequential"]["compile_ok"]  = ok
        result["sequential"]["compile_log"] = log
        print(f"  {'✓ Success' if ok else '✗ FAILED'}" + (f": {log}" if not ok else ""))

        # ── Compile parallel
        subheader("Compiling main_parallel.cpp")
        ok2, log2 = self._compile("main_parallel.cpp", "kmeans_parallel")
        result["parallel"]["compile_ok"]  = ok2
        result["parallel"]["compile_log"] = log2
        print(f"  {'✓ Success' if ok2 else '✗ FAILED'}" + (f": {log2}" if not ok2 else ""))

        # ── Run sequential
        if result["sequential"]["compile_ok"]:
            subheader("Running Sequential K-Means (500,000 pts × 20 clusters × 20 iters)")
            print("  Please wait — this may take ~15–40 seconds…")
            out, wall = self._run_binary("kmeans_sequential")
            result["sequential"]["output"]    = out
            result["sequential"]["wall_time"] = wall
            result["sequential"]["timing"]    = self._parse(out)
            print(out)
            print(f"\n  ⏱  Wall clock: {wall:.2f} s")

        # ── Run parallel
        if result["parallel"]["compile_ok"]:
            subheader("Running Parallel K-Means (500,000 pts × 20 clusters × 20 iters)")
            print("  Please wait — this may take ~5–20 seconds…")
            out2, wall2 = self._run_binary("kmeans_parallel")
            result["parallel"]["output"]    = out2
            result["parallel"]["wall_time"] = wall2
            result["parallel"]["timing"]    = self._parse(out2)
            print(out2)
            print(f"\n  ⏱  Wall clock: {wall2:.2f} s")

        # ── Chart generation (gnuplot → matplotlib fallback)
        subheader("Generating Comparison Chart")
        st   = result["sequential"]["timing"].get("total_time_s")
        pt   = result["parallel"]["timing"].get("total_time_s")
        pts  = result["sequential"]["timing"].get("num_points") or 500000
        clus = result["sequential"]["timing"].get("num_clusters") or 20

        png = None
        gnuplot_bin = sh("which gnuplot 2>/dev/null")
        if gnuplot_bin:
            print(f"  Using gnuplot at {gnuplot_bin}", flush=True)
            png = self._gnuplot(st, pt, pts, clus)
        else:
            print("  gnuplot not found — using matplotlib fallback", flush=True)
            png = self._matplotlib_chart(st, pt, pts, clus)

        result["gnuplot_png"] = png
        if png:
            print(f"  ✓ Chart → {png}", flush=True)
        else:
            print("  ⚠  Chart not generated", flush=True)

        return result

    # ── Matplotlib fallback chart ─────────────────────────────────────────────
    def _matplotlib_chart(self, seq_t, par_t, points: int, clusters: int):
        if seq_t is None or par_t is None:
            return None
        try:
            import importlib, numpy as np
            mpl = importlib.import_module("matplotlib")
            mpl.use("Agg")
            plt = importlib.import_module("matplotlib.pyplot")

            speedup  = seq_t / par_t if par_t > 0 else 0
            png_path = os.path.join(self.working, "speedup_comparison.png")

            fig, ax = plt.subplots(figsize=(10, 6.5))
            fig.patch.set_facecolor("#f8f9fa")
            ax.set_facecolor("#ffffff")

            cats   = ["Sequential", "Parallel"]
            values = [seq_t, par_t]
            colors = ["#2980b9", "#e74c3c"]

            bars = ax.bar(cats, values, color=colors, width=0.45,
                          edgecolor="white", linewidth=1.5, zorder=3)

            for bar, val in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width() / 2,
                        val + max(values) * 0.02,
                        f"{val:.3f} s",
                        ha="center", va="bottom",
                        fontsize=13, fontweight="bold", color="#1a1a2e")

            ax.text(0.5, 0.92,
                    f"Speedup: {speedup:.2f}×",
                    transform=ax.transAxes,
                    ha="center", fontsize=14, color="#c0392b", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3",
                              facecolor="#fff3f3", edgecolor="#e74c3c", alpha=0.8))

            ax.set_ylabel("Time (seconds)", fontsize=12)
            ax.set_title(
                f"K-Means: Sequential vs Parallel Total Time\n"
                f"({points:,} pts, {clusters} clusters, 20 iterations)",
                fontsize=14, fontweight="bold", pad=12)
            ax.set_ylim(0, max(values) * 1.35)
            ax.grid(axis="y", linestyle="--", alpha=0.5, zorder=0)
            ax.spines[["top", "right"]].set_visible(False)

            plt.tight_layout()
            plt.savefig(png_path, dpi=150, bbox_inches="tight",
                        facecolor=fig.get_facecolor())
            plt.close(fig)
            return png_path

        except Exception as e:
            print(f"  matplotlib chart error: {e}", flush=True)
            return None



# ──────────────────────────────────────────────────────────────────────────────
# 3. Markdown Report Builder
# ──────────────────────────────────────────────────────────────────────────────

class ReportWriter:

    def __init__(self, sys_info: dict, bench: dict, path: str, ts: str):
        self.sys   = sys_info
        self.bench = bench
        self.path  = path
        self.ts    = ts

    @staticmethod
    def _table(headers: list, rows: list) -> str:
        col_w = [len(str(h)) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_w):
                    col_w[i] = max(col_w[i], len(str(cell)))
        def fmt(cells):
            return "| " + " | ".join(str(c).ljust(col_w[i]) for i, c in enumerate(cells)) + " |"
        sep = "|-" + "-|-".join("-" * w for w in col_w) + "-|"
        return "\n".join([fmt(headers), sep] + [fmt(r) for r in rows])

    def build(self) -> str:
        L = []
        a = L.append

        # Title
        a(f"# K-Means Parallel Benchmark Report")
        a(f"")
        a(f"> **Generated:** {self.ts}  ")
        a(f"> **Host:** {self.sys.get('os', {}).get('hostname', 'N/A')}  ")
        a(f"> **Distro:** {self.sys.get('os', {}).get('distro', 'N/A')} (WSL2)")
        a(f"")
        a(f"---")
        a(f"")

        # TOC
        a(f"## Table of Contents")
        a(f"")
        a(f"1. [System Information](#system-information)")
        a(f"2. [Build Results](#build-results)")
        a(f"3. [Benchmark Results](#benchmark-results)")
        a(f"4. [Comparison Chart](#comparison-chart)")
        a(f"5. [Raw Program Output](#raw-program-output)")
        a(f"")
        a(f"---")
        a(f"")

        # ── 1. System Info ────────────────────────────────────────────────────
        a(f"## System Information")
        a(f"")

        # OS
        os_d = self.sys.get("os", {})
        a(f"### Operating System")
        a(f"")
        a(self._table(["Property", "Value"], [
            ["Distribution",   os_d.get("distro",         "N/A")],
            ["Version",        os_d.get("distro_version", "N/A")],
            ["Kernel",         os_d.get("kernel",         "N/A")],
            ["Architecture",   os_d.get("arch",           "N/A")],
            ["Hostname",       os_d.get("hostname",       "N/A")],
            ["Runtime",        os_d.get("wsl_version",    "N/A")],
            ["Windows Host",   (os_d.get("windows_host", "N/A") or "N/A")[:80]],
            ["Python",         os_d.get("python_version", "N/A")],
        ]))
        a(f"")

        # CPU
        cpu_d = self.sys.get("cpu", {})
        a(f"### CPU")
        a(f"")
        a(self._table(["Property", "Value"], [
            ["Model",             cpu_d.get("model",            "N/A")],
            ["Physical Cores",    cpu_d.get("physical_cores",   "N/A")],
            ["Logical CPUs",      cpu_d.get("logical_cpus",     "N/A")],
            ["Sockets",           cpu_d.get("sockets",          "N/A")],
            ["Threads/Core",      cpu_d.get("threads_per_core", "N/A")],
            ["Current MHz",       cpu_d.get("cpu_mhz",          "N/A")],
            ["Max MHz",           cpu_d.get("cpu_max_mhz",      "N/A")],
            ["Min MHz",           cpu_d.get("cpu_min_mhz",      "N/A")],
            ["L1d Cache",         cpu_d.get("cache_l1d",        "N/A")],
            ["L1i Cache",         cpu_d.get("cache_l1i",        "N/A")],
            ["L2 Cache",          cpu_d.get("cache_l2",         "N/A")],
            ["L3 Cache",          cpu_d.get("cache_l3",         "N/A")],
            ["AVX",               cpu_d.get("flags_avx",        "N/A")],
            ["AVX2",              cpu_d.get("flags_avx2",       "N/A")],
            ["SSE4",              cpu_d.get("flags_sse4",       "N/A")],
            ["OMP Max Threads",   cpu_d.get("omp_max_threads",  "N/A")],
        ]))
        a(f"")

        # RAM
        ram_d = self.sys.get("ram", {})
        a(f"### Memory (RAM)")
        a(f"")
        a(self._table(["Property", "Value"], [
            ["Total RAM",    ram_d.get("total",      "N/A")],
            ["Available",    ram_d.get("available",  "N/A")],
            ["Free",         ram_d.get("free",       "N/A")],
            ["Buffers",      ram_d.get("buffers",    "N/A")],
            ["Cached",       ram_d.get("cached",     "N/A")],
            ["Swap Total",   ram_d.get("swap_total", "N/A")],
            ["Swap Free",    ram_d.get("swap_free",  "N/A")],
        ]))
        a(f"")
        a(f"```")
        a(ram_d.get("free_output", "N/A"))
        a(f"```")
        a(f"")

        # GPU
        gpu_d = self.sys.get("gpu", {})
        a(f"### GPU")
        a(f"")
        gpus = gpu_d.get("gpus", [])
        if gpus:
            for i, g in enumerate(gpus, 1):
                a(f"**GPU {i}: {g.get('name', 'N/A')}**")
                a(f"")
                a(self._table(["Property", "Value"], [
                    ["VRAM Total",      f"{g.get('vram_total_mib', 'N/A')} MiB"],
                    ["VRAM Free",       f"{g.get('vram_free_mib', 'N/A')} MiB"],
                    ["Driver Version",  g.get("driver_version", "N/A")],
                    ["Temperature",     f"{g.get('temperature_c', 'N/A')} °C"],
                    ["GPU Utilization", f"{g.get('utilization_pct', 'N/A')} %"],
                    ["Clock",           f"{g.get('clock_mhz', 'N/A')} MHz"],
                    ["Max Clock",       f"{g.get('clock_max_mhz', 'N/A')} MHz"],
                ]))
                a(f"")
        else:
            a(f"```")
            a(gpu_d.get("nvidia_smi_raw", "No GPU info available."))
            a(f"```")
            a(f"")

        lspci = gpu_d.get("lspci_vga", "")
        if lspci and "not available" not in lspci:
            a(f"**PCI Display Devices:**")
            a(f"```")
            a(lspci)
            a(f"```")
        a(f"")

        a(f"---")
        a(f"")



        # ── 2. Build Results ──────────────────────────────────────────────────
        a(f"## Build Results")
        a(f"")
        seq = self.bench.get("sequential", {})
        par = self.bench.get("parallel",   {})

        def badge(ok): return "✅ Success" if ok else "❌ Failed"

        a(self._table(
            ["Source File", "Status", "Compiler Notes"],
            [
                ["main_sequential.cpp", badge(seq.get("compile_ok")),
                 (seq.get("compile_log") or "Clean compile").strip()[:120]],
                ["main_parallel.cpp",   badge(par.get("compile_ok")),
                 (par.get("compile_log") or "Clean compile").strip()[:120]],
            ]
        ))
        a(f"")
        a(f"> **Compile flags:** `g++ -O2 -fopenmp -I.`")
        a(f"")
        a(f"---")
        a(f"")

        # ── 3. Benchmark Results ──────────────────────────────────────────────
        a(f"## Benchmark Results")
        a(f"")
        st = seq.get("timing", {})
        pt = par.get("timing", {})

        def fmt(v, suffix=""): return f"{v}{suffix}" if v is not None else "N/A"

        a(self._table(
            ["Metric", "Sequential", "Parallel"],
            [
                ["Points",             fmt(st.get("num_points")),    fmt(pt.get("num_points"))],
                ["Clusters",           fmt(st.get("num_clusters")),  fmt(pt.get("num_clusters"))],
                ["Iterations",         fmt(st.get("num_iterations")),fmt(pt.get("num_iterations"))],
                ["OMP Processors",     "1 (sequential)",             fmt(pt.get("num_processors"))],
                ["Init Time (s)",      fmt(st.get("init_time_s")),   fmt(pt.get("init_time_s"))],
                ["**Total Time (s)**", f"**{fmt(st.get('total_time_s'))}**",
                                       f"**{fmt(pt.get('total_time_s'))}**"],
                ["Iter Time (s)",      fmt(st.get("iter_time_s")),   fmt(pt.get("iter_time_s"))],
                ["Wall Time (s)",      f"{seq.get('wall_time', 0):.2f}", f"{par.get('wall_time', 0):.2f}"],
            ]
        ))
        a(f"")
        a(f"---")
        a(f"")

        # ── 4. Chart ─────────────────────────────────────────────────────────
        a(f"## Comparison Chart")
        a(f"")
        png = self.bench.get("gnuplot_png")
        if png and os.path.exists(png):
            a(f"Chart saved to: `{png}`")
            a(f"")
            a(f"![K-Means Sequential vs Parallel Speedup](./speedup_comparison.png)")
        else:
            a(f"_Chart was not generated._")
            a(f"")
            a(f"Install gnuplot and re-run: `sudo apt-get install -y gnuplot`")
        a(f"")
        a(f"---")
        a(f"")

        # ── 6. Raw Output ─────────────────────────────────────────────────────
        a(f"## Raw Program Output")
        a(f"")
        a(f"### Sequential (`main_sequential.cpp`)")
        a(f"```")
        a(seq.get("output") or "(no output)")
        a(f"```")
        a(f"")
        a(f"### Parallel (`main_parallel.cpp`)")
        a(f"```")
        a(par.get("output") or "(no output)")
        a(f"```")
        a(f"")
        a(f"---")
        a(f"*Generated by `run_benchmark.py` — K-Means PDC Project*")

        return "\n".join(L)

    def save(self) -> None:
        content = self.build()
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n  ✓ Report saved → {self.path}")


# ──────────────────────────────────────────────────────────────────────────────
# 4. Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{'#'*70}")
    print(f"  K-Means Benchmark Runner")
    print(f"  Started : {ts}")
    print(f"  Root    : {ROOT_DIR}")
    print(f"  Output  : {WORKING}")
    print(f"{'#'*70}")

    # Verify we're in WSL
    header("Verifying WSL Environment")
    uname = sh("uname -a")
    if "linux" in uname.lower():
        print(f"  ✓ Running inside Linux/WSL: {uname}")
    else:
        print(f"  ⚠  Unexpected environment: {uname}")

    # System info
    si       = SystemInfo()
    sys_data = si.collect_all()

    # Build & benchmark
    bench        = CppBenchmark(ROOT_DIR, WORKING)
    bench_result = bench.run()

    # Write report
    header("Writing Markdown Report")
    writer = ReportWriter(sys_data, bench_result, REPORT_OUT, ts)
    writer.save()

    # Summary
    print(f"\n{'='*70}")
    print(f"  COMPLETE")
    print(f"  Report  : {REPORT_OUT}")
    if bench_result.get("gnuplot_png"):
        print(f"  Chart   : {bench_result['gnuplot_png']}")
    seq_t = bench_result.get("sequential", {}).get("timing", {}).get("total_time_s")
    par_t = bench_result.get("parallel",   {}).get("timing", {}).get("total_time_s")
    if seq_t and par_t and par_t > 0:
        print(f"  Speedup : {seq_t/par_t:.4f}x  ({seq_t:.2f} s → {par_t:.2f} s)")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
