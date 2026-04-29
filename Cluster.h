#ifndef K_MEANS_MIO_CPP_CLUSTER_H
#define K_MEANS_MIO_CPP_CLUSTER_H

#include <queue>
#include "Point.h"

class Cluster {
public:
    Cluster(double x_coord, double y_coord){
        new_x_coord = 0;
        new_y_coord = 0;
        size = 0;
        this->x_coord = x_coord;
        this->y_coord = y_coord;
    }

    Cluster(){
        new_x_coord = 0;
        new_y_coord = 0;
        size = 0;
        this->x_coord = 0;
        this->y_coord = 0;
    }

    // Lock-free method for the sequential run
    void add_point(Point point){
        new_x_coord += point.get_x_coord();
        new_y_coord += point.get_y_coord();
        size++;
    }

    // Thread-Local Reduction helper for the parallel run
    void add_local_sums(double sum_x, double sum_y, int count){
        new_x_coord += sum_x;
        new_y_coord += sum_y;
        size += count;
    }

    void free_point(){
        this->size = 0;
        this->new_x_coord = 0;
        this->new_y_coord = 0;
    }

    double get_x_coord(){
        return this->x_coord;
    }

    double get_y_coord(){
        return this->y_coord;
    }

    bool update_coords(){
        // Safety check to prevent division by zero if a cluster goes empty
        if(this->size == 0) return true; 

        if(this->x_coord == new_x_coord/this->size && this->y_coord == new_y_coord/this->size){
            return false;
        }

        this->x_coord = new_x_coord/this->size;
        this->y_coord = new_y_coord/this->size;

        return true;
    }

private:
    double x_coord;
    double y_coord;
    double new_x_coord;
    double new_y_coord;
    int size;
};

#endif //K_MEANS_MIO_CPP_CLUSTER_H