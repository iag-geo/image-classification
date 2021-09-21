
# get directory this script is running from
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# load AWS vars
. ${GIT_HOME}/temp_ec2_vars.sh

# copy and run python script remotely
FILENAME="04_load_training_data_to_postgres.py"

scp -F ${SSH_CONFIG} ${SCRIPT_DIR}/${FILENAME} ${USER}@${INSTANCE_ID}:~/
ssh -F ${SSH_CONFIG} ${INSTANCE_ID} "conda activate yolov5; python3 ${FILENAME}"


#ssh -F ${SSH_CONFIG} ${INSTANCE_ID}

## get file count
#ls -lR /home/ec2-user/training_data/*/*.tif | wc -l
