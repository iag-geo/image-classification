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
import math
import os
import platform
import psycopg2
import psycopg2.extras
import torch

from datetime import datetime
from PIL import Image
from psycopg2 import pool
from psycopg2.extensions import AsIs
# from torchvision import transforms


# TODO:
#   - add arguments to script to get rid of the hard coding below
#   - add logging fro a permanent record of processing times/issues

# output tables
label_table = "data_science.pool_labels"
image_table = "data_science.pool_images"

# reference tables
gnaf_table = "data_science.address_principals_nsw"
cad_table = "data_science.aus_cadastre_boundaries_nsw"
grid_table = "data_science.sydney_grid"

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
#
# # coordinates of area to process (Sydney - Inner West test area)
# # ~450 images take 1-2 mins to download
# input_x_min = 151.1331
# input_y_min = -33.8912
# # input_x_max = 151.1431
# # input_y_max = -33.8812
# input_x_max = 151.1703
# input_y_max = -33.8672

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

# process images in chunks to manage memory usage
image_limit = 250  # roughly 8Gb RAM for this model but can spike (GPUs have a 15Gb limit that can crash this script)

# how many parallel processes to run (only used for downloading images, hence can use 2x CPUs safely)
max_concurrent_downloads = torch.multiprocessing.cpu_count() * 2
max_postgres_connections = max_concurrent_downloads + 1  # +1 required due to rounding error in process counts below

# get count of CUDA enabled GPUs (= 0 for CPU only machines)
cuda_gpu_count = torch.cuda.device_count()

# DEBUGGING
# cuda_gpu_count = 4

# alter concurrent download limit if using multiple GPUs
if cuda_gpu_count > 1:
    max_concurrent_downloads = math.floor(max_concurrent_downloads / cuda_gpu_count)

# create postgres connection pool (accessible across multiple processes)
pg_pool = psycopg2.pool.SimpleConnectionPool(1, max_postgres_connections, pg_connect_string)


def main():
    full_start_time = datetime.now()

    print(f"START : swimming pool labelling : {full_start_time}")

    # get postgres connection from pool
    pg_conn = pg_pool.getconn()
    pg_conn.autocommit = True
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # clean out target tables
    pg_cur.execute(f"truncate table {label_table}")
    pg_cur.execute(f"truncate table {image_table}")

    # -----------------------------------------------------------------------------------------------------------------
    # Create a multiprocessing job list to download and label the images using available GPUs (or CPUs if no GPUs)
    # -----------------------------------------------------------------------------------------------------------------

    image_count, jobs_by_gpu = get_jobs()

    if cuda_gpu_count > 1:
        # required for torch multiprocessing on GPUs
        torch.multiprocessing.set_start_method("spawn", force=True)

        # assign a GPU number to each set of job group (1 set of groups per GPU)
        mp_job_list = list()
        gpu_number = 0
        for job_groups in jobs_by_gpu:
            mp_job_list.append([job_groups, gpu_number])
            gpu_number += 1

        mp_pool = torch.multiprocessing.Pool(cuda_gpu_count)
        mp_results = mp_pool.imap_unordered(get_labels, mp_job_list)
        mp_pool.close()
        mp_pool.join()

        total_label_count = 0
        total_image_fail_count = 0

        for label_count, image_fail_count in mp_results:
            total_label_count += label_count
            total_image_fail_count += image_fail_count

    else:
        total_label_count, total_image_fail_count = get_labels([jobs_by_gpu[0], 0])

    # show image download results
    print(f"{image_count} images downloaded into memory")
    print(f"\t - {total_image_fail_count} images FAILED to download")
    print(f"{total_label_count} labels imported")
    # start_time = datetime.now()

    # label_file_count = 0
    # no_label_file_count = 0

    # get counts of missing parcels and addresses
    pg_cur.execute(f"select count(*) from {label_table} where legal_parcel_id is NULL")
    row = pg_cur.fetchone()
    if row is not None:
        print(f"\t - {int(row[0])} missing parcel IDs")

    pg_cur.execute(f"select count(*) from {label_table} where gnaf_pid is NULL")
    row = pg_cur.fetchone()
    if row is not None:
        print(f"\t - {int(row[0])} missing address IDs")

    # print(f"\t - {label_file_count} images with labels")
    # print(f"\t - {no_label_file_count} images with no labels")

    # clean up postgres connection
    pg_cur.close()
    pg_pool.putconn(pg_conn)

    print(f"FINISHED : swimming pool labelling : {datetime.now() - full_start_time}")


def get_jobs():
    """Create job list by getting list o lat/longs from Postgres table.
       Then split jobs based on:
         a. the number of GPUs being used (if any); AND
         b. The max number of images to be processed in a single go by each GPU (to control memory usage)"""

    # new method - get lat/long grid from Postgres table (Sydney urban area)

    # get postgres connection from pool
    pg_conn = pg_pool.getconn()
    pg_conn.autocommit = True
    pg_cur = pg_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    pg_cur.execute(f"select latitude, longitude from {grid_table}")
    rows = pg_cur.fetchall()

    job_list = [[row[0], row[1]] for row in rows]
    image_count = len(job_list)

    # clean up postgres connection
    pg_cur.close()
    pg_pool.putconn(pg_conn)

    # old method - a user defined grid

    # """Create job list by cycling through the map image top/left coordinates going left then down.
    #    Then split jobs based on:
    #      a. the number of GPUs being used (if any); AND
    #      b. The max number of images to be processed in a single go by each GPU (to control memory usage)"""

    # # create job list
    # job_list = list()
    # image_count = 0
    # latitude = input_y_max
    #
    # while latitude > input_y_min:
    #     longitude = input_x_min
    #     while longitude < input_x_max:
    #         image_count += 1
    #         job_list.append([latitude, longitude])
    #         longitude += width
    #     latitude -= height

    # split jobs by number of GPUs and limit per job group
    jobs_by_gpu = list()

    if cuda_gpu_count > 1:
        # 1. split jobs into even groups by GPU
        jobs_per_gpu = math.ceil(len(job_list) / cuda_gpu_count)
        temp_job_groups = list(split_list(job_list, jobs_per_gpu))

        # 2. split each GPUs workload into "fits in memory" sized chunks
        for temp_job_group in temp_job_groups:
            job_groups = list(split_list(temp_job_group, image_limit))
            jobs_by_gpu.append(job_groups)

    else:
        job_groups = list(split_list(job_list, image_limit))
        jobs_by_gpu.append(job_groups)

    return image_count, jobs_by_gpu


def split_list(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def get_labels(job):
    """Downloads images asynchronously & in parallel then runs them through the model to detect pools"""

    job_groups = job[0]
    gpu_number = job[1]

    # get job counts
    job_count = 0
    for job_group in job_groups:
        job_count += len(job_group)

    # load trained model to run on selected GPU (or CPUs)
    if torch.cuda.is_available():
        device_tag = f"cuda:{gpu_number}"
    else:
        device_tag = "cpu"

    device = torch.device(device_tag)
    model = torch.hub.load(yolo_home, "custom", path=model_path, source="local")
    model.to(device)

    total_image_fail_count = 0
    total_label_count = 0
    i = 0

    # for each job group download images and detect labels on them
    for job_group in job_groups:
        start_time = datetime.now()

        i += len(job_group)

        # Download images into memory, asynchronously in parallel
        loop = asyncio.get_event_loop()
        image_download_list = loop.run_until_complete(async_get_images(job_group))

        # get rid of image download failures and count them
        coords_list = list()
        image_list = list()
        image_fail_count = 0
        for image_download in image_download_list:
            if image_download is not None:
                coords_list.append(image_download[0])
                image_list.append(image_download[1])
            else:
                image_fail_count += 1

        total_image_fail_count += image_fail_count

        # print(f"\t - {device_tag} : group {i} of {job_count} : images downloaded : {datetime.now() - start_time}")
        # start_time = datetime.now()

        # run inference
        results = model(image_list)
        tensor_labels = results.xyxy

        # DEBUG: save labelled images
        # results.save(os.path.join(script_dir, "output"))

        # print(f"\t - {device_tag} : group {i} of {job_count} : pool detection done : {datetime.now() - start_time}")
        # start_time = datetime.now()

        # step through each group of results and export to database
        j = 0

        for tensor_label in tensor_labels:
            label_list = tensor_label.tolist()

            label_count = len(label_list)
            if label_count > 0:
                total_label_count += label_count

                # get corresponding coords of image (used to create ID to match
                latitude = coords_list[j][0]
                longitude = coords_list[j][1]

                # DEBUG: save labels to disk
                # f = open(os.path.join(script_dir, "labels", f"test_image_{latitude}_{longitude}.txt"), "w")
                # f.write("\n".join(" ".join(map(str, row)) for row in results_list))
                # f.close()
                # print(f"Image {latitude}, {longitude} has {label_count} pools")

                import_labels_to_postgres(latitude, longitude, label_list)

            j += 1

        # print(f"\t - {device_tag} : group {i} of {job_count} : done - labels exported to postgres : {datetime.now() - start_time}")
        print(f"\t - {device_tag} : group {i} of {job_count} : done : {datetime.now() - start_time} : {total_label_count} labels detected")

    return total_label_count, total_image_fail_count


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
        # download image
        async with session.get(wms_base_url, params=params) as response:
            response = await response.read()

        # convert response to a Pillow image
        image_file = io.BytesIO(response)
        image = Image.open(image_file)

        # TESTING - need to convert images to tensors to enable multi-GPU processing.
        # Note: YOLOv5 authors claim multi-GPU can't be done.
        # tensor_image = transforms.ToTensor()(image).unsqueeze_(0)
        # # print(tensor_image.shape)

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
