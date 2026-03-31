import cv2
import base64
import json
import os
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QStandardPaths, QDir


class Bridge(QObject):

    frame_signal = pyqtSignal(str)

    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

        # Camera related
        self.cap = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.grab_frame)

        # Config file path (persistent across sessions)
        config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        QDir().mkpath(config_dir)  # Create folder if it doesn't exist
        self.config_path = os.path.join(config_dir, "userConfig.json")

    # ------------------- CAMERA -------------------
    @pyqtSlot(result=str)
    def startCamera(self):
        """Start the camera and begin sending frames"""
        self.stopCamera()

        self.cap = cv2.VideoCapture(0)

        if not self.cap.isOpened():
            print("❌ Cannot open camera")
            return "ERROR: Cannot open camera"

        print("✅ Camera started successfully")
        self.timer.start(30)  # ~33 fps
        return "OK"

    @pyqtSlot()
    def stopCamera(self):
        """Properly stop camera and timer"""
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

    # ------------------- DROPDOWN DATA -------------------
    @pyqtSlot(result=str)
    def current_job_id(self):
        """Return available jobs and thresholds for the UI dropdowns"""
        data = {
            "jobs": ["Product A", "Product B", "Product C"],
            "thresholds": [1, 2, 3, 4, 5, 6],
        }

        value = {
            "job_id": "checking",
            "threshold": "40",
            "data": data,
        }

        return json.dumps(value)

    # ------------------- USER CONFIG (NEW) -------------------
    @pyqtSlot(result=str)
    def get_defect_images(self):
        data = {
            "images": [
                "https://placehold.co/640x480/ff4d6d/white?text=EDGE+SLIVER",
                "https://placehold.co/640x480/ef233c/fff?text=DENT+DEFECT",
                "https://picsum.photos/seed/metaldefect1/640/480",
                "https://placehold.co/640x480/c1121f/white?text=SCRATCH+DEFECT",
                "https://picsum.photos/seed/industrialdefect/640/480",
                "https://placehold.co/640x480/d00000/fff?text=CRACK+DETECTED"
            ]
        }

        return json.dumps(data)

    @pyqtSlot(str)
    def saveUserConfig(self, json_string):
        """Save JSON string to userConfig.json"""
        try:
            data = json.loads(json_string)

            # Ensure we always have lastSaved timestamp
            if "lastSaved" not in data:
                data["lastSaved"] = ""

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"💾 Saved userConfig.json → {data}")
        except Exception as e:
            print(f"❌ Failed to save userConfig.json: {e}")

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
