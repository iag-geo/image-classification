#!/usr/bin/env bash

# --------------------------------------------------------------------------------------------------------------------

PYTHON_VERSION="3.8"

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

# activate and setup env
conda activate yolov5
conda config --env --add channels conda-forge
conda config --env --set channel_priority strict

# reactivate for env vars to take effect
conda activate yolov5

# install packages
echo "y" | conda install -c conda-forge rasterio owslib psycopg2

# --------------------------
# extra bits
# --------------------------

## activate env
#conda activate yolov5

## shut down env
#conda deactivate

## delete env permanently
#conda env remove --name yolov5
