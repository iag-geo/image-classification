# Swimming Pools

A set of Bash & Python scripts for configuring, training & running a swimming pool detection model.

Uses YOLOv5 image classification with aerial imagery provided (as open data) by [NSW DCS Spatial Services](https://six.nsw.gov.au/).

Runs on both NVIDIA CUDA GPU machines as well as CPU only; however, only tested on MacOS and Amazon Linux v2 (Fedora). The CPU vs GPU performance hit on pool detection is around 8-10x slower

**Important**: there are a number of moving parts to run the model; it requires a reasonable knowledge of Linux, Bash & AWS (if running remotely).

##Model Quality

It's important to note this model is **not production grade** and should be used for learning only in it's current state. It creates a number of false positives. e.g. blue vehicles & shadecloths


##Setting up Your Environment

All the code you need to setup up your environment locally or in an EC2 instance is in `01_create_ec2_instance.sh` and `02_remote_setup.sh`

If running locally, utilise the code that builds the Conda environment in the remote setup script & installs YOLOv5 with additional Python packages.

If building an EC2 instance - the script uses a number of AWS variables in a .sh file. See `sample_aws_vars.sh`. The remote setup script also assumes your training & reference (optional) data is in AWS S3; you can comment this out and copy manually.

## Training the model

To train the model you'll need to download the [labelled images](https://drive.google.com/file/d/1Rj9wxkH15j2bu9HCh3O6WRmYYzZga-0e).

You can set the file paths for the labelled data in the training config file `pool.yaml`; noting the defaults show you the rules about the naming & structure of training data image & label files - and your files should adhere to these.

Lastly, you can run the model training using `05_train_model.sh`.

Training on a GPU enabled EC2 instance takes ~30 mins. Training wasn't tested on a CPU only machine; assume it will take a number of hours.

## Running Inference

To detect pools from the imagery using your trained model: review and edit the user settings in `06_detect_pools.py` before running it

##IMPORTANT: Optional Reference Data

Both the training & inference processes can use reference Australian address and property data to return an address for each pool found. As the property data ([Geoscape Land Parcels](https://geoscape.com.au/data/land-parcels/)) is not open data - the use of this data is optional.
- When training the model: `04_load_training_data_to_postgres.py` doesn't need to be run and can be ignored
- When running inference: set _use_reference_data_ to _False_ in `06_detect_pools.py`
