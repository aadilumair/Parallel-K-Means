# K-Means Parallel Benchmark Report

> **Generated:** 2026-05-06 19:02:27  
> **Host:** aadil-umair-Nitro-ANV15-51  
> **Distro:** Ubuntu 24.04.1 LTS (WSL2)

---

## Table of Contents

1. [System Information](#system-information)
2. [Build Results](#build-results)
3. [Benchmark Results](#benchmark-results)
4. [Comparison Chart](#comparison-chart)
5. [Raw Program Output](#raw-program-output)

---

## System Information

### Operating System

| Property     | Value                                                                            |
|--------------|----------------------------------------------------------------------------------|
| Distribution | Ubuntu 24.04.1 LTS                                                               |
| Version      | 24.04                                                                            |
| Kernel       | 6.8.0-41-generic                                                                 |
| Architecture | x86_64                                                                           |
| Hostname     | aadil-umair-Nitro-ANV15-51                                                       |
| Runtime      | Native Linux                                                                     |
| Windows Host | Linux version 6.8.0-41-generic (buildd@lcy02-amd64-100) (x86_64-linux-gnu-gcc-13 |
| Python       | 3.12.3 (main, Jul 31 2024, 17:43:48) [GCC 13.2.0]                                |

### CPU

| Property        | Value                                |
|-----------------|--------------------------------------|
| Model           | 13th Gen Intel(R) Core(TM) i5-13420H |
| Physical Cores  | 8                                    |
| Logical CPUs    | 12                                   |
| Sockets         | 1                                    |
| Threads/Core    | 2                                    |
| Current MHz     | 1754.629                             |
| Max MHz         | 1900.582                             |
| Min MHz         | 400.000                              |
| L1d Cache       | 320 KiB                              |
| L1i Cache       | 384 KiB                              |
| L2 Cache        | 7 MiB                                |
| L3 Cache        | 12 MiB                               |
| AVX             | yes                                  |
| AVX2            | yes                                  |
| SSE4            | yes                                  |
| OMP Max Threads | 12                                   |

### Memory (RAM)

| Property   | Value     |
|------------|-----------|
| Total RAM  | 15.33 GiB |
| Available  | 9.66 GiB  |
| Free       | 6.11 GiB  |
| Buffers    | 0.11 GiB  |
| Cached     | 3.82 GiB  |
| Swap Total | 7.81 GiB  |
| Swap Free  | 7.81 GiB  |

```
total        used        free      shared  buff/cache   available
Mem:            15Gi       5.7Gi       6.1Gi       964Mi       4.1Gi       9.7Gi
Swap:          7.8Gi          0B       7.8Gi
```

### GPU

**GPU 1: NVIDIA GeForce RTX 3050 6GB Laptop GPU**

| Property        | Value      |
|-----------------|------------|
| VRAM Total      | 6144 MiB   |
| VRAM Free       | 5933 MiB   |
| Driver Version  | 535.183.01 |
| Temperature     | 43 °C      |
| GPU Utilization | 0 %        |
| Clock           | 1432 MHz   |
| Max Clock       | 2100 MHz   |

**PCI Display Devices:**
```
0000:00:02.0 VGA compatible controller: Intel Corporation Raptor Lake-P [UHD Graphics] (rev 04)
0000:01:00.0 VGA compatible controller: NVIDIA Corporation GN20-P0-R-K2 [GeForce RTX 3050 6GB Laptop GPU] (rev a1)
10000:e0:06.2 PCI bridge: Intel Corporation Device a73d
```

---

## Build Results

| Source File                | Status    | Compiler Notes                                                                                                           |
|----------------------------|-----------|--------------------------------------------------------------------------------------------------------------------------|
| main_sequential.cpp        | ✅ Success | main_sequential.cpp: In function ‘void draw_chart_gnu(std::vector<Point>&)’:
main_sequential.cpp:193:11: warning: ignori |
| main_parallel.cpp          | ✅ Success | main_parallel.cpp: In function ‘void draw_chart_gnu(std::vector<Point>&)’:
main_parallel.cpp:214:11: warning: ignoring r |
| main_parallel_improved.cpp | ✅ Success | main_parallel_improved.cpp: In function ‘void draw_chart_gnu(std::vector<Point>&)’:
main_parallel_improved.cpp:221:11: w |

> **Compile flags:** `g++ -O2 -fopenmp -I.`

---

## Benchmark Results

| Metric             | Sequential     | Parallel    | Parallel Improved |
|--------------------|----------------|-------------|-------------------|
| Points             | 500000         | 500000      | 500000            |
| Clusters           | 20             | 20          | 20                |
| Iterations         | 20             | 20          | 20                |
| OMP Processors     | 1 (sequential) | 12          | 12                |
| Init Time (s)      | 0.028068       | 0.032273    | 0.006106          |
| **Total Time (s)** | **0.449621**   | **0.63608** | **0.085442**      |
| Iter Time (s)      | 0.022481       | 0.031804    | 0.004272          |
| Wall Time (s)      | 1.01           | 1.21        | 0.63              |
| Speedup vs Seq     | 1.00x          | 0.71x       | 5.26x             |

---

## Comparison Chart

_Chart was not generated._

Install gnuplot and re-run: `sudo apt-get install -y gnuplot`

---

## Raw Program Output

### Sequential (`main_sequential.cpp`)
```
sh: 1: gnuplot: not found
Number of points 500000
Number of clusters 20
Starting initialization..
Creating points..
Points initialized 
Creating clusters..
Clusters initialized 
Points and clusters generated in: 0.028068 seconds
Starting iterate..
Iteration 1 done 
Iteration 2 done 
Iteration 3 done 
Iteration 4 done 
Iteration 5 done 
Iteration 6 done 
Iteration 7 done 
Iteration 8 done 
Iteration 9 done 
Iteration 10 done 
Iteration 11 done 
Iteration 12 done 
Iteration 13 done 
Iteration 14 done 
Iteration 15 done 
Iteration 16 done 
Iteration 17 done 
Iteration 18 done 
Iteration 19 done 
Iteration 20 done 
Number of iterations: 20, total time: 0.449621 seconds, time per iteration: 0.022481 seconds
Drawing the chart...
```

### Parallel (`main_parallel.cpp`)
```
sh: 1: gnuplot: not found
Number of points 500000
Number of clusters 20
Number of processors: 12
Starting initialization..
Creating points..
Creating clusters..
Clusters initialized 
Points initialized 
Points and clusters generated in: 0.032273 seconds
Starting iterate...
Iteration 1 done 
Iteration 2 done 
Iteration 3 done 
Iteration 4 done 
Iteration 5 done 
Iteration 6 done 
Iteration 7 done 
Iteration 8 done 
Iteration 9 done 
Iteration 10 done 
Iteration 11 done 
Iteration 12 done 
Iteration 13 done 
Iteration 14 done 
Iteration 15 done 
Iteration 16 done 
Iteration 17 done 
Iteration 18 done 
Iteration 19 done 
Iteration 20 done 
Number of iterations: 20, total time: 0.636080 seconds, time per iteration: 0.031804 seconds
Drawing the chart...
```

### Parallel Improved (`main_parallel_improved.cpp`)
```
sh: 1: gnuplot: not found
Number of points 500000
Number of clusters 20
Number of processors: 12
Starting initialization..
Creating points..
Points initialized
Creating clusters..
Clusters initialized
Points and clusters generated in: 0.006106 seconds
Starting iterate...
Iteration 1 done
Iteration 2 done
Iteration 3 done
Iteration 4 done
Iteration 5 done
Iteration 6 done
Iteration 7 done
Iteration 8 done
Iteration 9 done
Iteration 10 done
Iteration 11 done
Iteration 12 done
Iteration 13 done
Iteration 14 done
Iteration 15 done
Iteration 16 done
Iteration 17 done
Iteration 18 done
Iteration 19 done
Iteration 20 done
Number of iterations: 20, total time: 0.085442 seconds, time per iteration: 0.004272 seconds
Drawing the chart...
```

---
*Generated by `run_benchmark.py` — K-Means PDC Project*