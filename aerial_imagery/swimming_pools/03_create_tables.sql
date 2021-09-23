
-- add postgis to database
create extension if not exists postgis;

-- create schema
create schema if not exists data_science;
alter schema data_science owner to "ec2-user";

-- create image & label tables for both training and inference

drop table if exists data_science.pool_training_labels;
create table data_science.pool_training_labels (
    file_path text NOT NULL,
    legal_parcel_id text,
    gnaf_pid text,
    address text,
    latitude numeric(8,6) NOT NULL,
    longitude numeric(9,6) NOT NULL,
    point_geom geometry(Point, 4283) NOT NULL,
    geom geometry(Polygon, 4283) NOT NULL
);

alter table data_science.pool_training_labels owner to "ec2-user";

-- TODO: move these to after data import if this needs to scale
CREATE INDEX pool_training_labels_file_path_idx ON data_science.pool_training_labels USING btree (file_path);
CREATE INDEX pool_training_labels_point_geom_idx ON data_science.pool_training_labels USING gist (point_geom);
CREATE INDEX pool_training_labels_geom_idx ON data_science.pool_training_labels USING gist (geom);
ALTER TABLE data_science.pool_training_labels CLUSTER ON pool_training_labels_geom_idx;


drop table if exists data_science.pool_training_images;
create table data_science.pool_training_images (
    file_path text NOT NULL,
    label_count smallint NULL,
    width double precision NOT NULL,
    height double precision NOT NULL,
    geom geometry(Polygon,4283) NOT NULL
);
alter table data_science.pool_training_images owner to "ec2-user";

-- TODO: move these to after data import if this needs to scale
ALTER TABLE data_science.pool_training_images ADD CONSTRAINT pool_training_images_pkey PRIMARY KEY (file_path);
CREATE INDEX pool_training_images_geom_idx ON data_science.pool_training_images USING gist (geom);
ALTER TABLE data_science.pool_training_images CLUSTER ON pool_training_images_geom_idx;


drop table if exists data_science.pool_labels;
create table data_science.pool_labels (
    file_path text NOT NULL,
    confidence numeric(3,2) NOT NULL,
    legal_parcel_id text,
    gnaf_pid text,
    address text,
    latitude numeric(8,6) NOT NULL,
    longitude numeric(9,6) NOT NULL,
    point_geom geometry(Point, 4283) NOT NULL,
    geom geometry(Polygon, 4283) NOT NULL
);

alter table data_science.pool_labels owner to "ec2-user";

-- TODO: move these to after data import if this needs to scale
CREATE INDEX pool_labels_file_path_idx ON data_science.pool_labels USING btree (file_path);
CREATE INDEX pool_labels_point_geom_idx ON data_science.pool_labels USING gist (point_geom);
CREATE INDEX pool_labels_geom_idx ON data_science.pool_labels USING gist (geom);
ALTER TABLE data_science.pool_labels CLUSTER ON pool_labels_geom_idx;


drop table if exists data_science.pool_images;
create table data_science.pool_images (
    file_path text NOT NULL,
    label_count smallint NULL,
    width double precision NOT NULL,
    height double precision NOT NULL,
    geom geometry(Polygon,4283) NOT NULL
);
alter table data_science.pool_images owner to "ec2-user";

-- TODO: move these to after data import if this needs to scale
ALTER TABLE data_science.pool_images ADD CONSTRAINT pool_images_pkey PRIMARY KEY (file_path);
CREATE INDEX pool_images_geom_idx ON data_science.pool_images USING gist (geom);
ALTER TABLE data_science.pool_images CLUSTER ON pool_images_geom_idx;
