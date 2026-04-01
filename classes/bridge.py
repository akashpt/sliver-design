import cv2
import base64
import json
import os
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QStandardPaths, QDir
from PyQt5.QtWidgets import QApplication  # Only if needed elsewhere


class Bridge(QObject):

    frame_signal = pyqtSignal(str)

    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

        # Camera related
        self.cap = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.grab_frame)

        # Config file path
        config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        QDir().mkpath(config_dir)
        self.config_path = os.path.join(config_dir, "userConfig.json")

    # ====================== CAMERA ======================

    @pyqtSlot(result=str)
    def startCamera(self):
        """Start webcam and begin emitting frames"""
        if self.cap is not None and self.cap.isOpened():
            print("ℹ  Camera already running.")
            return "OK"

        self.cap = cv2.VideoCapture(0)  # Change to 1, 2 if needed

        if not self.cap.isOpened():
            print("❌ Cannot open camera")
            return "ERROR: Cannot open camera"

        print("✅ Camera started successfully")
        self.timer.start(30)  # ~33 fps
        return "OK"

    @pyqtSlot()
    def stopCamera(self):
        """Stop camera"""
        if self.timer.isActive():
            self.timer.stop()

        if self.cap is not None:
            if self.cap.isOpened():
                self.cap.release()
            self.cap = None

        print("⏹ Camera stopped.")

    def grab_frame(self):
        """Read frame from camera and emit base64 image"""

        # check camera
        if self.cap is None or not self.cap.isOpened():
            return

        # read frame
        ret, frame = self.cap.read()
        if not ret or frame is None:
            return

        try:
            # encode frame to jpg
            success, buffer = cv2.imencode(
                ".jpg",
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, 85]
            )

            if success:
                # numpy buffer → bytes → base64 string
                jpg_base64 = base64.b64encode(
                    buffer.tobytes()
                ).decode("utf-8")

                # emit frame to JS
                self.frame_signal.emit(jpg_base64)

        except Exception as e:
            print("Frame send error:", e)

    # ====================== OTHER METHODS ======================

    @pyqtSlot(result=str)
    def current_job_id(self):
        data = {
            "job_id": "checking",
            "threshold": "40",
            "data": {
                "jobs": ["Product A", "Product B", "Product C"],
                "thresholds": [1, 2, 3, 4, 5, 6],
            },
        }
        return json.dumps(data)

    @pyqtSlot(result=str)
    def get_defect_images(self):
        data = {
            "images": [
                "https://placehold.co/640x480/ff4d6d/white?text=EDGE+SLIVER",
                "https://placehold.co/640x480/ef233c/fff?text=DENT+DEFECT",
                "https://picsum.photos/seed/metaldefect1/640/480",
                "https://placehold.co/640x480/c1121f/white?text=SCRATCH+DEFECT",
                "https://picsum.photos/seed/industrialdefect/640/480",
                "https://placehold.co/640x480/d00000/fff?text=CRACK+DETECTED",
            ]
        }
        return json.dumps(data)

    @pyqtSlot(str)
    def saveUserConfig(self, json_string):
        try:
            data = json.loads(json_string)
            if "lastSaved" not in data:
                data["lastSaved"] = datetime.now().isoformat()
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"💾 Saved userConfig.json")
        except Exception as e:
            print(f"❌ Failed to save userConfig.json: {e}")

    @pyqtSlot(str)
    def saveTrainingSession(self, json_str: str):
        try:
            data = json.loads(json_str)
            record = {
                "jobId": data.get("jobId", ""),
                "count": data.get("count", ""),
                "yarn": data.get("yarn", ""),
                "color": data.get("color", ""),
                "savedAt": datetime.now().isoformat(timespec="seconds"),
            }

            session_path = os.path.join(
                os.path.dirname(self.config_path), "trainingSession.json"
            )
            with open(session_path, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2)

            print(f"✅ Training session saved: {record['jobId']}")
        except Exception as e:
            print(f"❌ saveTrainingSession error: {e}")

    # Navigation
    @pyqtSlot()
    def goHome(self):
        self.app_ref.load_page("index.html")

    @pyqtSlot()
    def goReport(self):
        self.app_ref.open_report_window()

    @pyqtSlot()
    def goTraining(self):
        self.app_ref.load_page("training.html")
