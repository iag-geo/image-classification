
create schema if not exists data_science;
alter schema data_science owner to postgres;

drop table if exists data_science.swimming_pool_labels;
create table data_science.swimming_pool_labels (
    file_path text,
    geom geometry(Polygon,4823)
);

alter table data_science.swimming_pool_labels owner to postgres;
