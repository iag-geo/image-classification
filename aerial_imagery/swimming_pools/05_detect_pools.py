
import io
# import multiprocessing
import os
import psycopg2
import psycopg2.extras
import requests
import torch

from datetime import datetime
from owslib.wms import WebMapService
from PIL import Image
from psycopg2 import pool
from psycopg2.extensions import AsIs
from torch.multiprocessing import cpu_count, Pool, Process, set_start_method

# required for CUDA multiprocessing
try:
    set_start_method("spawn", force=True)
except RuntimeError:
    pass

# how many parallel processes to run
# cpu_count = int(cpu_count() * 0.5)
cpu_count = 48  # cap it to stop CUDA out of memory errors (12 for 1 GPU, 48 for 4 GPUs)

# output tables
label_table = "data_science.pool_labels"
image_table = "data_science.pool_images"

# reference tables
gnaf_table = "data_science.address_principals_nsw"
cad_table = "data_science.aus_cadastre_boundaries_nsw"

# the directory of this script
script_dir = os.path.dirname(os.path.realpath(__file__))

# NSW DCS Web Map Service (https://maps.six.nsw.gov.au/arcgis/services/public/NSW_Cadastre/MapServer/WMSServer?request=GetCapabilities&service=WMS)
wms_base_url = "https://maps.six.nsw.gov.au/arcgis/services/public/NSW_Imagery/MapServer/WMSServer"
wms = WebMapService(wms_base_url)

# coordinates of area to process
x_min = 151.1331
y_min = -33.8912
x_max = 151.1703
y_max = -33.8672

# create images with the same pixel width & height as the training data
width = 0.0014272  # in degrees. A non-sensical unit, but accurate enough
height = width
image_width = 640
image_height = image_width

# create postgres connection pool
# pg_connect_string = "dbname=geo host=localhost port=5432 user='postgres' password='password'"
pg_connect_string = "dbname=geo host=localhost port=5432 user='ec2-user' password='ec2-user'"
pg_pool = psycopg2.pool.SimpleConnectionPool(1, cpu_count, pg_connect_string)

# load trained pool model
# model = torch.hub.load(f"{os.path.expanduser('~')}/git/yolov5", "custom",
#                        path=f"{os.path.expanduser('~')}/tmp/image-classification/model/weights/best.pt",
#                        source="local")


model = torch.hub.load(f"{os.path.expanduser('~')}/yolov5", "custom",
                       path=f"{os.path.expanduser('~')}/yolov5/runs/train/exp/weights/best.pt",
                       source="local")
# model = torch.hub.load("ultralytics/yolov5", "custom",
#                        path=f"{os.path.expanduser('~')}/yolov5/runs/train/exp/weights/best.pt")
# , force_reload=True


def main():
    start_time = datetime.now()

    print(f"START : swimming pool labelling : {start_time}")

    # get postgres connection from pool
    pg_conn = pg_pool.getconn()
    pg_conn.autocommit = True
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # clean out target tables
    pg_cur.execute(f"truncate table {label_table}")
    pg_cur.execute(f"truncate table {image_table}")

    # cycle through the map images starting top/left and going left then down to create job list
    job_list = list()
    image_count = 0
    latitude = y_max

    while latitude > y_min:
        longitude = x_min
        while longitude < x_max:
            image_count += 1
            job_list.append([latitude, longitude])
            longitude += width
        latitude -= height

    mp_pool = Pool(cpu_count)
    mp_results = mp_pool.imap_unordered(get_labels, job_list)
    mp_pool.close()
    mp_pool.join()

    # check multiprocessing results
    total_label_count = 0
    label_file_count = 0
    no_label_file_count = 0
    image_fail_count = 0

    for mp_result in mp_results:
        if mp_result > 0:
            total_label_count += mp_result
            label_file_count += 1
        elif mp_result == 0:
            no_label_file_count += 1
        elif mp_result == -1:
            image_fail_count += 1
        else:
            print("WARNING: multiprocessing error : {}".format(mp_result))

    # output results to screen
    print(f"\t - {image_count} images processed")
    print(f"\t\t - {image_fail_count} images FAILED to download")
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

    print(f"FINISHED : swimming pool labelling : {datetime.now() - start_time}")


def get_labels(coords):
    start_time = datetime.now()

    latitude = coords[0]
    longitude = coords[1]

    # download image
    image = get_image(latitude, longitude)
    # print(f"Got input image : {datetime.now() - start_time}")
    # start_time = datetime.now()

    if image is not None:
        # Run inference
        results = model(image)
        label_list = results.xyxy[0].tolist()

        # # save labelled image whether it has any labels or not (for QA)
        # results.save(os.path.join(script_dir, "output"))  # or .show()

        # export labels to postgres
        label_count = len(label_list)
        if label_count > 0:
            # # save labels
            # f = open(os.path.join(script_dir, "labels", f"test_image_{latitude}_{longitude}.txt"), "w")
            # f.write("\n".join(" ".join(map(str, row)) for row in results_list))
            # f.close()

            import_label_to_postgres(latitude, longitude, label_list)

        # export image polygon to Postgres
        import_image_to_postgres(latitude, longitude, label_count)

        print(f"Image {latitude}, {longitude} has {label_count} pools : {datetime.now() - start_time}")
    else:
        label_count = -1

    return label_count


# downloads images from a WMS service and returns a PIL image (note: coords are top/left)
def get_image(latitude, longitude):

    url = "https://api.gic.org//images/ExtractImages/bluesky-ultra?mode=best&EPSG=4326&xcoordinate=151.14&ycoordinate=-33.85&width=640&height=640&zoom=18&AuthToken=62d0513f3a3e0b63992f630caf6b414a83f8c51e830ce70a4d05afba4e44de5bfed588676e5e735fea4f21913799b2a0f914a2592b34d0476594cd57868fda3e888406f1217f5d962a061735b0c847a1523dddfe98841d71"
    response = requests.get(url)

    try:
        response = wms.getmap(
            layers=["0"],
            srs='EPSG:4326',
            bbox=(longitude, latitude - height, longitude + width, latitude),
            format="image/jpeg",
            size=(image_width, image_height)
        )

        image_file = io.BytesIO(response.read())
        image = Image.open(image_file)
        # image.save(os.path.join(script_dir, "input", f"image_{latitude}_{longitude}.jpg" ))

        return image

    except:
        # probably timed out
        print(f"NSW DCS WMS timed out for {latitude}, {longitude}")
        return None


def make_wkt_point(x_centre, y_centre):
    return f"POINT({x_centre} {y_centre})"


def make_wkt_polygon(x_min, y_min, x_max, y_max):
    return f"POLYGON(({x_min} {y_min}, {x_min} {y_max}, {x_max} {y_max}, {x_max} {y_min}, {x_min} {y_min}))"


def convert_label_to_polygon(latitude, longitude, label):
    # format of inference label files is:
    #   - left pixel
    #   - top pixel
    #   - right pixel
    #   - bottom pixel
    #   - confidence (0.00 to 1.00)
    #   - unknown (class? always 0.0)

    # e.g. [364.4530029296875, 480.5206298828125, 393.81219482421875, 512.9512939453125, 0.9367147088050842, 0.0]

    # these need to be converted to percentages
    label_left = float(label[0]) / float(image_width)
    label_top = float(label[1]) / float(image_height)
    label_right = float(label[2]) / float(image_width)
    label_bottom = float(label[3]) / float(image_height)

    confidence = float(label[4])

    # get lat/long bounding box
    x_min = longitude + width * label_left
    y_min = latitude - height * label_bottom
    x_max = longitude + width * label_right
    y_max = latitude - height * label_top

    # get lat/long centroid
    x_centre = (x_min + x_max) / 2.0
    y_centre = (y_min + y_max) / 2.0

    # create well known text (WKT) geometries
    point = make_wkt_point(x_centre, y_centre)
    polygon = make_wkt_polygon(x_min, y_min, x_max, y_max)

    return confidence, y_centre, x_centre, point, polygon


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


def import_label_to_postgres(latitude, longitude, label_list):
    # todo: fix this - the file name means nothing
    image_path = f"image_{latitude}_{longitude}.jpg"

    # insert row for each line in file (TODO: insert in one block of sql statements for performance lift)
    for label in label_list:
        label_row = dict()
        label_row["file_path"] = image_path

        # get label centre and polygon
        label_row["confidence"], label_row["latitude"], label_row["longitude"], label_row["point_geom"], label_row["geom"] = \
            convert_label_to_polygon(latitude, longitude, label)

        # get legal parcel identifier & address ID (gnaf_pid)
        label_row["legal_parcel_id"], label_row["gnaf_pid"], label_row["address"] = \
            get_parcel_and_address_ids(label_row["latitude"], label_row["longitude"])

        # insert into postgres
        insert_row(label_table,  label_row)


def import_image_to_postgres(latitude, longitude, label_count):
    # todo: fix this - the file name means nothing
    image_path = f"image_{latitude}_{longitude}.jpg"

    # import image bounds as polygons for reference
    x_max = longitude + width
    y_min = latitude - height

    image_row = dict()
    image_row["file_path"] = image_path
    image_row["label_count"] = label_count
    image_row["width"] = width
    image_row["height"] = width
    image_row["geom"] = make_wkt_polygon(longitude, y_min, x_max, latitude)
    insert_row(image_table,  image_row)


if __name__ == "__main__":
    main()
