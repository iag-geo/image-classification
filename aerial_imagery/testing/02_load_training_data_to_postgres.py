
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
cpu_count = 4

# input and output path/table
search_path = "/Users/s57405/Downloads/Swimming Pools with Labels/*/*.tif"
label_table = "data_science.swimming_pool_labels"
image_table = "data_science.swimming_pool_images"

# create postgres connect string
pg_connect_string = "dbname=geo host=localhost port=5432 user=postgres password=password"

# create postgres connection pool
pg_pool = psycopg2.pool.SimpleConnectionPool(1, cpu_count, pg_connect_string)


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
    # format of label files is:
    #   0: unknown (always 0 in my data sample)
    #   1: percentage distance from leftmost pixel
    #   2: percentage distance from topmost pixel
    #   3: percentage width
    #   4: percentage height

    # # TODO: convert percentages to coordinates -- appears to put polygon offset by 1/2 width and height
    # #  (bug in my code or misinterpretation of training labels?)
    # x_min = image["x_min"] + image["x_width"] * float(label[1])
    # y_min = image["y_max"] - image["y_height"] * (float(label[2]) + float(label[4]))
    # x_max = image["x_min"] + image["x_width"] * (float(label[1]) + float(label[3]))
    # y_max = image["y_max"] - image["y_height"] * float(label[2])

    x_min = image["x_min"] + image["x_width"] * (float(label[1]) - float(label[3]) / 2.0)
    y_min = image["y_max"] - image["y_height"] * (float(label[2]) + float(label[4]) / 2.0)
    x_max = image["x_min"] + image["x_width"] * (float(label[1]) + float(label[3]) / 2.0)
    y_max = image["y_max"] - image["y_height"] * (float(label[2]) - float(label[4]) / 2.0)

    x_centre = (x_min + x_max) / 2.0
    y_centre = (y_min + y_max) / 2.0

    point = make_wkt_point(x_centre, y_centre)
    polygon = make_wkt_polygon(x_min, y_min, x_max, y_max)

    return y_centre, x_centre, point, polygon


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
                label_row["latitude"],  label_row["longitude"],  label_row["point_geom"],  label_row["geom"] = \
                    convert_label_to_polygon(image, line.split(" "))

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
    start_time = datetime.now()

    print(f"START : swimming pool image & label import : {datetime.now()}")

    # clean out target tables

    # get postgres connection from pool
    pg_conn = pg_pool.getconn()
    pg_conn.autocommit = True
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    pg_cur.execute(f"truncate table {label_table}")
    pg_cur.execute(f"truncate table {image_table}")

    # clean up postgres connection
    pg_cur.close()
    pg_pool.putconn(pg_conn)

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
    label_count = 0
    label_file_count = 0
    no_label_file_count = 0

    for mp_result in mp_results:
        if mp_result > 0:
            label_count += mp_result
            label_file_count += 1
        elif mp_result == 0:
            no_label_file_count += 1
        else:
            print("WARNING: multiprocessing error : {}".format(mp_result))

    print(f"\t - {label_count} labels imported")
    print(f"\t - {label_file_count} images with labels")
    print(f"\t - {no_label_file_count} images with no labels")

    print(f"FINISHED : swimming pool image & label import : {datetime.now() - start_time}")
