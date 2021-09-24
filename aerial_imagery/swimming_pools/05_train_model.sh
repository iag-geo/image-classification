
# This runs the residential swimming pool model training and saves the model to AWS S3

# start environment
conda activate yolov5

# run on 1 GPU using the basic YOLOv5 S model
python3 ~/yolov5/train.py --data ~/pool.yaml

## run on 4 GPUs (untested)
#python -m torch.distributed.launch --nproc_per_node 4 train.py --data ~/pool.yaml--weights yolov5m.pt --device 0,1,2,3

# training takes ~25 mins on a g4dn.8xlarge EC2 instance (1 GPU)
#  300 epochs completed in 0.414 hours.
#  Optimizer stripped from runs/train/exp/weights/last.pt, 14.4MB
#  Optimizer stripped from runs/train/exp/weights/best.pt, 14.4MB
#  Results saved to runs/train/exp

# copy training results to S3
aws s3 cp ~/yolov5/runs/train/exp/ s3://image-classification-swimming-pools/model/ --recursive
