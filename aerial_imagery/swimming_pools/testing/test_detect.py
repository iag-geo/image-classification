
import torch

from datetime import datetime

start_time = datetime.now()

# load trained pool model
model = torch.hub.load("/Users/s57405/git/yolov5", "custom", path="/Users/s57405/tmp/image-classification/model/weights/best.pt", source="local")  # local repo

print(f"Model loaded : {datetime.now() - start_time}")
start_time = datetime.now()

# Get image to process
imgs = ["/Users/s57405/Downloads/Swimming Pools with Labels/chips_gordon_19/merged-gordon-19_151.143_-33.76.tif"]  # batch of images

# Inference
results = model(imgs)

print(f"Image processed : {datetime.now() - start_time}")

# Results
results.print()
results.save()  # or .show()

# print(results.xyxy[0])  # img1 predictions (tensor)
print(results.pandas().xyxy[0])  # img1 predictions (pandas)
