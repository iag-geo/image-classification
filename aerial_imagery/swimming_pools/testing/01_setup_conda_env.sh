#!/usr/bin/env bash

# --------------------------------------------------------------------------------------------------------------------

PYTHON_VERSION="3.9"

# --------------------------------------------------------------------------------------------------------------------

echo "-------------------------------------------------------------------------"
echo "Creating new Conda Environment 'yolov5'"
echo "-------------------------------------------------------------------------"

# update Conda platform
echo "y" | conda update conda

# WARNING - removes existing environment
conda env remove --name yolov5

# Create Conda environment
echo "y" | conda create -n yolov5 python=${PYTHON_VERSION}

# restart Conda - bug in iTerm causing it to not work?
conda init
source ~/.bash_profile

# activate and setup env
conda activate yolov5
conda config --env --add channels conda-forge
conda config --env --set channel_priority strict

# reactivate for env vars to take effect
conda activate yolov5

echo "-------------------------------------------------------------------------"
echo " Downloading & installing YOLOv5"
echo "-------------------------------------------------------------------------"

git clone https://github.com/ultralytics/yolov5  # clone repo
cd yolov5
pip3 install -r requirements.txt  # install dependencies

echo "-------------------------------------------------------------------------"
echo " Installing additional Python packages"
echo "-------------------------------------------------------------------------"

echo "y" | conda install -c conda-forge rasterio psycopg2 owslib

# --------------------------
# extra bits
# --------------------------

## activate env
#conda activate yolov5

## shut down env
#conda deactivate

## delete env permanently
#conda env remove --name yolov5
