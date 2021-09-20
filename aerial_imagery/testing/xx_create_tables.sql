
-- create schema and index on GNAF (gnaf-loader doesn't add it)
create schema if not exists data_science;
alter schema data_science owner to postgres;

-- takes 9 mins
CREATE INDEX IF NOT EXISTS address_principals_legal_parcel_id_idx ON gnaf_202108.address_principals USING btree (legal_parcel_id);

-- create image and label tables

drop table if exists data_science.swimming_pool_labels;
create table data_science.swimming_pool_labels (
    file_path text NOT NULL,
    label_type text NOT NULL,
    legal_parcel_id text,
    gnaf_pid text,
    latitude numeric(8,6) NOT NULL,
    longitude numeric(9,6) NOT NULL,
    point_geom geometry(Point, 4283) NOT NULL,
    geom geometry(Polygon, 4283) NOT NULL
);

alter table data_science.swimming_pool_labels owner to postgres;

-- TODO: move these to after data import if this has to scale
CREATE INDEX swimming_pool_labels_file_path_idx ON data_science.swimming_pool_labels USING btree (file_path);
CREATE INDEX swimming_pool_labels_point_geom_idx ON data_science.swimming_pool_labels USING gist (point_geom);
CREATE INDEX swimming_pool_labels_geom_idx ON data_science.swimming_pool_labels USING gist (geom);
ALTER TABLE data_science.swimming_pool_labels CLUSTER ON swimming_pool_labels_geom_idx;

drop table if exists data_science.swimming_pool_images;
create table data_science.swimming_pool_images (
    file_path text NOT NULL,
    label_count smallint NOT NULL,
    geom geometry(Polygon,4283) NOT NULL
);
alter table data_science.swimming_pool_images owner to postgres;

-- TODO: move these to after data import if this has to scale
ALTER TABLE data_science.swimming_pool_images ADD CONSTRAINT swimming_pool_images_pkey PRIMARY KEY (file_path);
CREATE INDEX swimming_pool_images_geom_idx ON data_science.swimming_pool_images USING gist (geom);
ALTER TABLE data_science.swimming_pool_images CLUSTER ON swimming_pool_images_geom_idx;



-- select count(*) from data_science.swimming_pool_labels;


select *
from geo_propertyloc.aus_cadastre_boundaries
where st_intersects(st_setsrid(st_makepoint(151.13, -33.84), 4283), geom)
;

select legal_parcel_id from gnaf_202108.address_principals
-- where state = 'NSW'
where legal_parcel_id like '%DP944236'
;

2/226248