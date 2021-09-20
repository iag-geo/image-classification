
create schema if not exists data_science;
alter schema data_science owner to postgres;

drop table if exists data_science.swimming_pool_labels;
create table data_science.swimming_pool_labels (
    file_path text NOT NULL,
    land_parcel_id text,
    gnaf_pid text,
    latitude numeric(8,6) NOT NULL,
    longitude numeric(9,6) NOT NULL,
    point_geom geometry(Point, 4283) NOT NULL,
    geom geometry(Polygon, 4283) NOT NULL
);

alter table data_science.swimming_pool_labels owner to postgres;


drop table if exists data_science.swimming_pool_images;
create table data_science.swimming_pool_images (
    file_path text,
    geom geometry(Polygon,4283)
);

alter table data_science.swimming_pool_images owner to postgres;
