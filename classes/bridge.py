import cv2
import base64
import json
import os
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QStandardPaths, QDir
from PyQt5.QtWidgets import QApplication  # Only if needed elsewhere

# from classes.mindvision import MindVisionCamera
from path import INDEX_PAGE, TRAINING_PAGE


class Bridge(QObject):

    frame_signal = pyqtSignal(str)
    sliver_data =  pyqtSignal(str)

    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

        # Camera
        self.camera = None
        self.cap = None
        self.use_mindvision = False
        self.camera_open = False

        # Frame timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.grab_frame)

        self.data_time = QTimer()
        self.data_time.timeout.connect(self.sliver_datas)

        # Config file path
        config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        QDir().mkpath(config_dir)
        self.config_path = os.path.join(config_dir, "userConfig.json")

    # ====================== CAMERA ======================
    @pyqtSlot(str, str, result=str)
    def saveUserConfig(self, job_id, threshold):
        try:
            data = {
                "jobId": job_id,
                "threshold": threshold,
                "lastSaved": datetime.now().isoformat(),
            }

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            print("✅ Process Confirmed")
            print("Job:", job_id)
            print("Threshold:", threshold)

            return json.dumps({
                "status": "success",
                "message": "Process Confirmed",
                "data": data
            })

        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": str(e)
            })
    
    
    # // start camera--------------------------------
    @pyqtSlot(result=str)
    def startCamera(self):

        # ─── Already Running ─────────────────────────────
        if self.camera_open:
            print("⚠️ Camera already running")
            return "Camera Already Running"

        print("🔥 Starting camera...")

        # ─── Try MindVision Camera First ─────────────────
        try:
            # self.camera = MindVisionCamera()
            self.camera.start()

            if self.camera.hCamera != 0:
                self.use_mindvision = True
                print("✅ Using MindVision Camera")

            else:
                raise Exception("MindVision handle invalid")

        except Exception as e:
            print("⚠️ MindVision not available:", e)

            self.camera = None
            self.use_mindvision = False

            # ─── Fallback → Webcam ───────────────────────
            self.cap = cv2.VideoCapture(0)

            if not self.cap.isOpened():
                print("❌ Webcam not available")
                self.camera_open = False
                return "Camera not available"

            print("✅ Using Webcam")

        # ─── Start Frame Timer ───────────────────────────
        self.camera_open = True
        self.timer.start(30)
        self.data_time.start(500)

        print("🎥 Camera Started Successfully")
        return "OK"

    # // stop camera--------------------------------
    @pyqtSlot()
    def stopCamera(self):
        if not self.camera_open:
            print("⚠️ Camera already stopped")
            return

        print("🛑 Stopping camera...")

        self.timer.stop()
        self.data_time.stop()

        if self.use_mindvision and self.camera:
            try:
                self.camera.stop()
                print("✅ MindVision stopped")
            except Exception as e:
                print("❌ MindVision stop error:", e)

            self.camera = None

        if self.cap:
            self.cap.release()
            self.cap = None
            print("✅ Webcam released")

        self.camera_open = False
        print("✅ Camera fully stopped")

    def sliver_datas(self):
        try:
            data = {
                "total_count":10,
                "inspect":5,
                "defect":5,
                "defect_image":[
                    "https://picsum.photos/seed/metaldefect1/640/480",
                    "https://placehold.co/640x480/ef233c/fff?text=DENT+DEFECT",
                    "https://picsum.photos/seed/metaldefect1/640/480",
                    "https://placehold.co/640x480/ff4d6d/white?text=EDGE+SLIVER",
                ]
            }

            self.sliver_data.emit(json.dumps(data))

            
        except Exception as e:
            print(e)

    def grab_frame(self):
        try:
            frame = None

            # =========================
            # MINDVISION CAMERA
            # =========================
            if self.use_mindvision and self.camera:
                frame = self.camera.get_frame()

                if frame is None:
                    print("⚠️ MindVision lost → switching to webcam")
                    self.use_mindvision = False
                    self.cap = cv2.VideoCapture(0)
                    return

                # frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # =========================
            # WEBCAM
            # =========================
            elif self.cap:
                ret, frame = self.cap.read()
                if not ret:
                    return

            else:
                return

            # =========================
            # 🔥 ROTATE FRAME
            # =========================
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

            # =========================
            # SAVE CURRENT FRAME
            # =========================
            self.current_frame = frame.copy()

            # =========================
            # SEND TO UI
            # =========================
            _, buffer = cv2.imencode(".jpg", frame)
            jpg = base64.b64encode(buffer).decode("utf-8")
            self.frame_signal.emit(jpg)

            # =========================
            # 🔥 RUN DETECTION
            # =========================
            # if self.detector and not self.training_running:
            #     print("🚀 Detection running...")
            #     self.run_detection()

        except Exception as e:
            print("❌ frame error:", e)

    # ====================== OTHER METHODS ======================

    @pyqtSlot(result=str)
    def current_job_id(self):
        data = {
            "job_id": "Product A",
            "threshold": "45",
            "data": {
                "jobs": ["Product A", "Product B", "Product C"],
                "thresholds": [1, 2, 3, 4, 5, 6],
            },
        }
        return json.dumps(data)

    @pyqtSlot(result=str)
    def get_defect_images(self):

        default_images = [
            "https://picsum.photos/seed/metaldefect1/640/480",
            "https://placehold.co/640x480/ef233c/fff?text=DENT+DEFECT",
            "https://picsum.photos/seed/metaldefect1/640/480",
            "https://placehold.co/640x480/ff4d6d/white?text=EDGE+SLIVER",
        ]

        # Camera detected images
        extra_images = [
            "https://placehold.co/640x480/ff4d6d/white?text=EDGE+SLIVER",
            "https://placehold.co/640x480/ff4d6d/white?text=EDGE+SLIVER"
        ]

        images = []

        # ✅ Add all trained images
        images.extend(default_images)

        # ✅ Compare detected images
        for img in extra_images:

            # IMAGE NOT MATCHED → DEFECT
            if img not in default_images:
                print("🔥 DEFECT IMAGE:", img)
                images.append(img)

        return json.dumps({"images": images})



    @pyqtSlot(str, result=str)
    def get_counts(self, job_id):
        if job_id == "Product A":
            inspected = 120
            good = 110
            defective = 10
        elif job_id == "Product B":
            inspected = 90
            good = 80
            defective = 10
        else:
            # default fallback
            inspected = 0
            good = 0
            defective = 0

        data = {
            "job_id": job_id,
            "inspected": inspected,
            "good": good,
            "defective": defective,
        }
        return json.dumps(data)

  
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
        self.app_ref.load_page(INDEX_PAGE)

    @pyqtSlot()
    def goReport(self):
        self.app_ref.open_report_window()

    @pyqtSlot()
    def goTraining(self):
        self.app_ref.load_page(TRAINING_PAGE)
