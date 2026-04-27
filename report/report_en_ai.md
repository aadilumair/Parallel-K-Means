[cite_start]**K-Means Algorithm: Sequential and Parallel Versions** [cite: 1]
[cite_start]**Alessandro Sestini** [cite: 2]
[cite_start]ID Number 6226094 [cite: 2]
[cite_start]alessandro.sestini@stud.unifi.it [cite: 2]

---

### [cite_start]**Abstract** [cite: 3]
[cite_start]This mid-term paper focuses on the study and implementation of the **k-means algorithm** in both sequential and parallel versions[cite: 4]. [cite_start]The implementation was developed in **C++**, using **OpenMP** for the parallel portion[cite: 5]. [cite_start]Finally, performance analyses and comparisons between the two versions were conducted on a machine equipped with a **2-core Intel i5 processor**[cite: 6]. [cite_start]For the study and development of the program, profiling and thread sanitizing techniques were adopted[cite: 7]. [cite_start]To evaluate performance, the speedup obtained by moving from the sequential to the parallel version was measured: results show that the parallel version achieves an average **speedup of 2**—a linear speedup—which is what is expected for a 2-core machine[cite: 7].

---

### **1. [cite_start]Introduction** [cite: 8]

#### **1.1. [cite_start]The Algorithm** [cite: 9]
[cite_start]K-Means is a clustering algorithm designed to divide points in space into **K groups** based on the characteristics of the points themselves[cite: 10]. [cite_start]The final objective is to have points belonging to the same class in the same cluster (meaning they must be similar and have a small distance between them), while points in different clusters must belong to different classes (meaning they should not be similar and have a relatively large distance)[cite: 11].

[cite_start]For simplicity, this paper generates random points in **2D space**, though it is possible to generalize to more dimensions using the same reasoning[cite: 12]. [cite_start]The algorithm is straightforward and consists of a few steps: [cite: 13]
* [cite_start]**Step 1**: Generate **N** random points in space[cite: 14].
* [cite_start]**Step 2**: Generate **K** centroids representing the K clusters[cite: 15].
* [cite_start]**Initial Step**: In the initialization phase, the cluster will contain only the centroid[cite: 16].
* [cite_start]**Step 3**: For every point, calculate the distance to all K clusters and assign the point to the **nearest cluster**[cite: 17].
* [cite_start]**Step 4**: Update the centroid's characteristics, specifically its position within the cluster[cite: 18].
* [cite_start]**Step 5**: Repeat from Step 3 until the centroids no longer move or a maximum number of iterations is reached[cite: 19].

#### **1.2. [cite_start]Parameters** [cite: 21]
The algorithm requires several parameters:
* [cite_start]The number **K** of clusters must be known and chosen a priori[cite: 22]. [cite_start]Alternatively, complex solutions can be used to find the best K, such as repeating the algorithm for different K values and choosing the one that minimizes the distance between centroids[cite: 23]. [cite_start]This paper uses a **fixed number of clusters**[cite: 24].
* [cite_start]The definition and initialization of centroids: in a 2D Euclidean space, the centroid is defined by the **average** of the points belonging to that cluster[cite: 25]. [cite_start]This would not be possible in a non-Euclidean space[cite: 26].
* [cite_start]Initial centroid selection: this program selects **K random points** in space[cite: 27].
* [cite_start]Distance metric: **Euclidean distance** is used in this project[cite: 28].
* [cite_start]Maximum iterations: this varies based on the nature and number of points and clusters[cite: 29].

#### **1.3. [cite_start]Considerations** [cite: 30]
[cite_start]The algorithm **converges very quickly**, although it does not guarantee finding the global optimum[cite: 31]. [cite_start]The quality of the final result depends largely on the initial number and position of the clusters[cite: 32]. [cite_start]Since clusters are initialized randomly, repeating the algorithm twice on the same points does not guarantee the same result[cite: 39].

---

### **2. [cite_start]Implementation** [cite: 40]
[cite_start]The implementation was written in C++ and extended with OpenMP[cite: 41, 42].

#### **2.1. [cite_start]Classes** [cite: 43]
Two main classes were created:
1.  [cite_start]**Point**: Composed of three attributes: `double x_coord`, `double y_coord`, and `int cluster_id`[cite: 45, 46]. [cite_start]During initialization, all points are assigned to cluster 0[cite: 47].
2.  [cite_start]**Cluster**: Composed of `x_coord`, `y_coord`, and an integer `size` indicating the number of points in the cluster[cite: 48]. [cite_start]It includes methods like `add_point()`, `free_point()`, and `update_coords()` to update centroid coordinates and verify movement[cite: 49].

#### [cite_start]**2.2. main_sequential.cpp** [cite: 50]
[cite_start]Points and clusters are stored in `std::vector` objects from the STL library[cite: 52]. [cite_start]The implementation focuses on two fundamental functions: `compute_distance()` and `update_clusters()`[cite: 51].

#### [cite_start]**2.3. compute_distance** [cite: 37]
[cite_start]Most of the algorithm's complexity is contained in this function[cite: 78]. [cite_start]For every point, it calculates the Euclidean distance to every cluster and assigns the point to the nearest one[cite: 78]. [cite_start]This involves processing hundreds of thousands of points with approximately 20-30 clusters[cite: 79]. [cite_start]Centroid variables are updated during this process to facilitate later coordinate updates[cite: 80].

#### [cite_start]**2.4. update_cluster** [cite: 81]
[cite_start]This function updates centroid coordinates based on the points assigned to the cluster during the iteration[cite: 88]. [cite_start]If even one cluster moves, the function returns `true` (continuing the loop); otherwise, it returns `false`, terminating the algorithm[cite: 89].

---

### **3. [cite_start]Parallel Version** [cite: 90]
[cite_start]The `compute_distance()` function is highly parallelizable because operations for each point are independent[cite: 91, 92, 93]. [cite_start]Profiling shows that the CPU spends the vast majority of its time in this first loop[cite: 95].

| Function | Time |
| :--- | :--- |
| `compute_distance()` | 1.075 s |
| `update_cluster()` | 0.000001 s |

[cite_start]**Table 1: Profiling of the sequential algorithm** [cite: 129]

#### **3.1. [cite_start]Parallel compute_distance** [cite: 131]
[cite_start]A `parallel for` was applied to the outermost loop using OpenMP[cite: 132].
* [cite_start]`min_distance` and `min_index` are **private** to each thread[cite: 132].
* [cite_start]`points_size` and `clusters_size` are **firstprivate** so each thread has a local copy[cite: 133].
* [cite_start]The points and clusters arrays remain **shared**[cite: 134].
* [cite_start]Since multiple threads may access the same cluster to update variables, the update section is defined as **critical**[cite: 98, 122].

#### **3.2. [cite_start]Other Considerations** [cite: 136]
[cite_start]Parallelization was also applied to cluster and point initialization, though the performance gain was negligible due to the simplicity of the operations[cite: 138]. [cite_start]The `update_cluster()` function was left sequential because it iterates over only a few dozen elements; the overhead of managing threads would exceed the time saved[cite: 139, 140, 143].

---

### **4. [cite_start]Experiments** [cite: 144]
[cite_start]Experiments compared completion times of both versions on a 2-core machine, varying the number of points and clusters while keeping iterations fixed at 20[cite: 145, 146].

| Points | Clusters | Total Sequential Time | Iteration Sequential Time | Total Parallel Time | Iteration Parallel Time |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 100,000 | 10 | 3.57 s | 0.18 s | 2.74 s | 0.13 s |
| 100,000 | 20 | 5.68 s | 0.28 s | 4.04 s | 0.20 s |
| 500,000 | 10 | 12.75 s | 0.64 s | 6.40 s | 0.37 s |
| 500,000 | 20 | 22.40 s | 1.12 s | 12.13 s | 0.61 s |
| 1,000,000 | 10 | 22.74 s | 1.13 s | 12.13 s | 0.61 s |
| 1,000,000 | 20 | 40.66 s | 2.03 s | 21.40 s | 1.20 s |

[cite_start]**Table 2: Experiment table** [cite: 142]

[cite_start]The speedup increases as the number of points and clusters increase[cite: 147]. [cite_start]A linear speedup (halved completion time) was achieved for larger datasets, while the overhead of thread creation is more visible for smaller point counts[cite: 148]. [cite_start]Results were visualized using **gnuplot**[cite: 149].

---

### **5. [cite_start]Notes** [cite: 150]
[cite_start]Visualizing results requires the **gnuplot** library[cite: 151]. [cite_start]The program uses a `system` call to plot points saved in a temporary `data.txt` file, which is deleted after viewing[cite: 152].