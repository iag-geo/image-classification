
# get directory this script is running from
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# load AWS vars
. ${GIT_HOME}/temp_ec2_vars.sh

# copy and run python script remotely
FILENAME="05_detect_pools.py"

scp -F ${SSH_CONFIG} ${SCRIPT_DIR}/${FILENAME} ${USER}@${INSTANCE_ID}:~/
ssh -F ${SSH_CONFIG} ${INSTANCE_ID} "conda activate yolov5; python3 ${FILENAME}"

# dump results from Postgres and copy locally
ssh -F ${SSH_CONFIG} ${INSTANCE_ID} "conda activate yolov5; pg_dump -Fc -d geo -t data_science.pool_images -t data_science.pool_labels -p 5432 -U ec2-user -f ~/pools.dmp --no-owner"
scp -F ${SSH_CONFIG} ${USER}@${INSTANCE_ID}:~/pools.dmp ${SCRIPT_DIR}/



#ssh -F ${SSH_CONFIG} ${INSTANCE_ID}

## get file count
#ls -lR /home/ec2-user/training-data/*/*.tif | wc -l
