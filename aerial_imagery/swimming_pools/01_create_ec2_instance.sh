#!/usr/bin/env bash

# Script builds a single EC2 instance with YOLOv5 (Python based) and Postgres/PostGIS installed
# Also copies pre-prepared training & reference data from S3 and imports it into Postgres
#
# Arguments:
#    -p : proxy address (if behind a proxy). e.g. http://myproxy.mycorp.corp:8080
#
# Note: script assumes you're not using a deep learning/ML AMI.
#   Comment out the NVIDIA driver install in 02_remote_setup.sh if you are
#
# Takes ~10 min to run

SECONDS=0*

# check if proxy server required
while getopts ":p:" opt; do
  case $opt in
  p)
    PROXY=$OPTARG
    ;;
  esac
done

echo "-------------------------------------------------------------------------"
echo " Start time : $(date)"
echo "-------------------------------------------------------------------------"
echo " Set temp local environment vars"
echo "-------------------------------------------------------------------------"

AMI_ID="ami-00764cc25c2985858"  # private AMI - choose your own preferred AMI
#INSTANCE_TYPE="m5d.12xlarge"  # CPU only
#INSTANCE_TYPE="p3.2xlarge"  # not available in my VPC but should be faster
INSTANCE_TYPE="g4dn.8xlarge"  # NVIDIA Tesla T4 instance

USER="ec2-user"

SSH_CONFIG="${HOME}/.ssh/aws-sandbox-config"

# load AWS parameters
. ${HOME}/.aws/iag_ec2_vars.sh

# script to check instance status
PYTHON_SCRIPT="import sys, json
try:
    print(json.load(sys.stdin)['InstanceStatuses'][0]['InstanceState']['Name'])
except:
    print('pending')"

# get directory this script is running from
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

echo "-------------------------------------------------------------------------"
echo " Create EC2 instance and wait for startup"
echo "-------------------------------------------------------------------------"

# create EC2 instance
INSTANCE_ID=$(aws ec2 run-instances \
--image-id ${AMI_ID} \
--count 1 \
--tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=hs_testing}]" \
--instance-type ${INSTANCE_TYPE} \
--key-name ${AWS_KEYPAIR} \
--security-group-ids ${AWS_SECURITY_GROUP} \
--subnet-id ${AWS_SUBNET} \
--iam-instance-profile "Name=${AWS_IAM_PROFILE}" | \
python3 -c "import sys, json; print(json.load(sys.stdin)['Instances'][0]['InstanceId'])")

echo "Instance ${INSTANCE_ID} created"

# this doesn't work everytime, hence the while/do below
aws ec2 wait instance-exists --instance-ids ${INSTANCE_ID}

# wait for instance to fire up
INSTANCE_STATE="pending"
while [ $INSTANCE_STATE != "running" ]; do
    sleep 5
    INSTANCE_STATE=$(aws ec2 describe-instance-status --instance-id  ${INSTANCE_ID} | python3 -c "${PYTHON_SCRIPT}")
    echo "  - Instance status : ${INSTANCE_STATE}"
done

INSTANCE_IP_ADDRESS=$(aws ec2 describe-instances --instance-ids ${INSTANCE_ID} | \
python3 -c "import sys, json; print(json.load(sys.stdin)['Reservations'][0]['Instances'][0]['PrivateIpAddress'])")
echo "  - Private IP address : ${INSTANCE_IP_ADDRESS}"

# save instance vars to a local file for easy SSH commands
echo "export SCRIPT_DIR=${SCRIPT_DIR}" > ~/git/temp_ec2_vars.sh
echo "export USER=${USER}" >> ~/git/temp_ec2_vars.sh
echo "export SSH_CONFIG=${SSH_CONFIG}" >> ~/git/temp_ec2_vars.sh
echo "export INSTANCE_ID=${INSTANCE_ID}" >> ~/git/temp_ec2_vars.sh
echo "export INSTANCE_IP_ADDRESS=${INSTANCE_IP_ADDRESS}" >> ~/git/temp_ec2_vars.sh

# wait for SSH to start
INSTANCE_READY=""
while [ ! $INSTANCE_READY ]; do
    echo "  - Waiting for ready status"
    sleep 5
    set +e
    OUT=$(ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes ${USER}@$INSTANCE_ID 2>&1 | grep "Permission denied" )
    [[ $? = 0 ]] && INSTANCE_READY='ready'
    set -e
done

echo "-------------------------------------------------------------------------"
echo " Copy AWS credentials & supporting files and run remote script"
echo "-------------------------------------------------------------------------"

# copy AWS creds to access S3
ssh -F ${SSH_CONFIG} -o StrictHostKeyChecking=no ${INSTANCE_ID} 'mkdir ~/.aws'
scp -F ${SSH_CONFIG} -r ${HOME}/.aws/credentials ${USER}@${INSTANCE_ID}:~/.aws/credentials

# copy required scripts
scp -F ${SSH_CONFIG} ${SCRIPT_DIR}/02_remote_setup.sh ${USER}@${INSTANCE_ID}:~/
scp -F ${SSH_CONFIG} ${SCRIPT_DIR}/03_create_tables.sql ${USER}@${INSTANCE_ID}:~/
scp -F ${SSH_CONFIG} ${SCRIPT_DIR}/04_load_training_data_to_postgres.py ${USER}@${INSTANCE_ID}:~/
scp -F ${SSH_CONFIG} ${SCRIPT_DIR}/05_train_model.sh ${USER}@${INSTANCE_ID}:~/
scp -F ${SSH_CONFIG} ${SCRIPT_DIR}/06_detect_pools.py ${USER}@${INSTANCE_ID}:~/
scp -F ${SSH_CONFIG} ${SCRIPT_DIR}/pool.yaml ${USER}@${INSTANCE_ID}:~/

# setup proxy (if required) install packages & environment and import data
if [ -n "${PROXY}" ]; then
  # set proxy permanently if required
  ssh -F ${SSH_CONFIG} ${USER}@${INSTANCE_ID} \
  'cat << EOF > ~/environment
  no_proxy="169.254.169.254,localhost,127.0.0.1,:11"
  http_proxy="'"${PROXY}"'"
  https_proxy="'"${PROXY}"'"
  proxy="'"${PROXY}"'"
  HTTP_PROXY="'"${PROXY}"'"
  HTTPS_PROXY="'"${PROXY}"'"
  PROXY="'"${PROXY}"'"
  NO_PROXY="169.254.169.254,localhost,127.0.0.1,:11"
  EOF'
  ssh -F ${SSH_CONFIG} ${USER}@${INSTANCE_ID} "sudo cp ~/environment /etc/environment"

  ssh -F ${SSH_CONFIG} ${USER}@${INSTANCE_ID} "sh ./02_remote_setup.sh -p ${PROXY}"
else
  ssh -F ${SSH_CONFIG} ${USER}@${INSTANCE_ID} "sh ./02_remote_setup.sh"
fi

echo "-------------------------------------------------------------------------"
duration=$SECONDS
echo " End time : $(date)"
echo " Build took $((duration / 60)) mins"
echo "----------------------------------------------------------------------------------------------------------------"


# HANDY STUFF BELOW

# connect
#ssh -F ${SSH_CONFIG} ${INSTANCE_ID}

# load ec2 vars
# . ~/git/temp_ec2_vars.sh
