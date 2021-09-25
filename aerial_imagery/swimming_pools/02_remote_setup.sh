#!/usr/bin/env bash

# installs NVIDIA drivers and Python packages to enable YOLOv5 image classification - training & inference

PYTHON_VERSION="3.9"
NVIDIA_DRIVER_VERSION="470.57.02"  # CUDA 11.4

# check if proxy server required
while getopts ":p:" opt; do
  case $opt in
  p)
    PROXY=$OPTARG
    ;;
  esac
done

echo "-------------------------------------------------------------------------"
echo " Installing git & kernel packages"
echo "-------------------------------------------------------------------------"

sudo yum -y install tmux git kernel-devel-$(uname -r) kernel-headers-$(uname -r)

# set git proxy (if required)
if [ -n "${PROXY}" ]; then
  git config --global http.https://github.com.proxy ${http_proxy}
  git config --global http.https://github.com.sslVerify false
fi

echo "-------------------------------------------------------------------------"
echo " Installing NVIDIA drivers"
echo "-------------------------------------------------------------------------"

# install NVIDIA CUDA drivers
curl -fSsl -O https://us.download.nvidia.com/tesla/${NVIDIA_DRIVER_VERSION}/NVIDIA-Linux-x86_64-${NVIDIA_DRIVER_VERSION}.run
chmod u+x ~/NVIDIA-Linux-x86_64-${NVIDIA_DRIVER_VERSION}.run
sudo sh ~/NVIDIA-Linux-x86_64-${NVIDIA_DRIVER_VERSION}.run -s > nvidia_driver_install.log
rm NVIDIA-Linux-x86_64-${NVIDIA_DRIVER_VERSION}.run

# Install Conda to create a Python 3.9 environment (AWS yum repos stop at Python 3.7)
echo "-------------------------------------------------------------------------"
echo " Installing Conda"
echo "-------------------------------------------------------------------------"

# download & install silently
curl -fSsl -O https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
chmod +x Miniconda3-latest-Linux-x86_64.sh
sh Miniconda3-latest-Linux-x86_64.sh -b

# initialise Conda & reload bash environment
${HOME}/miniconda3/bin/conda init
source ${HOME}/.bashrc

# update Python packages
echo "y" | conda update conda

echo "-------------------------------------------------------------------------"
echo " Creating new Conda Environment 'yolov5'"
echo "-------------------------------------------------------------------------"

# Create Conda environment
echo "y" | conda create -n yolov5 python=${PYTHON_VERSION}

# activate and setup env
conda activate yolov5
conda config --env --add channels conda-forge
conda config --env --set channel_priority strict

# reactivate for changes to take effect
conda activate yolov5

echo "-------------------------------------------------------------------------"
echo " Downloading & installing YOLOv5"
echo "-------------------------------------------------------------------------"

git clone https://github.com/ultralytics/yolov5  # get YOLOv5 code
cd yolov5
pip3 install -r requirements.txt  # install dependencies

echo "-------------------------------------------------------------------------"
echo " Installing additional Python packages"
echo "-------------------------------------------------------------------------"

echo "y" | conda install -c conda-forge rasterio psycopg2 postgis aiohttp

echo "-------------------------------------------------------------------------"
echo " Copy data from S3"
echo "-------------------------------------------------------------------------"

# training data has to be copied into specific structure for YOLOv5 (TODO: is this comment correct?)
# images
aws s3 cp s3://image-classification-swimming-pools/training/swimming-pools/near_burwood_chips_640x640/ ${HOME}/datasets/pool/images/train2017 --exclude "*" --include "*.tif" --recursive --no-progress --quiet
aws s3 cp s3://image-classification-swimming-pools/training/swimming-pools/chips_gordon_19/ ${HOME}/datasets/pool/images/train2017 --exclude "*" --include "*.tif" --recursive --no-progress --quiet
# labels
aws s3 cp s3://image-classification-swimming-pools/training/swimming-pools/near_burwood_chips_640x640_labels/ ${HOME}/datasets/pool/labels/train2017 --exclude "*" --include "*.txt" --exclude "classes.txt" --recursive --no-progress --quiet
aws s3 cp s3://image-classification-swimming-pools/training/swimming-pools/chips_gordon_19_labels/ ${HOME}/datasets/pool/labels/train2017 --exclude "*" --include "*.txt" --exclude "classes.txt" --recursive --no-progress --quiet
echo "Training data copied"

# GNAF & property boundary tables
aws s3 cp s3://image-classification-swimming-pools/geoscape/gnaf-cad.dmp ${HOME} --no-progress --quiet
echo "Postgres dump file copied"

echo "-------------------------------------------------------------------------"
echo " Setup Postgres Database"
echo "-------------------------------------------------------------------------"

# start postgres
initdb -D postgres
pg_ctl -D postgres -l logfile start

# create new database
createdb --owner=ec2-user geo

# add PostGIS extension to database, create schema and tables
psql -d geo -f ${HOME}/03_create_tables.sql

# restore GNAF & Cad tables (ignore the 2 ALTER TABLE errors)
pg_restore -Fc -d geo -p 5432 -U ec2-user ${HOME}/gnaf-cad.dmp

echo "-------------------------------------------------------------------------"
echo " Import training data into Postgres (for reference & debugging only)"
echo "-------------------------------------------------------------------------"

python3 ${HOME}/04_load_training_data_to_postgres.py

echo "-------------------------------------------------------------------------"
echo " Run model training (~25 mins) or copy existing model from S3"
echo "-------------------------------------------------------------------------"

# run training & copy model to S3
#python3 ~/yolov5/train.py --data ~/pool.yaml
#aws s3 cp ~/yolov5/runs/train/exp/ s3://image-classification-swimming-pools/model/ --recursive

# copy previous model from S3
aws s3 cp s3://image-classification-swimming-pools/model/ ~/yolov5/runs/train/exp/ --recursive
