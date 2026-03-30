import cv2
import base64
import json
import os
import datetime
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QStandardPaths, QDir


class Bridge(QObject):

    frame_signal = pyqtSignal(str)

    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

        # Camera
        self.cap = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.grab_frame)

        # Config file path
        config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        QDir().mkpath(config_dir)
        self.config_path = os.path.join(config_dir, "userConfig.json")

    # ------------------- CAMERA -------------------
    @pyqtSlot(result=str)
    def startCamera(self):
        self.stopCamera()
        self.cap = cv2.VideoCapture(0)

        if not self.cap.isOpened():
            print("❌ Cannot open camera")
            return "ERROR: Cannot open camera"

        print("✅ Camera started successfully")
        self.timer.start(30)   # ~33 fps
        return "OK"

    @pyqtSlot()
    def stopCamera(self):
        print("🛑 Stopping camera...")
        if self.timer.isActive():
            self.timer.stop()

        if self.cap is not None:
            if self.cap.isOpened():
                self.cap.release()
            self.cap = None

        print("✅ Camera stopped successfully")

    def grab_frame(self):
        if self.cap is None or not self.cap.isOpened():
            return

        ret, frame = self.cap.read()
        if ret:
            try:
                _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                jpg_as_text = base64.b64encode(buffer).decode("utf-8")
                self.frame_signal.emit(jpg_as_text)
            except Exception as e:
                print(f"❌ Error encoding frame: {e}")

    # ------------------- USER CONFIG -------------------
    @pyqtSlot(result=str)
    def readUserConfig(self):
        """Read userConfig.json"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                print(f"✅ Loaded userConfig.json: {data}")
                return json.dumps(data)
            else:
                default = {"jobId": "", "threshold": "", "lastSaved": ""}
                return json.dumps(default)
        except Exception as e:
            print(f"❌ Error loading userConfig.json: {e}")
            return json.dumps({"jobId": "", "threshold": "", "lastSaved": ""})

    @pyqtSlot(str)
    def writeUserConfig(self, json_string):
        """Save userConfig.json"""
        try:
            data = json.loads(json_string)
            data["lastSaved"] = datetime.datetime.now().isoformat()

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"💾 Saved userConfig.json → Job: {data.get('jobId')}, Threshold: {data.get('threshold')}")
        except Exception as e:
            print(f"❌ Failed to save userConfig.json: {e}")

    # ------------------- JOB LIST (via Bridge) -------------------
    @pyqtSlot(result=str)
    def getJobList(self):
        """Return available Job IDs via bridge"""
        jobs = [
            {"id": "75", "name": "Product A"},
            {"id": "102", "name": "Product B"},
            {"id": "145", "name": "Product C"},
            {"id": "208", "name": "Product D"},
            {"id": "319", "name": "Product E"},
        ]
        return json.dumps({"jobs": jobs})

    # ------------------- NAVIGATION -------------------
    @pyqtSlot()
    def goHome(self):
        self.app_ref.load_page("index.html")

    @pyqtSlot()
    def goReport(self):
        self.app_ref.open_report_window()

    @pyqtSlot()
    def goTraining(self):
        self.app_ref.load_page("training.html")