#!/usr/bin/env bash

# installs drivers and Python packages to enable YOLOv5 image classification

PYTHON_VERSION="3.9"
NVIDIA_DRIVER_VERSION="460.91.03"  # CUDA 11.2  #TODO: check if YOLOv5 works with CUDA 11.2 or 10.2 only?

# check if proxy server required
while getopts ":p:" opt; do
  case $opt in
  p)
    PROXY=$OPTARG
    ;;
  esac
done

#if [ -n "${PROXY}" ]; then
#  export no_proxy="localhost,127.0.0.1,:11";
#  export http_proxy="$PROXY";
#  export https_proxy=${http_proxy};
#  export HTTP_PROXY=${http_proxy};
#  export HTTPS_PROXY=${http_proxy};
#  export NO_PROXY=${no_proxy};
#
#  echo "-------------------------------------------------------------------------";
#  echo " Proxy set to ${http_proxy}";
#  echo "-------------------------------------------------------------------------";
#fi

echo "-------------------------------------------------------------------------"
echo " Installing git & kernel packages"
echo "-------------------------------------------------------------------------"

sudo yum -y install git kernel-devel-$(uname -r) kernel-headers-$(uname -r)

# set git proxy
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

echo "-------------------------------------------------------------------------"
echo " Installing Conda"
echo "-------------------------------------------------------------------------"

# download & install silently
curl -fSsl -O https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
chmod +x Miniconda3-latest-Linux-x86_64.sh
sh Miniconda3-latest-Linux-x86_64.sh -b

# initialise Conda & reload bash environment
${HOME}/miniconda3/bin/conda init
source .bashrc

# update
echo "y" | conda update conda

echo "-------------------------------------------------------------------------"
echo " Creating new Conda Environment 'yolov5'"
echo "-------------------------------------------------------------------------"

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

echo "-------------------------------------------------------------------------"
echo " Downloading & installing YOLOv5"
echo "-------------------------------------------------------------------------"

git clone https://github.com/ultralytics/yolov5  # clone repo
cd yolov5
pip3 install -r requirements.txt  # install dependencies

## create an in memory swapfile (if peformance issues)
#sudo fallocate -l 64G /swapfile
#sudo chmod 600 /swapfile
#sudo mkswap /swapfile
#sudo swapon /swapfile
#free -h  # check memory

echo "-------------------------------------------------------------------------"
echo " Installing additional Python packages"
echo "-------------------------------------------------------------------------"

echo "y" | conda install -c conda-forge rasterio psycopg2 s3fs


## remove proxy if set
#if [ -n "${PROXY}" ]; then
#  unset http_proxy
#  unset HTTP_PROXY
#  unset https_proxy
#  unset HTTPS_PROXY
#  unset no_proxy
#  unset NO_PROXY
#
#  git config --global --unset http.https://github.com.proxy
#  git config --global --unset http.https://github.com.sslVerify
#fi
