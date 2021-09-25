
-- create subset of property boundaries for NSW/ACT
drop table if exists data_science.aus_cadastre_boundaries_nsw;
create table data_science.aus_cadastre_boundaries_nsw as
select cad_pid,
       jurisdiction_id,
       state,
       parcel_type,
       geom
from geo_propertyloc.aus_cadastre_boundaries
where state in ('NSW', 'ACT')
  and parcel_type NOT LIKE 'ROAD%'
;
analyse data_science.aus_cadastre_boundaries_nsw;

CREATE INDEX aus_cadastre_boundaries_nsw_geom_idx ON data_science.aus_cadastre_boundaries_nsw USING gist (geom);
ALTER TABLE data_science.aus_cadastre_boundaries_nsw CLUSTER ON aus_cadastre_boundaries_nsw_geom_idx;


-- create subset of GNAF addresses for NSW/ACT
drop table if exists data_science.address_principals_nsw;
create table data_science.address_principals_nsw as
select gnaf_pid,
       address,
       locality_name,
       postcode,
       state,
       geom
from gnaf_202108.address_principals
where state in ('NSW', 'ACT')
  and coalesce(primary_secondary, 'P') = 'P'
;
analyse data_science.address_principals_nsw;

CREATE INDEX address_principals_nsw_geom_idx ON data_science.address_principals_nsw USING gist (geom);
ALTER TABLE data_science.address_principals_nsw CLUSTER ON address_principals_nsw_geom_idx;


-- create a grid of tiles to detect pools in covering all of Sydney
drop table if exists data_science.sydney_grid;
create table data_science.sydney_grid as
WITH grid AS (
SELECT (ST_SquareGrid(0.0014272, geom)).*
FROM census_2016_bdys.ucl_2016_aust WHERE ucl_name16 = 'Sydney'
)
SELECT st_ymax(grid.geom) as latitude,
       st_xmin(grid.geom) as longitude,
       grid.geom
FROM grid
INNER JOIN census_2016_bdys.ucl_2016_aust as ucl on st_intersects(grid.geom, ucl.geom)
WHERE ucl.ucl_name16 = 'Sydney'
;

analyse data_science.sydney_grid;

CREATE INDEX sydney_grid_geom_idx ON data_science.sydney_grid USING gist (geom);
ALTER TABLE data_science.sydney_grid CLUSTER ON sydney_grid_geom_idx;






-- -- 14799500
-- select count(*) from geo_propertyloc.aus_cadastre_boundaries;
--
-- -- 4837185
-- select count(*) from geo_propertyloc.aus_cadastre_boundaries
-- where state in ('NSW', 'ACT');
--
-- -- 3773682
-- select count(*) from geo_propertyloc.aus_cadastre_boundaries
-- where state in ('NSW', 'ACT')
--   and parcel_type NOT LIKE 'ROAD%';
