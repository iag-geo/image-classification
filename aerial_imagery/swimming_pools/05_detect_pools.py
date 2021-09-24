"""-----------------------------------------------------------------------------------------------------------------
 Detects residential swimming pools in downloaded aerial/satellite images; using an existing trained YOLOv5 model
 - Results are output to Postgres
 - Runs on both CPU and GPU enabled machines. Auto-detects & scales to multiple GPUs

 Author: Hugh Saalmans, Firemark Collective (IAG)
 License: Apache v2
-----------------------------------------------------------------------------------------------------------------"""

import aiohttp
import asyncio
import io
import multiprocessing
import os
import platform
import psycopg2
import psycopg2.extras
import requests
import torch
# import torch.nn as nn

from datetime import datetime
from PIL import Image
from psycopg2 import pool
from psycopg2.extensions import AsIs
# from torch.multiprocessing import set_start_method

# TODO: add arguments to script to get rid of the hard coding below

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

# # coordinates of area to process (Sydney - Inner West to Upper North Shore)
# # ~17k image downloads take ~25 mins via IAG proxy on EC2
# #
# input_x_min = 151.05760
# input_y_min = -33.90748
# input_x_max = 151.26752
# input_y_max = -33.74470

# coordinates of area to process (Sydney - Inner West test area)
# ~450 images take 1-2 mins to download
input_x_min = 151.1331
input_y_min = -33.8912
# input_x_max = 151.1431
# input_y_max = -33.8812
input_x_max = 151.1703
input_y_max = -33.8672

# create images with the same pixel width & height as the training data
width = 0.0014272  # in degrees. A non-sensical unit, but accurate enough
height = width
image_width = 640
image_height = image_width

# auto-select model & postgres settings to allow testing on both MocBook and EC2 GPU (G4) instances
if platform.system() == "Darwin":
    pg_connect_string = "dbname=geo host=localhost port=5432 user='postgres' password='password'"

    # model paths
    yolo_home = f"{os.path.expanduser('~')}/git/yolov5"
    model_path = f"{os.path.expanduser('~')}/tmp/image-classification/model/weights/best.pt"

else:
    pg_connect_string = "dbname=geo host=localhost port=5432 user='ec2-user' password='ec2-user'"

    # model paths
    yolo_home = f"{os.path.expanduser('~')}/yolov5"
    model_path = f"{os.path.expanduser('~')}/yolov5/runs/train/exp/weights/best.pt"

# how many parallel processes to run (only used for downloading images, hence can use all CPUs safely)
max_concurrent_downloads = multiprocessing.cpu_count()

# process images in chunks to manage memory usage
image_limit = 400  # roughly 13Gb RAM for this model (GPUs have a 15Gb limit that must be managed by this script)

# get count of CUDA enabled GPUs (= 0 for CPU only machines)
cuda_gpu_count = torch.cuda.device_count()

# create postgres connection pool
pg_pool = psycopg2.pool.SimpleConnectionPool(1, max_concurrent_downloads, pg_connect_string)


def main():
    full_start_time = datetime.now()
    start_time = datetime.now()

    print(f"START : swimming pool labelling : {start_time}")

    # get postgres connection from pool
    pg_conn = pg_pool.getconn()
    pg_conn.autocommit = True
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # clean out target tables
    pg_cur.execute(f"truncate table {label_table}")
    pg_cur.execute(f"truncate table {image_table}")

    # -----------------------------------------------------------------------------------------------------------------
    # Create the multiprocessing job list to download the images
    # Cycle through the map image top/left coordinates going left then down
    # -----------------------------------------------------------------------------------------------------------------

    job_list = list()
    image_count = 0
    latitude = input_y_max

    while latitude > input_y_min:
        longitude = input_x_min
        while longitude < input_x_max:
            image_count += 1
            job_list.append([latitude, longitude])
            longitude += width
        latitude -= height

    # -----------------------------------------------------------------------------------------------------------------
    # Download images into memory
    # ----------------------------------------------------------------------------------------------------------------

    # download asynchronously in parallel
    loop = asyncio.get_event_loop()
    image_download_list = loop.run_until_complete(async_get_images(job_list))

    # check download results
    image_fail_count = 0

    # get rid of image download failures and log them
    coords_list = list()
    image_list = list()
    for image_download in image_download_list:
        if image_download is not None:
            coords_list.append(image_download[0])
            image_list.append(image_download[1])
        else:
            image_fail_count += 1

    # show image download results
    print(f"\t - {image_count} images downloaded into memory : {datetime.now() - start_time}")
    print(f"\t\t - {image_fail_count} images FAILED to download")
    start_time = datetime.now()

    # process all images in one hit
    start_time, total_label_count = get_labels(image_list, coords_list)
    print(f"\t - {total_label_count} labels imported : {datetime.now() - start_time}")
    # start_time = datetime.now()

    # label_file_count = 0
    # no_label_file_count = 0

    # get counts of missing parcels and addresses
    pg_cur.execute(f"select count(*) from {label_table} where legal_parcel_id is NULL")
    row = pg_cur.fetchone()
    if row is not None:
        print(f"\t\t - {int(row[0])} missing parcel IDs")

    pg_cur.execute(f"select count(*) from {label_table} where gnaf_pid is NULL")
    row = pg_cur.fetchone()
    if row is not None:
        print(f"\t\t - {int(row[0])} missing address IDs")

    # print(f"\t - {label_file_count} images with labels")
    # print(f"\t - {no_label_file_count} images with no labels")

    # clean up postgres connection
    pg_cur.close()
    pg_pool.putconn(pg_conn)

    print(f"FINISHED : swimming pool labelling : {datetime.now() - full_start_time}")


def get_labels(image_list, coords_list):
    start_time = datetime.now()

    # if cuda_gpu_count > 1:
    #     # required for torch multiprocessing with CUDA
    #     set_start_method("spawn", force=True)

    # load trained pool model to run on all GPUs or CPUs
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"{device} is available with {torch.cuda.device_count()} GPUs")

    model = torch.hub.load(yolo_home, "custom", path=model_path, source="local")

    # if cuda_gpu_count > 1:
    #     model = nn.DataParallel(model)
    #     model.to(device)
    #     image_list = image_list.to(device)

    # Run inference after splitting images into groups to be processed (to control memory usage)

    image_groups = list()
    image_group = list()
    coords_groups = list()
    coords_group = list()
    i = 1
    j = 0

    for image in image_list:
        if i > image_limit:
            image_groups.append(image_group)
            image_group = list()
            coords_groups.append(coords_group)
            coords_group = list()
            i = 1

        image_group.append(image)
        coords_group.append(coords_list[j])

        i += 1
        j += 1

    if len(image_group) > 0:
        image_groups.append(image_group)
        coords_groups.append(coords_group)

    # don't need these anymore
    del image_list
    del coords_list

    tensor_labels_list = list()

    # run inference
    for group in image_groups:
        results = model(group)
        tensor_labels_list.append(results.xyxy)

        # DEBUG: save labelled images
        # results.save(os.path.join(script_dir, "output"))

    print(f"\t - pool detection done : {datetime.now() - start_time}")
    start_time = datetime.now()

    i = 0
    total_label_count = 0

    # step through each group of results and export to database
    for tensor_labels in tensor_labels_list:
        j = 0

        for tensor_label in tensor_labels:
            label_list = tensor_label.tolist()

            label_count = len(label_list)
            if label_count > 0:
                total_label_count += label_count

                # get corresponding coords of image (used to create ID to match
                latitude = coords_groups[i][j][0]
                longitude = coords_groups[i][j][1]

                # DEBUG: save labels to disk
                # f = open(os.path.join(script_dir, "labels", f"test_image_{latitude}_{longitude}.txt"), "w")
                # f.write("\n".join(" ".join(map(str, row)) for row in results_list))
                # f.close()

                # print(f"Image {latitude}, {longitude} has {label_count} pools")

                import_labels_to_postgres(latitude, longitude, label_list)

            j += 1
        i += 1

    return start_time, total_label_count


async def async_get_images(job_list):
    """Sets up the asynchronous downloading of images in parallel"""

    conn = aiohttp.TCPConnector(limit=max_concurrent_downloads)

    async with aiohttp.ClientSession(connector=conn, trust_env=True) as session:
        # create job list to do asynchronously
        process_list = []
        for coords in job_list:
            process_list.append(get_image(session, coords))

        # execute them all at once and return list of downloading images
        return await asyncio.gather(*process_list)


async def get_image(session, coords):
    """Downloads an image from a Web Map service (WMS) service into memory, saves it's bounds (as a polygon) to Postgres
       and returns a pillow image

       Note: map coords are top/left (normally bottom/left) to match pixel coordinate convention)"""

    latitude = coords[0]
    longitude = coords[1]

    # try:
        # response = wms.getmap(
        #     layers=["0"],
        #     srs='EPSG:4326',
        #     bbox=(longitude, latitude - height, longitude + width, latitude),
        #     format="image/jpeg",
        #     size=(image_width, image_height)
        # )

    # querystring parameters
    params = dict()
    params["service"] = "WMS"
    params["request"] = "GetMap"
    params["version"] = "1.3.0"
    params["layers"] = 0
    params["styles"] = ""
    params["crs"] = "epsg:4326"
    params["bbox"] = f"{longitude},{latitude - height},{longitude + width},{latitude}"
    params["width"] = image_width
    params["height"] = image_height
    params["format"] = "image/jpeg"

    try:
        async with session.get(wms_base_url, params=params) as response:
            response = await response.read()
        # response = requests.get(wms_base_url, params=params)

        image_file = io.BytesIO(response)
        image = Image.open(image_file)

        # DEBUG: save image to disk
        # image.save(os.path.join(script_dir, "input", f"image_{latitude}_{longitude}.jpg" ))

        # export image polygon & metadata to Postgres
        import_image_to_postgres(latitude, longitude)

        return [latitude, longitude], image

    except Exception as ex:
        # request most likely timed out
        print(f"Image download {latitude}, {longitude} FAILED: {ex}")
        return None


def make_wkt_point(x_centre, y_centre):
    """Creates a well known text (WKT) point geometry for insertion into database"""
    return f"POINT({x_centre} {y_centre})"


def make_wkt_polygon(x_min, y_min, x_max, y_max):
    """Creates a well known text (WKT) polygon geometry for insertion into database"""
    return f"POLYGON(({x_min} {y_min}, {x_min} {y_max}, {x_max} {y_max}, {x_max} {y_min}, {x_min} {y_min}))"


def convert_label_to_polygon(latitude, longitude, label):
    """Takes a detected label & converts it to centroid & boundary geometries for insertion into database

    format of label list is:
      0 - left pixel
      1 - top pixel
      2 - right pixel
      3 - bottom pixel
      4 - confidence (0.00 to 1.00)
      5 - unknown (class? always 0.0)

    e.g. [364.4530029296875, 480.5206298828125, 393.81219482421875, 512.9512939453125, 0.9367147088050842, 0.0]"""

    # these pixel coords need to be converted to percentages
    label_left = float(label[0]) / float(image_width)
    label_top = float(label[1]) / float(image_height)
    label_right = float(label[2]) / float(image_width)
    label_bottom = float(label[3]) / float(image_height)

    confidence = float(label[4])

    # get lat/long boundary by converting pixel coords to real world coords
    x_min = longitude + width * label_left
    y_min = latitude - height * label_bottom
    x_max = longitude + width * label_right
    y_max = latitude - height * label_top

    # get centroid lat/long
    x_centre = (x_min + x_max) / 2.0
    y_centre = (y_min + y_max) / 2.0

    # create well known text (WKT) geometries
    point = make_wkt_point(x_centre, y_centre)
    polygon = make_wkt_polygon(x_min, y_min, x_max, y_max)

    return confidence, y_centre, x_centre, point, polygon


def get_parcel_and_address_ids(latitude, longitude):
    """Takes a label's point and gets its address and land parcel IDs from the database.
    Returns None if no match (possible due to the vagaries of addressing & land titling)"""

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

    # TODO: import more than the first result.
    #   Can return multiple addresses due to strata titles & the realities of 3D land titling
    row = pg_cur.fetchone()

    legal_parcel_id = None
    gnaf_pid = None
    address = None

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
    """Inserts a python dictionary as a new row into a database table.
    Allows for any number of columns and types; but column names and types MUST match existing table structure"""

    # get postgres connection from pool
    pg_conn = pg_pool.getconn()
    pg_conn.autocommit = True
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # get column names & values (dict keys must match existing table columns)
    columns = list(row.keys())
    values = [row[column] for column in columns]

    insert_statement = f"INSERT INTO {table_name} (%s) VALUES %s"
    sql = pg_cur.mogrify(insert_statement, (AsIs(','.join(columns)), tuple(values))).decode("utf-8")
    pg_cur.execute(sql)

    # clean up postgres connection
    pg_cur.close()
    pg_pool.putconn(pg_conn)


def import_labels_to_postgres(latitude, longitude, label_list):
    """Inserts a list of labels into the database"""

    # TODO: come up with a more meaningful ID for linking images with labels
    image_path = f"image_{latitude}_{longitude}.jpg"

    # insert row for each line in file (TODO: insert in one block of sql statements for performance lift)
    for label in label_list:
        label_row = dict()
        label_row["file_path"] = image_path

        # get label centre and polygon
        label_row["confidence"], label_row["latitude"], label_row["longitude"], \
        label_row["point_geom"], label_row["geom"] = \
            convert_label_to_polygon(latitude, longitude, label)

        # get legal parcel identifier & address ID (gnaf_pid)
        label_row["legal_parcel_id"], label_row["gnaf_pid"], label_row["address"] = \
            get_parcel_and_address_ids(label_row["latitude"], label_row["longitude"])

        # insert into postgres
        insert_row(label_table,  label_row)


def import_image_to_postgres(latitude, longitude):
    """Inserts an image's polygon & metadata into the database"""

    # TODO: come up with a more meaningful ID for linking images with labels
    image_path = f"image_{latitude}_{longitude}.jpg"

    # import image bounds as polygons for reference
    x_max = longitude + width
    y_min = latitude - height

    image_row = dict()
    image_row["file_path"] = image_path
    # image_row["label_count"] = label_count
    image_row["width"] = width
    image_row["height"] = width
    image_row["geom"] = make_wkt_polygon(longitude, y_min, x_max, latitude)
    insert_row(image_table,  image_row)


if __name__ == "__main__":
    main()
