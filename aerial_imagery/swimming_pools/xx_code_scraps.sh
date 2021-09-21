
# run training
conda activate yolov5

python3 ~/yolov5/train.py --data ~/pool.yaml

# training takes ~25 mins on a g4dn.8xlarge EC2 instance
#  300 epochs completed in 0.414 hours.
#  Optimizer stripped from runs/train/exp5/weights/last.pt, 14.4MB
#  Optimizer stripped from runs/train/exp5/weights/best.pt, 14.4MB
#  Results saved to runs/train/exp5

# copy training results to S3
aws s3 cp ~/yolov5/runs/train/exp5/ s3://image-classification-swimming-pools/model/ --recursive



# copy training results to EC2
aws s3 cp s3://image-classification-swimming-pools/model/ ~/yolov5/runs/train/exp/ --recursive



# copy training results to Macbook
aws s3 cp s3://image-classification-swimming-pools/model/ ${HOME}/tmp/image-classification/model/ --recursive





# run inference
cp ~/datasets/pool/images/train2017/merged-gordon-19_151.143_-33.76.tif ~/detect/test_image.tif

python3 ~/yolov5/detect.py --img 640 --source ~/detect/test_image.tif --weights ~/yolov5/runs/train/exp5/weights/best.pt --conf-thres 0.4 --save-txt

#Model Summary: 224 layers, 7053910 parameters, 0 gradients, 16.3 GFLOPs
#image 1/1 /home/ec2-user/detect/test_image.tif: 640x640 6 pools, Done. (0.015s)
#Speed: 0.6ms pre-process, 14.5ms inference, 1.3ms NMS per image at shape (1, 3, 640, 640)
#Results saved to runs/detect/exp2

# copy results locally
scp -F ${SSH_CONFIG} ${USER}@${INSTANCE_ID}:~/runs/detect/exp3/test_image.tif ${SCRIPT_DIR}/testing/test_image.tif
scp -F ${SSH_CONFIG} ${USER}@${INSTANCE_ID}:~/runs/detect/exp3/labels/* ${SCRIPT_DIR}/testing/labels/