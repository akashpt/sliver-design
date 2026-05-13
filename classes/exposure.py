import MVSDK.mvsdk as mvsdk
dev_list = mvsdk.CameraEnumerateDevice()
cam = mvsdk.CameraInit(dev_list[0], -1, -1)

exp_min, exp_max, exp_def = mvsdk.CameraGetExposureTimeRange(cam)

print("MIN:", exp_min)
print("MAX:", exp_max)
print("DEFAULT:", exp_def)

mvsdk.CameraUnInit(cam)



#run command
# cd ~/Documents/i_sliver-design
# PYTHONPATH=. python3 classes/exposure.py