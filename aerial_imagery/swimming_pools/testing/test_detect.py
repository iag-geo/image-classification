
# import cv2
import io
import multiprocessing
import os
import psycopg2
import psycopg2.extras
import torch

from datetime import datetime
from owslib.wms import WebMapService
from PIL import Image
from psycopg2 import pool
from psycopg2.extensions import AsIs

# how many parallel processes to run
cpu_count = int(multiprocessing.cpu_count() * 0.8)

# output tables
label_table = "data_science.pool_labels"
image_table = "data_science.pool_images"

# the directory of this script
script_dir = os.path.dirname(os.path.realpath(__file__))

# NSW DCS Web Map Service (https://maps.six.nsw.gov.au/arcgis/services/public/NSW_Cadastre/MapServer/WMSServer?request=GetCapabilities&service=WMS)
wms_base_url = "https://maps.six.nsw.gov.au/arcgis/services/public/NSW_Imagery/MapServer/WMSServer"
wms = WebMapService(wms_base_url)
# print(list(wms.contents))

# coordinates of area to process
x_min = 151.1331
y_min = -33.8912
x_max = 151.1703
y_max = -33.8672

# create images with the same pixel width & height as the training data
width = 0.0014272  # in degrees. A non-sensical unit, but accurate enough4
height = width
image_width = 640
image_height = image_width

# load trained pool model
model = torch.hub.load("/Users/s57405/git/yolov5", "custom", path="/Users/s57405/tmp/image-classification/model/weights/best.pt", source="local")  # local repo


def main():
    full_start_time = datetime.now()
    start_time = datetime.now()

    print(f"Model loaded : {datetime.now() - start_time}")
    start_time = datetime.now()

    # cycle through the map images starting top/left and going left then down to create job list
    job_list = list()
    latitude = y_max

    while latitude > y_min:
        longitude = x_min

        while longitude < x_max:
            job_list.append([latitude, longitude])

            longitude += width
        latitude -= height

    mp_pool = multiprocessing.Pool(cpu_count)
    mp_results = mp_pool.imap_unordered(get_labels, job_list)
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

    print(f"FINISHED : {datetime.now() - full_start_time}")


def get_labels(coords):
    start_time = datetime.now()

    latitude = coords[0]
    longitude = coords[1]

    # download image
    # image_file_path = get_image(latitude, longitude, width, height, image_width, image_height)
    image = get_image(latitude, longitude, width, height, image_width, image_height)
    # print(f"Got input image : {datetime.now() - start_time}")
    # start_time = datetime.now()

    if image is not None:
    # if image_file_path is not None:
        # Run inference
        results = model([image], size=640)
        results_list = results.xyxy[0].tolist()

        # save labelled image whether it has any labels or not (for QA)
        results.save(os.path.join(script_dir, "output"))  # or .show()

        # save labels if any
        num_labels = len(results_list)
        if num_labels > 0:
            f = open(os.path.join(script_dir, "labels", f"test_image_{latitude}_{longitude}.txt"), "w")
            f.write("\n".join(" ".join(map(str, row)) for row in results_list))
            f.close()

        print(f"Image {latitude}, {longitude} has {len(results_list)} pools : {datetime.now() - start_time}")


def get_image(latitude, longitude, width, height, image_width, image_height):
    try:
        response = wms.getmap(
            layers=["0"],
            srs='EPSG:4326',
            bbox=(longitude, latitude, longitude + width, latitude + height),
            format="image/jpeg",
            size=(image_width, image_height)
        )

        # image = io.BytesIO(response.read())

        image = Image.open(io.BytesIO(response.read()))

        # return image

        # # save image
        # image_path = os.path.join(os.path.join(script_dir, "input"), f"test_image_{latitude}_{longitude}.jpg")
        # f = open(image_path, "wb")
        # f.write(response.read())
        # f.close()

        return image

    except:
        # probably timed out
        print(f"NSW DCS WMS timed out for {latitude}, {longitude}")
        return None


if __name__ == "__main__":
    main()
