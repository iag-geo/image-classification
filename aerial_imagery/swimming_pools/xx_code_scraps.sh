
# run training
conda activate yolov5
cd yolov5
python3 train.py --data ~/pool.yaml

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




~/yolov5/runs/train/exp5/