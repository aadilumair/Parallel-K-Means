#include <iostream>
#include <cmath>
#include <fstream>
#include <chrono>
#include "Point.h"
#include "Cluster.h"
#include <omp.h>
#include <cstdlib>     // setenv — for OMP_PLACES / OMP_PROC_BIND

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

    // FIX 7: Thread Affinity & Pinning
    // Set before ANY omp parallel region so libgomp reads them on first team
    // creation. OMP_PLACES=cores → one place per physical core (ignores HT
    // siblings). OMP_PROC_BIND=spread → distribute threads across all places
    // evenly, preventing the OS from migrating threads between P-cores and
    // E-cores and eliminating the associated cold-cache penalties.
    setenv("OMP_PLACES",    "cores",  1);   // 1 = don't overwrite if already set
    setenv("OMP_PROC_BIND", "spread", 1);

    printf("Number of points %d\n", num_point);
    printf("Number of clusters %d\n", num_cluster);
    printf("Number of processors: %d\n", omp_get_num_procs());
    printf("OMP_PLACES: %s\n",    getenv("OMP_PLACES")    ? getenv("OMP_PLACES")    : "(not set)");
    printf("OMP_PROC_BIND: %s\n", getenv("OMP_PROC_BIND") ? getenv("OMP_PROC_BIND") : "(not set)");

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

    // FIX 7: proc_bind(spread) — enforce spread binding in the init region too.
    // env vars are already set; the clause is a belt-and-suspenders guarantee.
#pragma omp parallel proc_bind(spread)
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

    // FIX 7: proc_bind(spread) — same affinity policy as the init region.
#pragma omp parallel proc_bind(spread)
    {
        // Thread-private accumulation arrays — allocated on the stack.
        vector<double> thr_sum_x(clusters_size, 0.0);
        vector<double> thr_sum_y(clusters_size, 0.0);
        vector<int>    thr_count(clusters_size, 0);

        // FIX 6: Inline squared-distance comparison — eliminates sqrt() from
        // the 500k × 20 inner loop without any type conversion or heap allocation.
        // Comparing dist² gives the same nearest-cluster result as comparing dist.
        // No float arrays: benchmark compiles with -O2 (no AVX autovectorization),
        // so double→float conversion would add overhead with zero SIMD benefit.
#pragma omp for schedule(guided) nowait
        for (int i = 0; i < points_size; i++) {

            Point &point = points[i];
            double px = point.get_x_coord();
            double py = point.get_y_coord();

            double min_dist2 = 1e300;
            int    min_index = 0;

            for (int j = 0; j < clusters_size; ++j) {
                double dx    = px - clusters[j].get_x_coord();
                double dy    = py - clusters[j].get_y_coord();
                double dist2 = dx * dx + dy * dy;   // no sqrt

                if (dist2 < min_dist2) {
                    min_dist2 = dist2;
                    min_index = j;
                }
            }

            point.set_cluster_id(min_index);

            // Local accumulation — NO shared-memory writes in the hot path.
            thr_sum_x[min_index] += px;
            thr_sum_y[min_index] += py;
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
