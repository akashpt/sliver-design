import cv2
import base64
import json
import os
import sqlite3
import random
import shutil
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QStandardPaths, QDir
from PyQt5.QtWidgets import QApplication  # Only if needed elsewhere
from classes.mindvision import MindVisionCamera
from path import *
from classes.training import StripColorTraining
from classes.prediction import StripColorPrediction
from classes.modbus_relay_code import *
# from classes.report import ReportManager

class Bridge(QObject):

    frame_signal = pyqtSignal(str)
    counts_signal = pyqtSignal(str)
    storage_signal = pyqtSignal(str)  
    defect_signal = pyqtSignal(str)   

    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

        #database
        self.db_path = str(DB_FILE)   # set DB path
        # self.init_db()    
        print("DB Path:", self.db_path)            # create table automatically

        # Camera
        self.camera = None  
        self.cap = None
        self.use_mindvision = False
        self.camera_open = False
        self.current_frame = None
        self.defect_active = False
        self.training_running = False
        self.training_folder_name = ""
        self.training_save_interval = 1000   # milliseconds
        self.last_training_save_time = 0
        self.get_system_storage()

        self.test_image_path = None
        self.test_frame = None

        # Frame timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.grab_frame)
        self.process = None

        self.count_time = QTimer()
        self.count_time.timeout.connect(self.count_show)
        self.count_time.start(1000)
        self.pdf_mail_timer = QTimer()
        self.pdf_mail_timer.timeout.connect(self.send_hourly_pdf_mail)
        # self.pdf_mail_timer.start(60 * 60 * 1000)  # 1 hour
        self.pdf_mail_timer.start(10000)  # 10 seconds (testing)
        self.inspected = 0
        self.good = 0
        self.bad = 0

        # Config file path
        # config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        # QDir().mkpath(config_dir)
        # self.config_path = os.path.join(config_dir, "userConfig.json")        
        self.config_path= str(USER_CONFIG_FILE)

        # For observation purpose - ignored frames count
        self.session_start_time = ""
        self.session_end_time = ""
        self.ignored_count = 0

        # Prediction Class
        self.detector = StripColorPrediction()

        self.model_key, self.threshold = self.get_job_from_config()

        if self.threshold:
            self.detector.color_threshold = float(self.threshold)
            self.get_system_storage()

        # For testing
        self.test_image_path = r"/home/texa_developer/Divya Data/i_sliver-design/strips.bmp"
        self.test_frame = cv2.imread(self.test_image_path)

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

            self.inspected = 0
            self.good = 0
            self.bad = 0

            self.counts_signal.emit(json.dumps({
                "inspected": 0,
                "good": 0,
                "bad": 0,
                "status": "reset"
            }))

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

        # if clear_existing:
        #     for file_path in job_folder.iterdir():
        #         if file_path.is_file():
        #             try:
        #                 file_path.unlink()
        #                 print(f"🗑 Deleted old training image: {file_path.name}")
        #             except Exception as e:
        #                 print(f"❌ Could not delete {file_path.name}: {e}")

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

            self.get_system_storage()

            print(f"✅ Training image saved: {file_path}")
            return str(file_path)

        except Exception as e:
            print(f"❌ save_training_image error: {e}")
            return ""
        
   
    @pyqtSlot(str,result=str)
    def startCamera(self,process):
        self.process = process

        # For obseravtion - ignored frame details
        self.session_start_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        self.ignored_count = 0

        if self.camera_open:
            print("⚠️ Camera already running")
            return "Camera Already Running"

        print("🔥 Starting camera...")
        # turn_on_whitelight()
        turn_off_redlight()
        turn_on_greenlight()
        print("🟢 Green light ON, 🔴 Red light OFF - camera started")

        job_id, _ = self.get_job_from_config()
        if job_id:
            self.load_db_counts_for_job(job_id)

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

        # # Grab one frame immediately so current_frame is ready
        # self.grab_frame()
        if process == "live_stream":
            self.timer.start(35)
        else:
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
        # all lights off when camera stops
        turn_off_greenlight()
        # turn_off_redlight()
        # turn_off_whitelight()
        # self.insert_report()

        self.session_end_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        if self.process == "prediction":
            self.save_session_txt()
            print("✅ Prediction session file created")

    def save_session_txt(self):
        try:
            job_id, threshold = self.get_job_from_config()

            file_name = datetime.now().strftime("session_%Y%m%d_%H%M%S.txt")
            file_path = SESSION_LOG_DIR / file_name   # create path in path.py

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"job_id: {job_id}\n")
                f.write(f"threshold: {threshold}\n")
                f.write(f"lastSaved: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}\n")
                f.write(f"start time: {self.session_start_time}\n")
                f.write(f"end time: {self.session_end_time}\n")
                f.write(f"inspected: {self.inspected}\n")
                f.write(f"good: {self.good}\n")
                f.write(f"bad: {self.bad}\n")
                f.write(f"ignored frame count: {self.ignored_count}\n")

            print("✅ Session txt saved:", file_path)

        except Exception as e:
            print("❌ save_session_txt error:", e)

    def count_show(self):
        job_id, _ = self.get_job_from_config()

        if job_id:
            self.load_db_counts_for_job(job_id)
        else:
            self.inspected = 0
            self.good = 0
            self.bad = 0

        self.get_system_storage()

        counts_data = {
            "inspected": self.inspected,
            "good": self.good,
            "bad": self.bad,
            "status": "defect"
        }
        self.counts_signal.emit(json.dumps(counts_data))

    def grab_frame(self):
        try:
            frame = None

            # # For testing
            # if self.test_image_path:
            #     frame = cv2.imread(self.test_image_path)
            #     frame = self.test_frame.copy()

            #     if frame is None:
            #         print("Test image not found")
            #         return


            # # =========================
            # # MINDVISION CAMERA
            # # =========================
            if self.use_mindvision and self.camera:
                frame = self.camera.get_frame()

                if frame is None:
                    print("⚠️ MindVision lost → switching to webcam")
                    self.use_mindvision = False
                    self.cap = cv2.VideoCapture(0)
                    return


                # frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # # =========================
            # # WEBCAM
            # # =========================
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
            # =========================defect_path
            # SAVE CURRENT FRAME
            # =========================
            self.current_frame = frame.copy()

            if self.process == "training":
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
            processed_img = None
            if self.training_running and self.process == "training":
                status = "training"
            elif self.process == "live_stream":
                status = "live_stream"
            else:
                # status = self.run_detection(frame)
                # status, processed_img, raw_img = self.run_detection(frame)
                status, processed_img, raw_img, bad_count, bad_indices = self.run_detection(frame)
            
            total_strips = self.detector.expected_strip_count
            
            if status == "good":
                turn_on_greenlight()
                turn_off_redlight()
                print("🟢 GOOD: Green light ON, Red light OFF")

            if status == "strip missing":
                bad_strips = bad_count
                bad_strip_number = "missing"
                turn_off_greenlight()
                turn_on_redlight()
                print("⚠️ STRIP MISSING: Green light OFF, Red light ON")
                
            elif status == "defect":
                bad_strips = bad_count
                bad_strip_number = ",".join(map(str, bad_indices))
                turn_off_greenlight()
                turn_on_redlight()
                print(f"🔴 DEFECT: Green light OFF, Red light ON - Bad strip No: {bad_strip_number}")
                
            else:
                bad_strips = 0
                bad_strip_number = ""


            bad_image_path = None

            if status == "defect" or status == "strip missing":
                job_id, _ = self.get_job_from_config()

                if job_id:
                    job_folder = PREDICTION_IMAGES_DIR / job_id
                    job_folder.mkdir(parents=True, exist_ok=True)


                    # processed image folder
                    defect_folder = job_folder / "defect"
                    defect_folder.mkdir(parents=True, exist_ok=True)

                    # raw image folder
                    raw_folder = job_folder / "defect_raw"
                    raw_folder.mkdir(parents=True, exist_ok=True)

                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')

                    # processed image path
                    file_path = defect_folder / f"defect_{timestamp}.jpg"

                    # raw image path
                    raw_path = raw_folder / f"raw_{timestamp}.jpg"


                    # filename = f"defect_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
                    # file_path = job_folder / filename
                    # save_path = f"{job_id}/{filename}"
                    save_path = f"{job_id}/defect/{file_path.name}"



                    # saved = cv2.imwrite(str(file_path), self.current_frame)
                    saved = cv2.imwrite(str(file_path), processed_img if processed_img is not None else self.current_frame)
                    bad_image_path = save_path


                    if raw_img is not None:
                        cv2.imwrite(str(raw_path), raw_img)
                    else:
                        cv2.imwrite(str(raw_path), self.current_frame)


                    if saved:
                        from classes.send_mail import send_email_with_attachments
                        import threading

                        # ✅ ADD HERE
                        defect_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                        frame_no = self.inspected
                        material = job_id
                        training_color = "-"
                        defect_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                        frame_no = self.inspected
                        material = job_id
                        training_color = "-"

                        conn = sqlite3.connect(self.db_path)
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT machine_no
                            FROM REPORT
                            WHERE job_id = ?
                            ORDER BY id DESC
                            LIMIT 1
                        """, (job_id,))
                        row = cursor.fetchone()
                        conn.close()

                        if row and row[0]:
                            machine_no = row[0]
                        else:
                            machine_no = "M1"

                        try:
                            if os.path.exists(TRAINING_SETTINGS_FILE):
                                with open(TRAINING_SETTINGS_FILE, "r", encoding="utf-8") as f:
                                    training_data = json.load(f)
                                    training_color = training_data.get("color", "-")
                        except Exception as e:
                            print("❌ Error reading training settings for email:", e)

                        # EXISTING THREAD BELOW
                        threading.Thread(
                            target=send_email_with_attachments,
                            args=(str(file_path), machine_no, frame_no, material, training_color, defect_time),
                            daemon=True
                        ).start()
                        print(f"Saved: {file_path}")
                       
                        # defect_payload = {
                        #     "status": status,
                        #     "defect_type": status,
                        #     "image_path": str(file_path),
                        #     "time": defect_time
                        # }

                        # self.defect_signal.emit(json.dumps(defect_payload))
                        

                        # stop prediction after defect
                        

            # if self.process == "prediction":
                        if self.process == "prediction" and status != "ignored":
                            self.save_report_entry(
                                status,
                                bad_image_path,
                                total_strips,
                                bad_strips,
                                bad_strip_number
                            )

                        print("✅ DEFECT REPORT SAVED")
                        print("saved image path =", file_path)
                        print("db image path =", bad_image_path)
                        self.emit_defect_payload(status, file_path)
                        self.stopCamera()
                        return

            if self.process == "prediction" and status != "ignored":
                # self.save_report_entry(status, bad_image_path)
                    self.save_report_entry(
                        status,
                        bad_image_path,
                        total_strips,
                        bad_strips,
                        bad_strip_number
                    )
            # =========================
            # SEND TO UI
            # =========================
            # _, buffer = cv2.imencode(".jpg", frame)
            if status != "ignored":
                display_frame = processed_img if processed_img is not None else frame
                _, buffer = cv2.imencode(".jpg", display_frame)
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
        # self.inspected += 1

        # Get model + threshold
        model_key, threshold = self.get_job_from_config()

        if threshold:
            self.detector.color_threshold = float(threshold)

        # Prediction file function
        status, processed_img, raw_img, bad_count, bad_indices = self.detector.process_image(frame, model_key)

        # # Update counts
        # if status == "good":
        #     self.good += 1
        # elif status == "defect":
        #     self.bad += 1
        # else :
        #     self.bad +=1

        # Count only valid frames

        if status == "ignored":
            self.ignored_count += 1

        if status != "ignored":
            self.inspected += 1

        # Good / Bad counts
        if status == "good":
            self.good += 1

        elif status in ["defect", "strip missing"]:
            self.bad += 1


        # Replace frame with processed image 
        # if processed_img is not None:
        #     self.current_frame = processed_img

        return status,processed_img, raw_img, bad_count, bad_indices
    
    def emit_defect_payload(self, status, file_path):
        try:
            turn_off_greenlight()
            turn_on_redlight()
            print("🔴 Defect popup showing: Green OFF, Red ON")

            defect_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

            payload = {
                "status": status,
                "defect_type": status,
                "image_path": str(file_path),
                "time": defect_time
            }

            self.defect_signal.emit(json.dumps(payload))

        except Exception as e:
            print("❌ emit_defect_payload error:", e)

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
        default_threshold = ""

        try:
            jobs = self.get_model_job_ids()

            if not jobs:
                jobs = []

            job_id = ""
            threshold = default_threshold

            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

                saved_job_id = config.get("job_id", "")

                if saved_job_id in jobs:
                    job_id = saved_job_id

            if not job_id and jobs:
                job_id = jobs[0]

            # latest threshold from DB for selected job
            latest_db_threshold = self.get_latest_threshold_from_report(job_id)

            if latest_db_threshold:
                threshold = latest_db_threshold
            else:
                # fallback from config if DB value not found
                if os.path.exists(self.config_path):
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    threshold = str(config.get("threshold", default_threshold))

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

    def save_report_entry(self, result_status, bad_image_path="", total_strips=0,bad_strips=0,bad_strip_number=""):
        try:
            job_id, threshold = self.get_job_from_config()

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
                    threshold,
                    result,
                    total_strips,
                    bad_strips,
                    bad_strip_number,
                    bad_image_path
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                1,
                "M1",
                job_id,
                str(threshold) if threshold is not None else "",
                result_status,
                total_strips,
                bad_strips,
                bad_strip_number,
                bad_image_path,
            ))

            conn.commit()
            conn.close()

            self.get_system_storage()

            print(
                f"✅ Report row inserted: job_id={job_id}, threshold={threshold}, "
                f"status={result_status}, image={bad_image_path}"
            )

        except Exception as e:
            print("❌ save_report_entry error:", e)

    def get_latest_threshold_from_report(self, job_id):
        try:
            if not job_id:
                return ""

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT threshold
                FROM REPORT
                WHERE job_id = ?
                AND threshold IS NOT NULL
                AND TRIM(threshold) != ''
                ORDER BY id DESC
                LIMIT 1
            """, (job_id,))

            row = cursor.fetchone()
            conn.close()

            return str(row[0]) if row and row[0] is not None else ""

        except Exception as e:
            print("❌ get_latest_threshold_from_report error:", e)
            return ""


    @pyqtSlot(str, result=str)
    def get_threshold_by_job(self, job_id):
        try:
            threshold = self.get_latest_threshold_from_report(job_id)

            return json.dumps({
                "ok": True,
                "job_id": job_id,
                "threshold": threshold
            })

        except Exception as e:
            print("❌ get_threshold_by_job error:", e)
            return json.dumps({
                "ok": False,
                "job_id": job_id,
                "threshold": "",
                "message": str(e)
            })
    

    @pyqtSlot(result=str)
    def get_defect_images(self):
        try:
            job_id, _ = self.get_job_from_config()

            if not job_id:
                return json.dumps({"images": []})
            

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT bad_image_path
                FROM REPORT
                WHERE job_id = ?
                AND result != 'good'
                AND bad_image_path IS NOT NULL
                AND bad_image_path != ''
                ORDER BY datetime(created_time) DESC
                LIMIT 10
            """, (job_id,))

            rows = cursor.fetchall()
            conn.close()

            images = []

            for row in rows:
                path = row[0]
                full_path = str(PREDICTION_IMAGES_DIR / path)  
                images.append(full_path)

            return json.dumps({"images": images})
        
        except Exception as e:
            print("❌ get_defect_images error:", e)
            return json.dumps({"images": []})

    @pyqtSlot(str, result=str)
    def get_counts(self, job_id):
        try:
            # print("🔥 get_counts CALLED")
            # print("job_id from UI =", job_id)
            # print("db_path =", self.db_path)

            conn = sqlite3.connect(self.db_path)
            print("✅ DB connected")

            cursor = conn.cursor()
            print("✅ cursor created")

            print("✅ before execute")
            cursor.execute("""
                SELECT 
                    COUNT(*) AS inspected,
                    SUM(CASE WHEN LOWER(result) = 'good' THEN 1 ELSE 0 END) AS good,
                    SUM(CASE WHEN LOWER(result) IN ('bad', 'defect', 'strip missing') THEN 1 ELSE 0 END) AS bad
                FROM REPORT
                WHERE job_id = ?
                AND date(created_time) = date('now', 'localtime')
            """, (job_id,))
            print("✅ after execute")

            row = cursor.fetchone()
            # print("✅ after fetchone")
            # print("DB row =", row)

            # conn.close()
            # print("✅ DB closed")

            inspected = row[0] if row and row[0] is not None else 0
            good = row[1] if row and row[1] is not None else 0
            bad = row[2] if row and row[2] is not None else 0

            data = {
                "job_id": job_id,
                "inspected": inspected,
                "good": good,
                "defective": bad
            }

            print("Returning counts =", data)
            return json.dumps(data)

        except Exception as e:
            print("❌ get_counts error:", e)
            return json.dumps({
                "job_id": job_id,
                "inspected": 0,
                "good": 0,
                "defective": 0
            })

    def load_db_counts_for_job(self, job_id):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT 
                    COUNT(*) AS inspected,
                    SUM(CASE WHEN LOWER(result) = 'good' THEN 1 ELSE 0 END) AS good,
                    SUM(CASE WHEN LOWER(result) in ('defect','strip missing') THEN 1 ELSE 0 END) AS bad
                FROM REPORT
                WHERE job_id = ?
                AND date(created_time) = date('now', 'localtime')
            """, (job_id,))

            row = cursor.fetchone()
            conn.close()

            self.inspected = row[0] if row and row[0] is not None else 0
            self.good = row[1] if row and row[1] is not None else 0
            self.bad = row[2] if row and row[2] is not None else 0

            # print("✅ DB counts loaded into live counters")
            # print("self.inspected =", self.inspected)
            # print("self.good =", self.good)
            # print("self.bad =", self.bad)

        except Exception as e:
            print("❌ load_db_counts_for_job error:", e)
            self.inspected = 0
            self.good = 0
            self.bad = 0

    @pyqtSlot(str, result=str)
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

            job_folder = self.get_training_job_folder(folder_name)
            print("job_folder =", job_folder)

            # Mark training as active
            self.training_running = True
            self.training_folder_name = folder_name

            print(f"✅ Training session started: {folder_name}")

            return json.dumps({
                "ok": True,
                "job_id": folder_name,
                "message": "Training session started"
            })

        except Exception as e:
            print(f"❌ saveTrainingSession error: {e}")
            return json.dumps({
                "ok": False,
                "job_id": "",
                "message": str(e)
            })


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

            self.get_system_storage()

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
            
    
    # @pyqtSlot(result=str)
    # def get_report_summary(self):
    #     try:
    #         manager = ReportManager()
    #         return manager.get_summary_json()
    #     except Exception as e:
    #         print("❌ get_report_summary bridge error:", e)
    #         return json.dumps({
    #             "ok": False,
    #             "total": 0,
    #             "good": 0,
    #             "defective": 0,
    #             "message": str(e)
    #         })

    # ====================== REPORT SUMMARY Start======================
    @pyqtSlot(str, result=str)
    def get_counts_by_range(self, period):
        """
        period: 'day' | 'week' | 'month'
        Returns cards + donut/bar + line chart data
        """
        try:
            date_filter_map = {
                "day": "date(created_time) = date('now', 'localtime')",
                "week": "date(created_time) >= date('now', '-6 days', 'localtime')",
                "month": "date(created_time) >= date('now', 'start of month', 'localtime')",
            }

            if period not in date_filter_map:
                return json.dumps({
                    "ok": False,
                    "message": f"Unknown period: {period}"
                })

            date_condition = date_filter_map[period]

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # cards
            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS inspected,
                    SUM(CASE WHEN LOWER(COALESCE(result, '')) = 'good' THEN 1 ELSE 0 END) AS good,
                    SUM(CASE WHEN LOWER(COALESCE(result, '')) IN ('defect', 'bad', 'strip missing') THEN 1 ELSE 0 END) AS bad
                FROM REPORT
                WHERE {date_condition}
                """
            )
            row = cursor.fetchone()

            inspected = row[0] if row and row[0] is not None else 0
            good = row[1] if row and row[1] is not None else 0
            bad = row[2] if row and row[2] is not None else 0
            rate = round((bad / inspected) * 100, 1) if inspected > 0 else 0.0

            # bar chart
            breakdown_labels = ["Good", "Defective"]
            breakdown_values = [good, bad]

            # line chart
            if period == "day":
                hourly_labels = [f"{h:02d}" for h in range(24)]
                hourly_values = [0] * 24

                cursor.execute(
                    f"""
                    SELECT
                        strftime('%H', created_time) AS hour_label,
                        COUNT(*) AS total
                    FROM REPORT
                    WHERE {date_condition}
                    AND LOWER(COALESCE(result, '')) IN ('defect', 'bad', 'strip missing')
                    GROUP BY strftime('%H', created_time)
                    ORDER BY hour_label
                    """
                )

                for hour_label, total in cursor.fetchall():
                    if hour_label is not None:
                        hourly_values[int(hour_label)] = total

            elif period == "week":
                hourly_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                hourly_values = [0] * 7

                cursor.execute(
                    f"""
                    SELECT
                        strftime('%w', created_time) AS day_no,
                        COUNT(*) AS total
                    FROM REPORT
                    WHERE {date_condition}
                    AND LOWER(COALESCE(result, '')) IN ('defect', 'bad', 'strip missing')
                    GROUP BY strftime('%w', created_time)
                    ORDER BY day_no
                    """
                )

                sqlite_to_idx = {
                    "1": 0,  # Mon
                    "2": 1,
                    "3": 2,
                    "4": 3,
                    "5": 4,
                    "6": 5,
                    "0": 6,  # Sun
                }

                for day_no, total in cursor.fetchall():
                    if day_no in sqlite_to_idx:
                        hourly_values[sqlite_to_idx[day_no]] = total

            else:  # month
                hourly_labels = [str(i) for i in range(1, 32)]
                hourly_values = [0] * 31

                cursor.execute(
                    f"""
                    SELECT
                        strftime('%d', created_time) AS day_label,
                        COUNT(*) AS total
                    FROM REPORT
                    WHERE {date_condition}
                    AND LOWER(COALESCE(result, '')) IN ('defect', 'bad', 'strip missing')
                    GROUP BY strftime('%d', created_time)
                    ORDER BY day_label
                    """
                )

                for day_label, total in cursor.fetchall():
                    if day_label is not None:
                        idx = int(day_label) - 1
                        if 0 <= idx < 31:
                            hourly_values[idx] = total

            conn.close()

            data = {
                "ok": True,
                "period": period,
                "inspected": inspected,
                "good": good,
                "defective": bad,
                "rate": rate,
                "breakdown": {
                    "labels": breakdown_labels,
                    "values": breakdown_values
                },
                "line_chart": {
                    "labels": hourly_labels,
                    "values": hourly_values
                }
            }

            print(f"✅ get_counts_by_range [{period}] →", data)
            return json.dumps(data)

        except Exception as e:
            print("❌ get_counts_by_range error:", e)
            return json.dumps({
                "ok": False,
                "period": period,
                "inspected": 0,
                "good": 0,
                "defective": 0,
                "rate": 0.0,
                "breakdown": {
                    "labels": ["Good", "Defective"],
                    "values": [0, 0]
                },
                "line_chart": {
                    "labels": [],
                    "values": []
                },
                "message": str(e),
            })

    def load_email_template(self):
        try:
            with open(EMAIL_PAGE, "r", encoding="utf-8") as file:
                return file.read()
        except Exception as e:
            print("❌ load_email_template error:", e)
            return ""

    def to_gb(self,value):
        return round(value / (1024 ** 3), 2)
    
    # @pyqtSlot(result=str)
    def get_system_storage(self):
        try:
            total, used, free = shutil.disk_usage("/")
            total_gp = self.to_gb(total)
            used_gp = self.to_gb(used)
            free_gp = self.to_gb(free)
            hidden_gp = total_gp -(used_gp + free_gp)
            data = {
                "total_gb": total_gp,
                "used_gb": used_gp + hidden_gp,
                "free_gb": free_gp,
                "total_gb": total_gp,
                "used_gb": used_gp + hidden_gp,
                "free_gb": free_gp,
                "used_percent": round((used ) / total * 100, 1) if total > 0 else 0,
                "free_percent": round((free / total) * 100, 1) if total > 0 else 0,
                "updated_at": datetime.now().isoformat()
            }

            with open(STORAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            payload = json.dumps({
                "ok": True,
                "data": data
            })

            self.storage_signal.emit(payload)

            # print(f"✅ Storage saved to: {STORAGE_FILE}")

            return payload

        except Exception as e:
            print("❌ get_system_storage error:", e)
            return json.dumps({
                "ok": False,
                "message": str(e)
            })
    # ====================== REPORT SUMMARY End ======================

# invoice viewer slot 
    # @pyqtSlot()
    # def openInvoiceViewer(self):
    #     try:
    #         from classes.invoice_pdf import InvoicePDFGenerator
    #         from classes.invoice_viewer import InvoiceViewer

    #         ok = InvoicePDFGenerator().generate_pdf()

    #         if not ok:
    #             print("❌ Invoice PDF generation failed")
    #             return

    #         viewer = InvoiceViewer()
    #         viewer.exec_()

    #     except Exception as e:
    #         print("❌ openInvoiceViewer error:", e)
    @pyqtSlot()
    def openInvoiceViewer(self):
        try:
            from classes.invoice_pdf import InvoicePDFGenerator

            self.pdf_generator = InvoicePDFGenerator()

            self.pdf_generator.generate_pdf(
                parent=self.app_ref,
                finished_callback=self._open_invoice_after_pdf
            )

        except Exception as e:
            print("❌ openInvoiceViewer error:", e)


    def _open_invoice_after_pdf(self, ok):
        try:
            if not ok:
                print("❌ Invoice PDF generation failed")
                return

            from classes.invoice_viewer import InvoiceViewer

            viewer = InvoiceViewer()
            viewer.exec_()

        except Exception as e:
            print("❌ _open_invoice_after_pdf error:", e)
    
    def send_hourly_pdf_mail(self):
        try:
            from classes.invoice_pdf import InvoicePDFGenerator

            print("🔥 Hourly PDF generation started")

            self.hourly_pdf_generator = InvoicePDFGenerator()
            self.hourly_pdf_generator.generate_pdf(
                parent=self.app_ref,
                finished_callback=self._send_pdf_after_generate
            )

        except Exception as e:
            print("❌ send_hourly_pdf_mail error:", e)


    def _send_pdf_after_generate(self, ok):
        try:
            if not ok:
                print("❌ Hourly PDF generation failed. Mail not sent.")
                return

            from classes.send_mail import send_last_generated_pdf
            import threading

            threading.Thread(
                target=send_last_generated_pdf,
                daemon=True
            ).start()

            print("📧 Fresh generated PDF mail triggered")

        except Exception as e:
            print("❌ _send_pdf_after_generate error:", e)
                
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

    #=====================================================================
    # 👉 467.89 GB = 100% (always)
    # 👉 94.9% is only used + free (incomplete data)
    # 👉 Remaining ~5.1% (23.84 GB) is:

    # system reserved
    # filesystem overhead
    # hidden usage