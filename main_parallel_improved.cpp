#include <iostream>
#include <cmath>
#include <fstream>
#include <chrono>
#include "Point.h"
#include "Cluster.h"
#include <omp.h>
#include <immintrin.h>

using namespace std;
using namespace std::chrono;

double max_range = 100000;
int num_point = 500000;
int num_cluster = 20;
int max_iterations = 20;

vector<Point> init_point(int num_point);
vector<Cluster> init_cluster(int num_cluster);
void compute_distance(vector<Point> &points, vector<Cluster> &clusters);
double euclidean_dist(Point point, Cluster cluster);
bool update_clusters(vector<Cluster> &clusters);
void draw_chart_gnu(vector<Point> &points);

int main() {

    printf("Number of points %d\n", num_point);
    printf("Number of clusters %d\n", num_cluster);
    printf("Number of processors: %d\n", omp_get_num_procs());

    srand(int(time(NULL)));

    double time_point1 = omp_get_wtime();
    printf("Starting initialization..\n");

    // FIX 1: init_point() is internally parallelised with omp parallel for
    // and rand_r(), so no omp sections imbalance or rand() data race here.
    printf("Creating points..\n");
    vector<Point> points = init_point(num_point);
    printf("Points initialized\n");

    printf("Creating clusters..\n");
    vector<Cluster> clusters = init_cluster(num_cluster);
    printf("Clusters initialized\n");

    double time_point2 = omp_get_wtime();
    double duration = time_point2 - time_point1;

    printf("Points and clusters generated in: %f seconds\n", duration);

    bool conv = true;
    int iterations = 0;

    printf("Starting iterate...\n");

    // The algorithm stops when iterations > max_iteration or clusters didn't move
    while (conv && iterations < max_iterations) {

        iterations++;

        compute_distance(points, clusters);

        conv = update_clusters(clusters);

        printf("Iteration %d done\n", iterations);
    }

    double time_point3 = omp_get_wtime();
    duration = time_point3 - time_point2;

    printf("Number of iterations: %d, total time: %f seconds, time per iteration: %f seconds\n",
           iterations, duration, duration / iterations);

    try {
        printf("Drawing the chart...\n");
        draw_chart_gnu(points);
    } catch (int e) {
        printf("Chart not available, gnuplot not found");
    }

    return 0;
}

// FIX 1a: Parallelised init with rand_r() (thread-safe, no global lock).
// FIX 1b: Direct in-place construction — no heap allocation / memory leak.
vector<Point> init_point(int num_point) {

    vector<Point> points(num_point);

#pragma omp parallel
    {
        // Each thread gets its own seed derived from its ID so results are
        // deterministic per-thread and there is no contention on rand().
        unsigned int seed = (unsigned int)omp_get_thread_num();

#pragma omp for schedule(guided)
        for (int i = 0; i < num_point; i++) {
            points[i] = Point(rand_r(&seed) % (int)max_range,
                              rand_r(&seed) % (int)max_range);
        }
    }

    return points;
}

// FIX 1b applied: no heap allocation / memory leak.
vector<Cluster> init_cluster(int num_cluster) {

    vector<Cluster> clusters(num_cluster);

    for (int i = 0; i < num_cluster; i++) {
        clusters[i] = Cluster(rand() % (int)max_range,
                              rand() % (int)max_range);
    }

    return clusters;
}

// FIX 2: Thread-local reduction — eliminates per-point atomic contention.
//
// main_parallel.cpp calls clusters[min_index].add_point(point) inside the
// parallel loop, which fires 3 omp atomics for EVERY one of the 500 000
// points per iteration (= 1 500 000 atomic ops / iteration).
//
// Here each thread accumulates into its own private arrays (zero contention)
// and merges into the shared Cluster objects exactly ONCE per thread via a
// short critical section (= num_threads * num_clusters ops / iteration).
// That is a ~3 000x reduction in synchronisation cost.

void compute_distance(vector<Point> &points, vector<Cluster> &clusters) {

    int points_size   = (int)points.size();
    int clusters_size = (int)clusters.size();

    // Pre-extract cluster coordinates as floats for AVX2 vectorization
    vector<float> cx(clusters_size);
    vector<float> cy(clusters_size);
    for (int c = 0; c < clusters_size; ++c) {
        cx[c] = (float)clusters[c].get_x_coord();
        cy[c] = (float)clusters[c].get_y_coord();
    }

#pragma omp parallel
    {
        // Thread-private accumulation arrays — allocated on the stack.
        vector<double> thr_sum_x(clusters_size, 0.0);
        vector<double> thr_sum_y(clusters_size, 0.0);
        vector<int>    thr_count(clusters_size, 0);

        // nowait lets fast threads proceed to the critical merge immediately.
// FIX 6: AVX2 Intrinsics (_mm256_sub_ps / _mm256_mul_ps) for distance calculation
#pragma omp for schedule(guided) nowait
        for (int i = 0; i < points_size; i++) {

            Point &point = points[i];
            float px = (float)point.get_x_coord();
            float py = (float)point.get_y_coord();

            // Broadcast the point's coordinates to all 8 slots of the AVX2 registers
            __m256 v_px = _mm256_set1_ps(px);
            __m256 v_py = _mm256_set1_ps(py);

            float min_distance = 1e30f;
            int   min_index    = -1;

            int j = 0;
            // Process 8 clusters at a time using 256-bit AVX2 vectors
            for (; j <= clusters_size - 8; j += 8) {
                // Load 8 cluster X and Y coordinates (unaligned load)
                __m256 v_cx = _mm256_loadu_ps(&cx[j]);
                __m256 v_cy = _mm256_loadu_ps(&cy[j]);

                // Compute differences: dx = px - cx, dy = py - cy
                __m256 v_dx = _mm256_sub_ps(v_px, v_cx);
                __m256 v_dy = _mm256_sub_ps(v_py, v_cy);

                // Compute squared differences: dx^2, dy^2
                __m256 v_dx2 = _mm256_mul_ps(v_dx, v_dx);
                __m256 v_dy2 = _mm256_mul_ps(v_dy, v_dy);

                // Sum the squared differences to get the squared distance
                __m256 v_dist2 = _mm256_add_ps(v_dx2, v_dy2);

                // Extract distances back to memory to find the minimum in this block
                // (Squared distance is fine for finding the nearest cluster, no sqrt needed)
                float dists[8];
                _mm256_storeu_ps(dists, v_dist2);

                for (int k = 0; k < 8; ++k) {
                    if (dists[k] < min_distance) {
                        min_distance = dists[k];
                        min_index    = j + k;
                    }
                }
            }

            // Handle any remaining clusters (if clusters_size is not a multiple of 8)
            for (; j < clusters_size; ++j) {
                float dx = px - cx[j];
                float dy = py - cy[j];
                float dist2 = dx * dx + dy * dy;

                if (dist2 < min_distance) {
                    min_distance = dist2;
                    min_index    = j;
                }
            }

            point.set_cluster_id(min_index);

            // Local accumulation — NO shared-memory writes in the hot path.
            thr_sum_x[min_index] += point.get_x_coord();
            thr_sum_y[min_index] += point.get_y_coord();
            thr_count[min_index]++;
        }

        // Merge: one critical section per thread (not per point).
        // add_batch() has no atomics; the critical directive is sufficient.
#pragma omp critical
        {
            for (int c = 0; c < clusters_size; c++) {
                if (thr_count[c] > 0) {
                    clusters[c].add_batch(thr_sum_x[c], thr_sum_y[c], thr_count[c]);
                }
            }
        }
    }
}

double euclidean_dist(Point point, Cluster cluster) {

    double distance = sqrt(pow(point.get_x_coord() - cluster.get_x_coord(), 2) +
                           pow(point.get_y_coord() - cluster.get_y_coord(), 2));

    return distance;
}

// For each cluster, update the coords. If only one cluster moves, conv will be TRUE.
bool update_clusters(vector<Cluster> &clusters) {

    bool conv = false;

    for (int i = 0; i < (int)clusters.size(); i++) {
        conv = clusters[i].update_coords();
        clusters[i].free_point();
    }

    return conv;
}

// Draw point plot with gnuplot
void draw_chart_gnu(vector<Point> &points) {

    ofstream outfile("data.txt");

    for (int i = 0; i < (int)points.size(); i++) {
        Point point = points[i];
        outfile << point.get_x_coord() << " " << point.get_y_coord() << " "
                << point.get_cluster_id() << std::endl;
    }

    outfile.close();
    system("gnuplot -p -e \"plot 'data.txt' using 1:2:3 with points palette notitle\"");
    remove("data.txt");
}
