import cv2
import base64
import json
import os
import sqlite3
import random
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QStandardPaths, QDir
from PyQt5.QtWidgets import QApplication  # Only if needed elsewhere
from classes.mindvision import MindVisionCamera
from path import *
from classes.training import StripColorTraining
from classes.prediction import StripColorPrediction


class Bridge(QObject):

    frame_signal = pyqtSignal(str)
    counts_signal = pyqtSignal(str)

    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

        #database
        self.db_path = str(DB_FILE)   # set DB path
        self.init_db()    
        print("DB Path:", self.db_path)            # create table automatically

         # Camera
        self.camera = None
        self.cap = None
        self.use_mindvision = False
        self.camera_open = False
        self.current_frame = None
        self.training_running = False
        self.training_folder_name = ""
        self.training_save_interval = 1000   # milliseconds
        self.last_training_save_time = 0

        # Frame timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.grab_frame)

        self.inspected = 0
        self.good = 0
        self.bad = 0

        # Config file path
        # config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        # QDir().mkpath(config_dir)
        # self.config_path = os.path.join(config_dir, "userConfig.json")        
        self.config_path= str(USER_CONFIG_FILE)

        # Prediction Class
        self.detector = StripColorPrediction()

        self.model_key, self.threshold = self.get_job_from_config()

        if self.threshold:
            self.detector.color_threshold = float(self.threshold)


        # For testing
        self.test_image_path = r"/home/godzilla/Downloads/sample_sliver.bmp"
        self.test_frame = cv2.imread(self.test_image_path)


    # ====================== CAMERA ======================
    # ====================== SAVE USER CONFIG ======================

    @pyqtSlot(str, str, result=str)
    def saveUserConfig(self, job_id, threshold):
        # print("🔥 saveUserConfig CALLED") 
        try:
            data = {
                "job_id": job_id,
                "threshold": threshold,
                "lastSaved": datetime.now().isoformat(),
            }

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)  #w py dict into json

            print("✅ Process Confirmed")
            print("Job:", job_id)
            print("Threshold:", threshold)
           

            return json.dumps({
                "status": "success",
                "message": "Process Confirmed",
                "data": data
            }) #con py dict to json str
        
        

        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": str(e)
            })
        
    def get_job_from_config(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f) # json r con to py dict

                return config.get("job_id", ""), config.get("threshold", "")
        except Exception as e:
            print("❌ Error reading config:", e)

        return "", ""
    
    @pyqtSlot()
    def resetUserConfig(self):
        try:
            empty_config = {
                "job_id": "",
                "threshold": "",
                "lastSaved": datetime.now().isoformat()
            }

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(empty_config, f, indent=2)

            print("Config reset successfully")

        except Exception as e:
            print("Reset config error:", e)

    def get_training_job_folder(self, job_id: str, clear_existing: bool = False):
        job_id = (job_id or "").strip()

        if not job_id:
            job_id = "Unknown_Product"

        safe_job_id = "".join(
            ch if ch.isalnum() or ch in (" ", "_", "-") else "_"
            for ch in job_id
        ).strip()

        job_folder = TRAINING_IMAGES_DIR / safe_job_id
        job_folder.mkdir(parents=True, exist_ok=True)

        if clear_existing:
            for file_path in job_folder.iterdir():
                if file_path.is_file():
                    try:
                        file_path.unlink()
                        print(f"🗑 Deleted old training image: {file_path.name}")
                    except Exception as e:
                        print(f"❌ Could not delete {file_path.name}: {e}")

        return job_folder


    def save_training_image(self, frame, job_id: str):
        """
        Save one training image inside:
        Sliver_Data/data/training_images/<job_id>/
        """
        try:
            job_folder = self.get_training_job_folder(job_id)

            filename = f"train_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.bmp"
            file_path = job_folder / filename

            ok = cv2.imwrite(str(file_path), frame)
            if not ok:
                raise Exception("cv2.imwrite failed")

            print(f"✅ Training image saved: {file_path}")
            return str(file_path)

        except Exception as e:
            print(f"❌ save_training_image error: {e}")
            return ""
        
   
    @pyqtSlot(result=str)
    def startCamera(self):
        if self.camera_open:
            print("⚠️ Camera already running")
            return "Camera Already Running"

        print("🔥 Starting camera...")

        try:
            self.camera = MindVisionCamera()
            self.camera.start()

            if self.camera.hCamera != 0:
                self.use_mindvision = True
                print("✅ Using MindVision Camera")
            else:
                raise Exception("MindVision not available")
                # return "Camera not available"

        except Exception as e:
            print("⚠️ MindVision not available:", e)

            self.camera = None
            self.use_mindvision = False

            self.cap = cv2.VideoCapture(0)

            if not self.cap.isOpened():
                print("❌ Webcam not available")
                return "Camera not available"

            print("✅ Using Webcam")
        self.camera_open = True

        # Grab one frame immediately so current_frame is ready
        self.grab_frame()

        # Continue live updates
        self.timer.start(1000)

        return "OK"

    @pyqtSlot()
    def stopCamera(self):
        if not self.camera_open:
            print("⚠️ Camera already stopped")
            return

        print("🛑 Stopping camera...")

        self.timer.stop()

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
        self.insert_report()

    def grab_frame(self):
        try:
            frame = None


            # For testing
            if self.test_image_path:
                frame = cv2.imread(self.test_image_path)
                frame = self.test_frame.copy()

                if frame is None:
                    print("Test image not found")
                    return

            # =========================
            # MINDVISION CAMERA
            # =========================
            elif self.use_mindvision and self.camera:
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
            # frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

            # =========================
            # SAVE CURRENT FRAME
            # =========================
            self.current_frame = frame.copy()

            if self.training_running and self.training_folder_name:
                current_time = int(datetime.now().timestamp() * 1000)

                if current_time - self.last_training_save_time >= self.training_save_interval:
                    saved_path = self.save_training_image(
                        self.current_frame.copy(),
                        self.training_folder_name
                    )

                    if saved_path:
                        print(f"✅ Training image auto-saved: {saved_path}")
                        self.last_training_save_time = current_time
                    else:
                        print("❌ Training image auto-save failed")
            # =========================
            # RUN DETECTION PER FRAME
            # =========================
            status = self.run_detection(frame)

            counts_data = {
                "inspected": self.inspected,
                "good": self.good,
                "bad": self.bad,
                "status": status
            }

            self.counts_signal.emit(json.dumps(counts_data))

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


    def run_detection(self, frame):
         # Every frame is inspected
        self.inspected += 1

        # is_defect = random.random() < 0.3

        # if is_defect:
        #     self.bad += 1
        #     status = "bad"
        # else:
        #     self.good += 1
        #     status = "good"

        # return status

        # Get model + threshold
        model_key, threshold = self.get_job_from_config()

        if threshold:
            self.detector.color_threshold = float(threshold)

        # Prediction file function
        status, processed_img, raw_img, bad_count, bad_indices = self.detector.process_image(frame, model_key)

        # Update counts
        if status == "good":
            self.good += 1
        elif status == "defect":
            self.bad += 1

        # Replace frame with processed image 
        # if processed_img is not None:
        #     self.current_frame = processed_img

        return status

    # ====================== OTHER METHODS ======================

    # @pyqtSlot(result=str)
    # def current_job_id(self):
    #     data = {
    #         "job_id": "Product A",
    #         "threshold": "45",
    #         "data": {
    #             "jobs": ["Product A", "Product B", "Product C"],
    #             "thresholds": [1, 2, 3, 4, 5, 6],
    #         },
    #     }
    #     return json.dumps(data)

    def get_model_job_ids(self):
        try:
            if not MODELS_DIR.exists():
                return []

            job_ids = sorted(
                [item.name for item in MODELS_DIR.iterdir() if item.is_dir()]
            )
            return job_ids

        except Exception as e:
            print("❌ Error reading model job ids:", e)
            return []

    @pyqtSlot(result=str)
    def current_job_id(self):
        default_threshold = "45"

        try:
            jobs = self.get_model_job_ids()

            # Fallback if models folder is empty
            if not jobs:
                jobs = []

            default_job = jobs[0] if jobs else ""

            job_id = default_job
            threshold = default_threshold

            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

                saved_job_id = config.get("job_id", "")
                saved_threshold = config.get("threshold", default_threshold)

                # use saved job only if it exists in models folder
                if saved_job_id in jobs:
                    job_id = saved_job_id

                threshold = saved_threshold

            data = {
                "job_id": job_id,
                "threshold": threshold,
                "data": {
                    "jobs": jobs,
                    "thresholds": [1, 2, 3, 4, 5, 6],
                },
            }

            return json.dumps(data)

        except Exception as e:
            print("Error loading config:", e)

            data = {
                "job_id": "",
                "threshold": default_threshold,
                "data": {
                    "jobs": [],
                    "thresholds": [1, 2, 3, 4, 5, 6],
                },
            }

            return json.dumps(data)
        
    def init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS REPORT (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_id INTEGER,
                machine_no TEXT NOT NULL,
                job_id TEXT NOT NULL,
                result TEXT NOT NULL,
                total_strips INTEGER,
                bad_strips INTEGER,
                bad_strip_number TEXT,
                bad_image_path TEXT,
                created_time TEXT,
                updated_time TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (shift_id) REFERENCES SHIFT(id)
            )
            """)

            conn.commit()
            conn.close()

            print("✅ Database + Tables initialized")

        except Exception as e:
            print("❌ DB Init Error:", e)
            #Creates jobs.db if not exists
            # Creates jobs table if not exists
            # Safe to run every time app starts ✅

    def insert_report(self):
        print("🚀 insert_report called")
        try:
            job_id, threshold = self.get_job_from_config()
            print("Fetched from config → Job ID:", job_id, "| Threshold:", threshold)

            if not job_id:
                print("⚠️ No job_id found in config")
                return

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO REPORT (
                    shift_id,
                    machine_no,
                    job_id,
                    result,
                    total_strips,
                    bad_strips,
                    bad_strip_number,
                    bad_image_path,
                    created_time
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                1,                          # shift_id (dummy for now)
                "M1",                       # machine_no
                job_id,                     # ✅ from JSON
                "GOOD",                     # result
                8,                          # total_strips
                1,                          # bad_strips
                "2,5,10",                   # bad_strip_number
                "path/to/image.jpg",        # bad_image_path
                datetime.now().isoformat()  # created_time
            ))

            conn.commit()
            conn.close()
            print("🚀 insert_report called")
            print(f"✅ Inserted job_id '{job_id}' into DB")

        except Exception as e:
            print("❌ Insert Error:", e)

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

    @pyqtSlot(str, result=str)
    def get_counts(self, job_id):
        if job_id == "Product A":
            inspected = 0
            good = 0
            defective = 0
        elif job_id == "Product B":
            inspected = 0
            good = 0
            defective = 0
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
                "count": data.get("count", ""),
                "yarn": data.get("yarn", ""),
                "color": data.get("color", ""),
                "savedAt": datetime.now().isoformat(timespec="seconds"),
            }

            with open(TRAINING_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2)

            print("TRAINING_IMAGES_DIR =", TRAINING_IMAGES_DIR)

            folder_name = f"{record['count']}_{record['yarn']}_{record['color']}"
            folder_name = folder_name.replace(" ", "_")
            print("folder_name =", folder_name)

            job_folder = self.get_training_job_folder(folder_name, clear_existing=True)
            print("job_folder =", job_folder)

            # Mark training as active
            self.training_running = True
            self.training_folder_name = folder_name

            print(f"✅ Training session started: {folder_name}")

        except Exception as e:
            print(f"❌ saveTrainingSession error: {e}")


    @pyqtSlot(result=str)
    def stopTrainingSession(self):
        try:
            if not self.training_folder_name:
                return json.dumps({
                    "ok": False,
                    "message": "No active training folder found"
                })

            # Stop image saving
            self.training_running = False

            folder_name = self.training_folder_name
            training_folder = TRAINING_IMAGES_DIR / folder_name

            print("🛑 Training stopped for folder:", folder_name)
            print("📂 Training images folder:", training_folder)

            trainer = StripColorTraining()
            result = trainer.train(str(training_folder), folder_name)

            # Clear current training state
            self.training_folder_name = ""
            self.last_training_save_time = 0

            return json.dumps(result)

        except Exception as e:
            print("❌ stopTrainingSession error:", e)
            return json.dumps({
                "ok": False,
                "message": str(e)
            })
            


       
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