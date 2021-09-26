# Swimming Pools

A set of Bash & Python scripts for configuring, training & running a swimming pools detection model.

Uses YOLOv5 image classification with aerial imagery provided as open data by [NSW DCS Spatial Services](https://six.nsw.gov.au/).

Runs on both NVIDIA CUDA GPU machines as well as CPU only; however, only tested on MacOS and Amazon Linux v2 (Fedora).

**Important**: there are a number of moving parts to get the model to run and it requires a reasonable knowledge of Linux, Bash & AWS (if running remotely).

##Setting up Your Environment

All the code you need setup up your environment locally or in an EC2 instance is in `01_create_ec2_instance.sh` and `02_remote_setup.sh`.

If running locally, grab the code that builds the Conda environment and install YOLOv5 and the additional Python packages.

If building an EC2 instance - the script uses a number of AWS variables in a .sh file. See `sample_aws_vars.sh`


## Training the model

To train the model you'll need to download the [labelled images](https://drive.google.com/file/d/1Rj9wxkH15j2bu9HCh3O6WRmYYzZga-0e).

If running locally, you can see the default file paths for the labelled data in `pool.yaml`.
