
import os
import torch

from datetime import datetime
from owslib.wms import WebMapService

script_dir = os.path.dirname(os.path.realpath(__file__))

# NSW DCS Web Map Service (https://maps.six.nsw.gov.au/arcgis/services/public/NSW_Cadastre/MapServer/WMSServer?request=GetCapabilities&service=WMS)
wms_base_url = "https://maps.six.nsw.gov.au/arcgis/services/public/NSW_Cadastre/MapServer/WMSServer"


def get_image(latitude, longitude, width):
    # Get parcel ID from NSW DCS WMS service (intermittent performance - service barely running as of 20210920)
    wms = WebMapService(wms_base_url)

    try:
        response = wms.getfeatureinfo(
            layers=["1"],
            srs='EPSG:4326',
            bbox=(longitude - 0.000001, latitude - 0.000001, longitude + 0.000001, latitude + 0.000001),
            query_layers=["1"],
            info_format="application/json",  # JSON output not working on this server - thanks ESRI!
            feature_count=1,
            method='GET',
            size=(2,2),
            xy=(1,1)
            )

        # output is ugly, old XML, this is a hack to just get what we want
        # b'<?xml version="1.0" encoding="UTF-8"?>\n\r\n<FeatureInfoResponse xmlns:esri_wms="http://www.esri.com/wms" xmlns="http://www.esri.com/wms">\r\n<FIELDS OBJECTID="1712612" Shape="Polygon" cadid="102901598" createdate="8/09/1993" modifieddate="8/09/1993" controllingauthorityoid="2" planoid="19032" plannumber="7796" planlabel="DP7796" ITSTitleStatus="ITSTitle" itslotid="598507" StratumLevel="Ground Level" HasStratum="False" ClassSubtype="StandardLot" lotnumber="32" sectionnumber="Null" planlotarea="Null" planlotareaunits="Null" startdate="26/11/2004 7:43:44 PM" enddate="1/01/3000" lastupdate="26/11/2004 7:43:44 PM" msoid="208734" centroidid="Null" shapeuuid="ac568fff-56c7-3150-9d4b-2ece31d365c2" changetype="I" lotidstring="32//DP7796" processstate="Null" urbanity="U" shape_Length="163.283866" shape_Area="1245.718807"></FIELDS>\r\n</FeatureInfoResponse>\r\n'
        response_text = response.read().decode("utf-8")
        response_list = response_text.split(" ")
        for element in response_list:
            if "lotidstring=" in element:
                legal_parcel_id = element.replace("lotidstring=","").replace('"', '')

        print(f"legal_parcel_id : {legal_parcel_id}")
    except:
        # probably timed out
        print(f"NSW DCS WMS timed out for label at {latitude}, {longitude} ")









start_time = datetime.now()

# load trained pool model
model = torch.hub.load("/Users/s57405/git/yolov5", "custom", path="/Users/s57405/tmp/image-classification/model/weights/best.pt", source="local")  # local repo

print(f"Model loaded : {datetime.now() - start_time}")
start_time = datetime.now()

# Get image to process
imgs = ["/Users/s57405/Downloads/Swimming Pools with Labels/chips_gordon_19/merged-gordon-19_151.143_-33.76.tif"]  # batch of images

# Inference
results = model(imgs)

results_list = results.xyxy[0].tolist()

print(results_list)



print(f"Image processed : {datetime.now() - start_time}")




# # Results
# results.print()

# # save labelled image
# results.save(script_dir)  # or .show()

# print(results.xyxy[0])  # img1 predictions (tensor)
# print(results.pandas().xyxy[0])  # img1 predictions (pandas)
