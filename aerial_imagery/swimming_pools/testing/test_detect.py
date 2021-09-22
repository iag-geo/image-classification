
import io
import os
import torch

from datetime import datetime
from owslib.wms import WebMapService

script_dir = os.path.dirname(os.path.realpath(__file__))

# NSW DCS Web Map Service (https://maps.six.nsw.gov.au/arcgis/services/public/NSW_Cadastre/MapServer/WMSServer?request=GetCapabilities&service=WMS)
wms_base_url = "https://maps.six.nsw.gov.au/arcgis/services/public/NSW_Imagery/MapServer/WMSServer"
wms = WebMapService(wms_base_url)
# print(list(wms.contents))

# coordinates of area to process
x_min = 151.1331
y_min = -33.8912
x_max = 151.1703
y_max = -33.8692

# create images with the same pixel width & height as the training data
width = 0.0014272  # in degrees. A non-sensical unit, but accurate enough4
height = width
image_width = 640
image_height = image_width


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
        # return image

        # save image
        image_path = os.path.join(script_dir, f"test_image_{latitude}_{longitude}.jpg")
        f = open(image_path, "wb")
        f.write(response.read())
        f.close()

        return image_path

    except:
        # probably timed out
        print(f"NSW DCS WMS timed out for {latitude}, {longitude} ")
        return None



start_time = datetime.now()

# load trained pool model
model = torch.hub.load("/Users/s57405/git/yolov5", "custom", path="/Users/s57405/tmp/image-classification/model/weights/best.pt", source="local")  # local repo

print(f"Model loaded : {datetime.now() - start_time}")
start_time = datetime.now()

# Get image to process
image_file_path = get_image(latitude, longitude, width, height, image_width, image_height)

print(f"Got input image : {datetime.now() - start_time}")
start_time = datetime.now()

if image_file_path is not None:
    images = [image_file_path]

    # Run inference
    results = model(images)
    results_list = results.xyxy[0].tolist()

    print(f"Image processed - found {len(results_list)} pools : {datetime.now() - start_time}")

    print(results_list)

    # # Results
    # results.print()

    # # save labelled image
    results.save(script_dir)  # or .show()

    # print(results.xyxy[0])  # img1 predictions (tensor)
    # print(results.pandas().xyxy[0])  # img1 predictions (pandas)
