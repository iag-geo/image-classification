
import glob
import os
import rasterio

training_data_path = "/Users/s57405/Downloads/Swimming Pools with Labels"


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

    output["x_pixel_size"] = (bounds.right - bounds.left) / float(output["width"])
    output["y_pixel_size"] = (bounds.top - bounds.bottom) / float(output["height"])

    output["x_centre"] = (bounds.right + bounds.left) / 2.0
    output["y_centre"] = (bounds.bottom + bounds.top) / 2.0

    label_file_path = os.path.split(os.path.abspath(file_path))

    output["label_file"] = os.path.join(label_file_path[0] + "_labels", label_file_path[1].replace(".tif", ".txt"))

    return output


# format of label files is:
#   0: unknown (always 0 in my data sample)
#   1: percentage distance from leftmost pixel
#   2: percentage distance from topmost pixel
#   3: percentage width
#   4: percentage height
def convert_to_polygon(image, label):

    x_min =  image["x_min"] +  image["x_width"] * float(label[1])
    y_max = float(label[2]) * float(image["height"])




    return output



# /Users/s57405/Downloads/Swimming Pools with Labels/chips_gordon_19_labels/merged-gordon-19_151.16_-33.767.txt
# /Users/s57405/Downloads/Swimming Pools with Labels/chips_gordon_19_labels/merged-gordon-19_151.16_-33.765.txt

if __name__ == "__main__":
    # load an image and it's stats
    image_path = "/Users/s57405/Downloads/Swimming Pools with Labels/chips_gordon_19/merged-gordon-19_151.16_-33.765.tif"

    image = get_image("/Users/s57405/Downloads/Swimming Pools with Labels/chips_gordon_19/merged-gordon-19_151.16_-33.765.tif")




    # convert labels to polygons (if file exists - could be no labels for the file)
    if os.path.isfile(image["label_file"]):
        with open(image["label_file"], "r") as file:
            label = file.readline().split(" ")

            bounds = convert_to_polygon(image, label)

    else:
        print(f"No labels for {image_path}")



# print(f"Image has {image.count} bands, size is {image.width} x {image.height} pixels")
#
# print(f"Image bounds: {image.bounds}")
