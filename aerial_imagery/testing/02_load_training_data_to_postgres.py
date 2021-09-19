
import rasterio


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

    output["x_pixel_size"] = (bounds.right - bounds.left) / float(output["width"])
    output["y_pixel_size"] = (bounds.top - bounds.bottom) / float(output["height"])

    output["x_centre"] = (bounds.right + bounds.left) / 2.0
    output["y_centre"] = (bounds.bottom + bounds.top) / 2.0

    return output



# load an image

image = get_image("/Users/s57405/Downloads/Swimming Pools with Labels/chips_gordon_19/merged-gordon-19_151.16_-33.767.tif")







# print(f"Image has {image.count} bands, size is {image.width} x {image.height} pixels")
#
# print(f"Image bounds: {image.bounds}")
