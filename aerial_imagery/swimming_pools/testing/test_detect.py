
import torch

# Model
model = torch.hub.load("/Users/s57405/tmp/image-classification/model/weights", 'best', pretrained=True)

# Images
imgs = ["/Users/s57405/Downloads/Swimming Pools with Labels/chips_gordon_19/merged-gordon-19_151.143_-33.76.tif"]  # batch of images

# Inference
results = model(imgs)

# Results
# results.print()
# results.save()  # or .show()

print(results.xyxy[0])  # img1 predictions (tensor)
# results.pandas().xyxy[0]  # img1 predictions (pandas)