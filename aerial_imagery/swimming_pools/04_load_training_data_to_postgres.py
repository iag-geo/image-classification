
import glob
import multiprocessing
import os
import psycopg2
import psycopg2.extras
import rasterio

from datetime import datetime
from psycopg2 import pool
from psycopg2.extensions import AsIs

# how many parallel processes to run
cpu_count = 16

# input and output path/table
search_path = "/home/ec2-user/training_data/*/*.tif"
label_table = "data_science.swimming_pool_labels"
image_table = "data_science.swimming_pool_images"

# reference tables
gnaf_table = "data_science.address_principals_nsw"
cad_table = "data_science.aus_cadastre_boundaries_nsw"

# create postgres connection pool
pg_connect_string = "dbname=geo host=localhost port=5432 user='ec2-user' password='ec2-user'"
pg_pool = psycopg2.pool.SimpleConnectionPool(1, cpu_count, pg_connect_string)


def main():
    start_time = datetime.now()

    print(f"START : swimming pool image & label import : {datetime.now()}")

    # get postgres connection from pool
    pg_conn = pg_pool.getconn()
    pg_conn.autocommit = True
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # clean out target tables
    pg_cur.execute(f"truncate table {label_table}")
    pg_cur.execute(f"truncate table {image_table}")

    # get list of image paths and process them using multiprocessing
    file_list = list()
    image_count = 0
    for file_name in glob.glob(search_path):
        file_list.append(file_name)
        image_count += 1

    print(f"\t - {image_count} images to import")

    mp_pool = multiprocessing.Pool(cpu_count)
    mp_results = mp_pool.imap_unordered(import_label_to_postgres, file_list)
    mp_pool.close()
    mp_pool.join()

    # check multiprocessing results
    total_label_count = 0
    label_file_count = 0
    no_label_file_count = 0

    for mp_result in mp_results:
        if mp_result > 0:
            total_label_count += mp_result
            label_file_count += 1
        elif mp_result == 0:
            no_label_file_count += 1
        else:
            print("WARNING: multiprocessing error : {}".format(mp_result))

    # output results to screen
    print(f"\t - {total_label_count} labels imported")

    # get counts of missing parcels and addresses
    pg_cur.execute(f"select count(*) from {label_table} where legal_parcel_id is NULL")
    row = pg_cur.fetchone()
    if row is not None:
        print(f"\t\t - {int(row[0])} missing parcel IDs")

    pg_cur.execute(f"select count(*) from {label_table} where gnaf_pid is NULL")
    row = pg_cur.fetchone()
    if row is not None:
        print(f"\t\t - {int(row[0])} missing address IDs")

    print(f"\t - {label_file_count} images with labels")
    print(f"\t - {no_label_file_count} images with no labels")

    # clean up postgres connection
    pg_cur.close()
    pg_pool.putconn(pg_conn)

    print(f"FINISHED : swimming pool image & label import : {datetime.now() - start_time}")


def get_image(file_path):

    output = dict()

    output["image"] = rasterio.open(file_path)

    output["bands"] = output["image"].count
    output["width"] = output["image"].width
    output["height"] = output["image"].height

    bounds = output["image"].bounds

    output["x_min"] = bounds.left
    output["y_min"] = bounds.bottom
    output["x_max"] = bounds.right
    output["y_max"] = bounds.top

    output["x_width"] = bounds.right - bounds.left
    output["y_height"] = bounds.top - bounds.bottom

    # output["x_pixel_size"] = (bounds.right - bounds.left) / float(output["width"])
    # output["y_pixel_size"] = (bounds.top - bounds.bottom) / float(output["height"])

    output["x_centre"] = (bounds.right + bounds.left) / 2.0
    output["y_centre"] = (bounds.bottom + bounds.top) / 2.0

    label_file_path = os.path.split(os.path.abspath(file_path))

    output["label_file"] = os.path.join(label_file_path[0] + "_labels", label_file_path[1].replace(".tif", ".txt"))

    return output


def make_wkt_point(x_centre, y_centre):
    return f"POINT({x_centre} {y_centre})"


def make_wkt_polygon(x_min, y_min, x_max, y_max):
    return f"POLYGON(({x_min} {y_min}, {x_min} {y_max}, {x_max} {y_max}, {x_max} {y_min}, {x_min} {y_min}))"


def convert_label_to_polygon(image, label):
    # format of YOLO label files provided is:
    #   - class (always 0 as there's only one label in this training data: "pool")
    #   - centroid percentage distance from leftmost pixel
    #   - centroid percentage distance from topmost pixel
    #   - percentage width of bounding box
    #   - percentage height of bounding box

    # get lat/long bounding box
    x_min = image["x_min"] + image["x_width"] * (float(label[1]) - float(label[3]) / 2.0)
    y_min = image["y_max"] - image["y_height"] * (float(label[2]) + float(label[4]) / 2.0)
    x_max = image["x_min"] + image["x_width"] * (float(label[1]) + float(label[3]) / 2.0)
    y_max = image["y_max"] - image["y_height"] * (float(label[2]) - float(label[4]) / 2.0)

    # get lat/long centroid
    x_centre = (x_min + x_max) / 2.0
    y_centre = (y_min + y_max) / 2.0

    # create well known text (WKT) geometries
    point = make_wkt_point(x_centre, y_centre)
    polygon = make_wkt_polygon(x_min, y_min, x_max, y_max)

    return y_centre, x_centre, point, polygon


def get_parcel_and_address_ids(latitude, longitude):
    legal_parcel_id = None
    gnaf_pid = None
    address = None

    # get postgres connection from pool
    pg_conn = pg_pool.getconn()
    pg_conn.autocommit = True
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # get legal parcel ID and address ID using spatial join (joining on legal parcel ID is flaky due to GNAF's approach)
    sql = f"""select cad.jurisdiction_id, 
                     gnaf.gnaf_pid, 
                     concat(gnaf.address, ', ', gnaf.locality_name, ' ', gnaf.state, ' ', gnaf.postcode) as address
              from {cad_table} as cad
              inner join {gnaf_table} as gnaf on st_intersects(gnaf.geom, cad.geom)
              where st_intersects(st_setsrid(st_makepoint({longitude}, {latitude}), 4283), cad.geom)"""
    pg_cur.execute(sql)

    # TODO: import all the results. Can return multiple addresses due to strata titles & the specifics of land titling
    row = pg_cur.fetchone()

    if row is not None:
        legal_parcel_id = row[0]
        gnaf_pid = row[1]
        address = row[2]

    # clean up postgres connection
    pg_cur.close()
    pg_pool.putconn(pg_conn)

    # print(f"{legal_parcel_id} : {gnaf_pid}")

    return legal_parcel_id, gnaf_pid, address


def insert_row(table_name, row):
    # get postgres connection from pool
    pg_conn = pg_pool.getconn()
    pg_conn.autocommit = True
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # get column names & values (dict keys must match existing table structure)
    columns = list(row.keys())
    values = [row[column] for column in columns]

    insert_statement = f"INSERT INTO {table_name} (%s) VALUES %s"
    sql = pg_cur.mogrify(insert_statement, (AsIs(','.join(columns)), tuple(values))).decode("utf-8")
    pg_cur.execute(sql)

    # clean up postgres connection
    pg_cur.close()
    pg_pool.putconn(pg_conn)


def import_label_to_postgres(image_path):
    # open image file
    image = get_image(image_path)

    # convert labels to polygons (if label file exists. Image could have no labelled features)
    label_count = 0

    if os.path.isfile(image["label_file"]):
        with open(image["label_file"], "r") as file:

            # insert row for each line in file (TODO: insert in one block of sql statements for performance lift)
            for line in file:
                label_row = dict()
                label_row["file_path"] = image_path
                label_row["label_type"] = "training"

                # get label centre and polygon
                label_row["latitude"], label_row["longitude"], label_row["point_geom"], label_row["geom"] = \
                    convert_label_to_polygon(image, line.split(" "))

                # get legal parcel identifier & address ID (gnaf_pid)
                label_row["legal_parcel_id"], label_row["gnaf_pid"], label_row["address"] = \
                    get_parcel_and_address_ids(label_row["latitude"], label_row["longitude"])

                # insert into postgres
                insert_row(label_table,  label_row)

                label_count += 1

    # import image bounds as polygons for reference
    image_row = dict()
    image_row["file_path"] = image_path
    image_row["label_count"] = label_count
    image_row["geom"] = make_wkt_polygon(image["x_min"], image["y_min"], image["x_max"], image["y_max"])
    insert_row(image_table,  image_row)

    return label_count


if __name__ == "__main__":
    main()