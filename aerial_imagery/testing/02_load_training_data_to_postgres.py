
import glob
import multiprocessing
import os
import psycopg2
import psycopg2.extras
import rasterio

from psycopg2 import pool
from psycopg2.extensions import AsIs

# how many parallel processes to run
cpu_count = 4

# input and output path/table
search_path = "/Users/s57405/Downloads/Swimming Pools with Labels/*/*.tif"
target_table = "data_science.swimming_pool_labels"

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


def convert_to_polygon(image, label):
    # format of label files is:
    #   0: unknown (always 0 in my data sample)
    #   1: percentage distance from leftmost pixel
    #   2: percentage distance from topmost pixel
    #   3: percentage width
    #   4: percentage height

    # convert percentages to coordinates
    x_min = image["x_min"] + image["x_width"] * float(label[1])
    y_min = image["y_max"] - image["y_height"] * (float(label[2]) + float(label[4]))
    x_max = image["x_min"] + image["x_width"] * (float(label[1]) + float(label[3]))
    y_max = image["y_max"] - image["y_height"] * float(label[2])

    return f"POLYGON(({x_min} {y_min}, {x_min} {y_max}, {x_max} {y_max}, {x_max} {y_min}, {x_min} {y_min}))"


def import_label_to_postgres(image_path):
    # open image file
    image = get_image(image_path)

    # convert labels to polygons (if file exists - could be no labels for the file)
    if os.path.isfile(image["label_file"]):
        with open(image["label_file"], "r") as file:
            polygon = convert_to_polygon(image, file.readline().split(" "))
    else:
        print(f"No labels for {image_path}")
        polygon = None

    # get postgres connection from pool
    pg_conn = pg_pool.getconn()
    pg_conn.autocommit = True
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    row = dict()
    row["file_path"] = image_path
    row["geom"] = polygon

    columns = list(row.keys())
    values = [row[column] for column in columns]

    insert_statement = f"INSERT INTO {target_table} (%s) VALUES %s"
    sql = pg_cur.mogrify(insert_statement, (AsIs(','.join(columns)), tuple(values))).decode("utf-8")
    pg_cur.execute(sql)

    # clean up postgres connection
    pg_cur.close()
    pg_pool.putconn(pg_conn)

    print(f"Imported {os.path.basename(image_path)} labels")


if __name__ == "__main__":
    # get list of image paths
    file_list = list()
    for file_name in glob.glob(search_path):
        file_list.append(file_name)

    mp_pool = multiprocessing.Pool(cpu_count)
    mp_results = mp_pool.imap_unordered(import_label_to_postgres, file_list)
    mp_pool.close()
    mp_pool.join()

    # check multiprocessing results
    for mp_result in mp_results:
        if mp_result is not None:
            print("WARNING: multiprocessing error : {}".format(mp_result))
