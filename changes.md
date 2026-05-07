# Changes: `main_parallel_improved.cpp` vs `main_parallel.cpp`

## Overview

`main_parallel.cpp` introduces OpenMP parallelism but is often **slower** than the
sequential version due to several fundamental mistakes. `main_parallel_improved.cpp`
fixes each of those mistakes. The supporting method `Cluster::add_batch()` was added
to `Cluster.h` to enable the thread-local reduction pattern.

---

## Fix 1 — Removed Unbalanced `omp sections` from Initialisation

### Problem (`main_parallel.cpp`)
```cpp
#pragma omp parallel
{
    #pragma omp sections
    {
        #pragma omp section { points  = init_point(num_point);   }  // ~500 000 items
        #pragma omp section { clusters = init_cluster(num_cluster); } // ~20 items
    }
}
```
- Only **2 sections** execute, so all threads beyond the first two are idle.
- The two sections are wildly **imbalanced** (500 000 points vs 20 clusters).
- `rand()` inside `init_point` uses **global state** — calling it from a parallel
  section causes a data race and implicit serialisation via an internal libc lock.

### Fix (`main_parallel_improved.cpp`)
- `init_point()` is **internally parallelised** with `#pragma omp parallel for` and
  uses `rand_r(&seed)` with a per-thread seed — fully thread-safe, no lock contention.
- `init_cluster()` (20 items) is left sequential — the overhead of a parallel region
  for 20 iterations would outweigh any benefit.
- The `omp sections` block in `main()` is removed entirely.

---

## Fix 2 — Eliminated Heap Allocation Inside Init Loops

### Problem (`main_parallel.cpp`)
```cpp
for (int i = 0; i < num_point; i++) {
    Point* point = new Point(...);   // heap alloc — malloc lock contention
    ptr[i] = *point;                 // copy
    // 'point' is never deleted — MEMORY LEAK
}
```
Every iteration allocates on the heap. In a multithreaded context the allocator's
internal lock serialises these calls. Additionally, the pointer is **never freed**,
leaking 500 000 × sizeof(Point) bytes per run.

### Fix (`main_parallel_improved.cpp`)
```cpp
points[i] = Point(rand_r(&seed) % (int)max_range,
                  rand_r(&seed) % (int)max_range);
```
Direct in-place construction with no heap allocation, no memory leak.

---

## Fix 3 — Thread-Local Reduction in `compute_distance()` (Critical Fix)

This is the **root cause** of the parallel version being slower than sequential.

### Problem (`main_parallel.cpp`)
```cpp
#pragma omp for schedule(static)
for (int i = 0; i < points_size; i++) {
    // ... find nearest cluster ...
    clusters[min_index].add_point(point);  // ← HOT PATH
}
```

Inside `Cluster::add_point()`:
```cpp
void add_point(Point point) {
    #pragma omp atomic   new_x_coord += ...;  // serialised
    #pragma omp atomic   new_y_coord += ...;  // serialised
    #pragma omp atomic   size++;              // serialised
}
```

- **500 000 × 3 = 1 500 000 atomic operations per iteration.**
- All threads compete to write to the same ~20 cluster objects → massive contention.
- Atomics are implemented via hardware bus locks — far more expensive than plain writes.
- Adjacent clusters share CPU cache lines → **false sharing** causes additional
  cache-coherency traffic between cores even for different clusters.

### Fix (`main_parallel_improved.cpp`)

Each thread accumulates into **private stack arrays** with zero shared-memory writes
inside the hot path. After finishing its chunk, each thread merges into the shared
clusters exactly **once** via a short `#pragma omp critical` block.

```cpp
#pragma omp parallel
{
    vector<double> thr_sum_x(clusters_size, 0.0);  // private per thread
    vector<double> thr_sum_y(clusters_size, 0.0);
    vector<int>    thr_count(clusters_size, 0);

    #pragma omp for schedule(static) nowait
    for (int i = 0; i < points_size; i++) {
        // ... find nearest cluster ...
        point.set_cluster_id(min_index);
        thr_sum_x[min_index] += point.get_x_coord();  // NO atomics
        thr_sum_y[min_index] += point.get_y_coord();
        thr_count[min_index]++;
    }

    #pragma omp critical          // entered once per thread, not once per point
    {
        for (int c = 0; c < clusters_size; c++)
            if (thr_count[c] > 0)
                clusters[c].add_batch(thr_sum_x[c], thr_sum_y[c], thr_count[c]);
    }
}
```

| Metric | `main_parallel.cpp` | `main_parallel_improved.cpp` |
|---|---|---|
| Atomic ops / iteration | 1 500 000 | `num_threads × num_clusters × 3` ≈ 480 |
| Sync cost per point | 3 atomics (bus locks) | ~0 (local write) |
| False sharing | Yes (shared cluster array) | No (private arrays in hot path) |
| Critical sections / iteration | 0 (atomics used instead) | `num_threads` (≈ 8–16) |

Reduction in synchronisation operations: **~3 000×**.

---

## Fix 4 — Added `nowait` to the Inner `omp for`

```cpp
#pragma omp for schedule(guided) nowait
```

Without `nowait`, all threads block at an implicit barrier after the loop before
proceeding. With `nowait`, threads that finish their chunk early can immediately
enter the `critical` merge section, overlapping the merge cost with the remaining
work of slower threads.


2.7437x speedup
---

## Fix 5 — Hybrid-Aware Load Balancing (`schedule(guided)`)

### Problem
Static scheduling (`schedule(static)`) divides iterations equally among threads. On modern hybrid architectures (like Intel P-cores and E-cores, or Apple Silicon P/E cores), this causes fast P-cores to finish their chunks early and idle while waiting for slower E-cores to finish their equally-sized chunks.

### Fix
Using `schedule(guided)` dynamically assigns chunks to threads. The chunk size starts large (reducing scheduling overhead) and exponentially decreases. This ensures that:
1. Fast P-cores claim more of the larger chunks early on.
2. Slower E-cores work on smaller chunks.
3. As the loop nears completion, the chunks are small enough that fast threads can "steal" remaining work if slow threads are lagging behind, drastically reducing overall wait time.

---

## Supporting Change — `Cluster::add_batch()` in `Cluster.h`

A new non-atomic batch accumulator was added to support Fix 3:

```cpp
void add_batch(double sum_x, double sum_y, int count) {
    new_x_coord += sum_x;
    new_y_coord += sum_y;
    size += count;
}
```

No atomics are needed here because `add_batch` is only ever called from inside a
`#pragma omp critical` section, which already provides mutual exclusion.


Speedup 5.2623x
---

## Fix 6 — Inlined Squared-Distance (no `sqrt`, no type conversion)

### What was tried and why it regressed (4.3x → 4.3x)

Two previous attempts both caused a regression from 5.2x → 4.3x:

| Attempt | Problem |
|---|---|
| Manual `_mm256_storeu_ps` + scalar scan | **Store-to-load forwarding stall** — writing SIMD results to memory then immediately reading back caused a multi-cycle pipeline stall every 8 clusters |
| `float cx[]/cy[]` arrays + compiler autovectorization | **Benchmark compiles with `-O2 -fopenmp`** (not `-O3 -mavx2`), so no autovectorization fires — double→float conversion for 500k points per iteration added overhead with zero SIMD benefit |

The benchmark compile command (from `run_benchmark.py` line 316):
```python
f"g++ -O2 -fopenmp -I. '{src}' -o '{out_path}'"
```

### Final Fix

Remove all type conversions and heap allocations. Keep the one optimization that works at **any** optimization level: **comparing squared distances instead of actual distances**, eliminating `sqrt()` from 500,000 × 20 = 10 million inner-loop calls per iteration.

```cpp
// Before (euclidean_dist used sqrt + pow):
double distance = sqrt(pow(px - cx, 2) + pow(py - cy, 2));  // expensive

// After — same nearest-cluster result, no sqrt:
double dist2 = dx * dx + dy * dy;   // dist² preserves ordering
```

Also: cluster coords are now read directly from `clusters[j]`, avoiding two separate heap-allocated float vectors that were being constructed and destroyed every `compute_distance()` call (20 times total).

Speedup: 5.4191x

---

## Summary of All Changes

| # | Location | Change | Root Problem Fixed |
|---|---|---|---|
| 1 | `main()` | Removed `omp sections`; init called sequentially | Imbalanced work, idle threads |
| 2 | `init_point()` | `rand_r(&seed)` + `omp parallel for` | `rand()` data race & lock contention |
| 3 | `init_point()` / `init_cluster()` | Direct construction, no `new` | Memory leak + malloc lock contention |
| 4 | `compute_distance()` | Thread-local reduction + `omp critical` merge | 1.5M atomics / iteration |
| 5 | `compute_distance()` | `nowait` on `omp for` | Unnecessary barrier stall |
| 6 | `init_point()` / `compute_distance()` | `schedule(guided)` | Load imbalance on P/E hybrid architectures |
| 7 | `compute_distance()` | Inlined `dx*dx + dy*dy` instead of `sqrt(pow(...))` | `sqrt` + `pow` overhead in 10M inner-loop calls/iter |
| 8 | `Cluster.h` | `add_batch()` without atomics | Supports Fix 4 |
