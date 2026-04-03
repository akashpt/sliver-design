# coding=utf-8
import cv2
import numpy as np
import time
import MVSDK.mvsdk as mvsdk


class MindVisionCamera:
    def __init__(self, camera_index=0, exposure_us=30000,r_gain = 180,g_gain = 100,b_gain = 200):
        self.camera_index = camera_index
        self.exposure_us = exposure_us

        self.hCamera = 0
        self.cap = None
        self.pFrameBuffer = None
        self.FrameBufferSize = 0
        self.monoCamera = False
        self.opened = False
        self.r_gain = r_gain
        self.g_gain = g_gain
        self.b_gain = b_gain

    def start(self):
        devs = mvsdk.CameraEnumerateDevice()
        if not devs:
            raise RuntimeError("No camera found")

        if self.camera_index >= len(devs):
            raise RuntimeError(f"Invalid camera index {self.camera_index}")

        dev = devs[self.camera_index]
        print("Opening:", dev.GetFriendlyName(), dev.GetPortType())

        try:
            self.hCamera = mvsdk.CameraInit(dev, -1, -1)
        except mvsdk.CameraException as e:
            raise RuntimeError(f"CameraInit failed ({e.error_code}): {e.message}")

        self.cap = mvsdk.CameraGetCapability(self.hCamera)
        self.monoCamera = (self.cap.sIspCapacity.bMonoSensor != 0)

        if self.monoCamera:
            print("Mono camera detected")
            mvsdk.CameraSetIspOutFormat(self.hCamera, mvsdk.CAMERA_MEDIA_TYPE_MONO8)
        else:
            print("Color camera detected -> BGR8 output")
            mvsdk.CameraSetIspOutFormat(self.hCamera, mvsdk.CAMERA_MEDIA_TYPE_BGR8)

        # continuous mode
        mvsdk.CameraSetTriggerMode(self.hCamera, 0)

        # fixed exposure
        mvsdk.CameraSetAeState(self.hCamera, 0)
        mvsdk.CameraSetExposureTime(self.hCamera, self.exposure_us)

        # start camera
        mvsdk.CameraPlay(self.hCamera)

        self.FrameBufferSize = (
            self.cap.sResolutionRange.iWidthMax *
            self.cap.sResolutionRange.iHeightMax *
            (1 if self.monoCamera else 3)
        )

        self.pFrameBuffer = mvsdk.CameraAlignMalloc(self.FrameBufferSize, 16)
        self.opened = True
        print("Camera opened successfully")
        self.set_gain(self.r_gain,self.g_gain,self.b_gain)

    def set_gain(self, r_gain, g_gain, b_gain):
        if not self.opened:
            raise RuntimeError("Camera not opened")

        if self.monoCamera:
            print("Mono camera: RGB gain not applicable")
            return

        mvsdk.CameraSetWbMode(self.hCamera, 0)   # auto WB off
        mvsdk.CameraSetGain(self.hCamera, int(r_gain), int(g_gain), int(b_gain))
        print(f"Manual gain set -> R:{r_gain} G:{g_gain} B:{b_gain}")

    def get_gain(self):
        if not self.opened:
            raise RuntimeError("Camera not opened")

        if self.monoCamera:
            return None

        r, g, b = mvsdk.CameraGetGain(self.hCamera)
        return r, g, b

    def auto_white_balance_once(self, wait_sec=1.0):
        if not self.opened:
            raise RuntimeError("Camera not opened")

        if self.monoCamera:
            print("Mono camera: white balance not applicable")
            return None

        # one-time white balance
        mvsdk.CameraSetWbMode(self.hCamera, 0)
        mvsdk.CameraSetOnceWB(self.hCamera)
        time.sleep(wait_sec)

        r, g, b = mvsdk.CameraGetGain(self.hCamera)
        print(f"One-time WB result -> R:{r} G:{g} B:{b}")

        # freeze those values
        mvsdk.CameraSetGain(self.hCamera, r, g, b)
        mvsdk.CameraSetWbMode(self.hCamera, 0)

        return r, g, b

    def set_image_tuning(self, gamma=None, contrast=None, saturation=None):
        if not self.opened:
            raise RuntimeError("Camera not opened")

        if gamma is not None:
            mvsdk.CameraSetGamma(self.hCamera, int(gamma))
            print("Gamma set:", gamma)

        if contrast is not None:
            mvsdk.CameraSetContrast(self.hCamera, int(contrast))
            print("Contrast set:", contrast)

        if saturation is not None and not self.monoCamera:
            mvsdk.CameraSetSaturation(self.hCamera, int(saturation))
            print("Saturation set:", saturation)

    def get_frame(self, resize_to=None, timeout=200):
        if not self.opened:
            raise RuntimeError("Camera not opened")

        try:
            pRawData, FrameHead = mvsdk.CameraGetImageBuffer(self.hCamera, timeout)
            mvsdk.CameraImageProcess(self.hCamera, pRawData, self.pFrameBuffer, FrameHead)
            mvsdk.CameraReleaseImageBuffer(self.hCamera, pRawData)

            frame_data = (mvsdk.c_ubyte * FrameHead.uBytes).from_address(self.pFrameBuffer)
            frame = np.frombuffer(frame_data, dtype=np.uint8)

            channels = 1 if FrameHead.uiMediaType == mvsdk.CAMERA_MEDIA_TYPE_MONO8 else 3
            frame = frame.reshape((FrameHead.iHeight, FrameHead.iWidth, channels))

            if channels == 1:
                frame = frame.reshape((FrameHead.iHeight, FrameHead.iWidth))

            if resize_to is not None:
                frame = cv2.resize(frame, resize_to, interpolation=cv2.INTER_LINEAR)

            return frame

        except mvsdk.CameraException as e:
            if e.error_code == mvsdk.CAMERA_STATUS_TIME_OUT:
                return None
            raise RuntimeError(f"Get frame failed ({e.error_code}): {e.message}")

    def stop(self):
        if self.pFrameBuffer:
            mvsdk.CameraAlignFree(self.pFrameBuffer)
            self.pFrameBuffer = None

        if self.hCamera:
            mvsdk.CameraUnInit(self.hCamera)
            self.hCamera = 0

        self.opened = False
        print("Camera closed")


# if __name__ == "__main__":
#     cam = MindVisionCamera(camera_index=0, exposure_us=60000)

#     try:
#         cam.start()
#         while True:
#             frame = cam.get_frame(resize_to=(2448, 2048), timeout=200)
#             if frame is None:
#                 continue
#             resize = cv2.resize(frame,(640,480))
#             cv2.imshow("MindVision Camera", resize)

#             key = cv2.waitKey(1) & 0xFF
#             if key == ord('q'):
#                 break

#     finally:
#         cam.stop()
#         cv2.destroyAllWindows()