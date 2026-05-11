import cv2
import base64
import json
import os
import sqlite3
import random
import shutil
from datetime import datetime, timedelta, time as datetime_time
from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer, QStandardPaths, QDir
from PyQt5.QtWidgets import QApplication  # Only if needed elsewhere
from classes.mindvision import MindVisionCamera
from path import DB_FILE,SETTINGS_FILE, TRAINING_IMAGES_DIR, SESSION_LOG_DIR, PREDICTION_IMAGES_DIR, TRAINING_SETTINGS_FILE, MODELS_DIR, EMAIL_PAGE, STORAGE_FILE, INDEX_PAGE, TRAINING_PAGE, SETTINGS_PAGE
from classes.training import StripColorTraining
from classes.prediction import StripColorPrediction
from classes.modbus_relay_code import *
from classes.invoice_pdf import InvoicePDFGenerator
from classes.database import create_new_shift_version
# from datetime import datetime, time
# from classes.report import ReportManager

class Bridge(QObject):

    frame_signal = pyqtSignal(str)
    counts_signal = pyqtSignal(str)
    storage_signal = pyqtSignal(str)  
    defect_signal = pyqtSignal(str)   
    signal_status_signal = pyqtSignal(str)

    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

        self.db_path = str(DB_FILE)   # set DB path
        self.config_path= str(SETTINGS_FILE)
        
        # Camera
        self.camera = None  
        self.cap = None
        self.use_mindvision = False
        self.mindvision_fail_count = 0
        self.camera_open = False
        self.current_frame = None
        self.defect_active = False
        self.training_running = False
        self.training_folder_name = ""
        self.training_save_interval = 1000   # milliseconds
        self.last_training_save_time = 0
        self.get_system_storage()

        self.test_frame = None

        # Frame timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.grab_frame)
        # Prediction interval from settings.json
        self.pr_time = self.get_prediction_interval_seconds()
        self.last_prediction_interval_seconds = self.pr_time
        # self.pr_time = 1  # seconds
        self.process = None
        self.prediction_live = False
        self.reset_click = False

        self.count_time = QTimer()
        self.count_time.timeout.connect(self.count_show)
        self.count_time.start(1000)
        self.pdf_mail_timer = QTimer()
        self.pdf_mail_timer.timeout.connect(self.send_shift_pdf_mail)
        # self.pdf_mail_timer.start(60 * 60 * 1000)  # 1 hour
        self.pdf_mail_timer.start(60 * 1000)  # 1 minute testing
        # self.pdf_mail_timer.start(10000)  # 10 seconds (testing)
        self.current_shift_name = ""
        self.last_sent_shift_key = ""
        self.inspected = 0
        self.good = 0
        self.bad = 0
        self.current_signal_status = {
            "signal1": True,
            "signal2": True,
            "signal3": False,
            "signal4": False,
            "signal5": False,
            "signal6": False,
            "signal7": False,
        }
        self.save_signal_status_to_settings(self.current_signal_status)

        # Config file path
        # config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        # QDir().mkpath(config_dir)
        # self.config_path = os.path.join(config_dir, "userConfig.json")        
        self.config_path= str(SETTINGS_FILE)

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
        
        


    # ====================== SAVE USER CONFIG ======================

    @pyqtSlot(str, str, result=str)
    def saveUserConfig(self, job_id, threshold):
        # print("🔥 saveUserConfig CALLED") 
        try:
            config = {}

            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

            config["job_id"] = job_id
            config["threshold"] = threshold
            config["lastSaved"] = datetime.now().isoformat()

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2) #w py dict into json

            print("✅ Process Confirmed")
            print("Job:", job_id)
            print("Threshold:", threshold)
           

            return json.dumps({
                "status": "success",
                "message": "Process Confirmed",
                "data": config
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
            config = {}

            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

            config["job_id"] = ""
            config["threshold"] = ""
            config["lastSaved"] = datetime.now().isoformat()

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)

            self.inspected = 0
            self.good = 0
            self.bad = 0

            self.counts_signal.emit(json.dumps({
                "inspected": 0,
                "good": 0,
                "bad": 0,
                "status": "reset"
            }))
            
            self.emit_signal_status()
            
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

    #------------retrain methods-------------------

    IMAGE_EXTENSIONS = (".bmp", ".jpg", ".jpeg", ".png", ".tif", ".tiff")

    def safe_job_name(self, job_id):
        job_id = (job_id or "").strip()
        return "".join(
            ch if ch.isalnum() or ch in (" ", "_", "-") else "_"
            for ch in job_id
        ).strip()

    @pyqtSlot(result=str)
    def getTrainedModelList(self):
        try:
            jobs = self.get_model_job_ids()

            return json.dumps({
                "ok": True,
                "models": jobs
            })

        except Exception as e:
            return json.dumps({
                "ok": False,
                "models": [],
                "message": str(e)
            })

    @pyqtSlot(str, result=str)
    def retrainSelectedModel(self, job_id):
        try:
            job_id = self.safe_job_name(job_id)

            if not job_id:
                return json.dumps({
                    "ok": False,
                    "message": "Please select model"
                })

            training_folder = TRAINING_IMAGES_DIR / job_id
            model_folder = MODELS_DIR / job_id

            if not training_folder.exists():
                return json.dumps({
                    "ok": False,
                    "message": "Training images folder not found"
                })

            images = [
                p for p in training_folder.iterdir()
                if p.is_file() and p.suffix.lower() in self.IMAGE_EXTENSIONS
            ]

            if not images:
                return json.dumps({
                    "ok": False,
                    "message": "No training images found for this model"
                })

            backup_folder = None

            if model_folder.exists():
                backup_folder = MODELS_DIR / f"{job_id}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.move(str(model_folder), str(backup_folder))

            trainer = StripColorTraining()
            result = trainer.train(str(training_folder), job_id)

            if result.get("ok"):
                if backup_folder and backup_folder.exists():
                    shutil.rmtree(str(backup_folder), ignore_errors=True)

                self.get_system_storage()

                return json.dumps({
                    "ok": True,
                    "message": "Model retrained successfully",
                    "job_id": job_id,
                    "image_count": len(images)
                })

            if backup_folder and backup_folder.exists():
                if model_folder.exists():
                    shutil.rmtree(str(model_folder), ignore_errors=True)
                shutil.move(str(backup_folder), str(model_folder))

            return json.dumps({
                "ok": False,
                "message": result.get("message", "Retraining failed. Old model restored.")
            })

        except Exception as e:
            return json.dumps({
                "ok": False,
                "message": str(e)
            })
    #----------------------------------------------------------
    
    def get_saved_exposure(self):
        exposure = 30000

        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    exposure = int(config.get("exposure", 30000))
        except Exception as e:
            print("⚠️ Exposure config read error:", e)
            exposure = 30000

        return exposure


    def apply_webcam_exposure(self, exposure):
        try:
            import subprocess

            # 🔥 Convert UI exposure (0–10000) → webcam range (10–625)
            cam_exp = max(10, min(625, int(exposure / 20)))

            # Step 1: Set manual mode
            subprocess.run(
                ["v4l2-ctl", "-d", "/dev/video0", "--set-ctrl=auto_exposure=1"],
                check=False
            )

            # Step 2: Set exposure
            subprocess.run(
                ["v4l2-ctl", "-d", "/dev/video0", f"--set-ctrl=exposure_time_absolute={cam_exp}"],
                check=False
            )

            print("📷 Webcam exposure applied via v4l2:")
            print("UI exposure =", exposure)
            print("Camera exposure =", cam_exp)

        except Exception as e:
            print("❌ apply_webcam_exposure error:", e)

    def get_prediction_interval_seconds(self):
        try:
            default_seconds = 1

            if not os.path.exists(self.config_path):
                return default_seconds

            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            seconds = int(config.get("prediction_interval_seconds", default_seconds))

            if seconds < 1:
                seconds = 1

            return seconds

        except Exception as e:
            print("❌ get_prediction_interval_seconds error:", e)
            return 1


    # def sync_prediction_interval_from_settings(self):
    #     try:
    #         new_seconds = self.get_prediction_interval_seconds()

    #         if new_seconds != self.last_prediction_interval_seconds:
    #             self.pr_time = new_seconds
    #             self.last_prediction_interval_seconds = new_seconds

    #             print(f"⏱ Prediction interval changed to {new_seconds} seconds")

    #             if self.camera_open and self.process == "prediction":
    #                 self.timer.start(new_seconds * 1000)
    #                 print(f"✅ Running prediction timer updated: {new_seconds} seconds")

    #     except Exception as e:
    #         print("❌ sync_prediction_interval_from_settings error:", e)


    def savePredictionTiming(self, value, unit):
        try:
            value = int(value)
            unit = str(unit).strip().lower()

            if value <= 0:
                return json.dumps({
                    "ok": False,
                    "message": "Prediction timing must be greater than 0"
                })

            if unit in ["minute", "minutes", "min"]:
                seconds = value * 60
                unit = "minutes"
            else:
                seconds = value
                unit = "seconds"

            config = {}

            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

            config["prediction_interval_value"] = value
            config["prediction_interval_unit"] = unit
            config["prediction_interval_seconds"] = seconds
            config["lastSaved"] = datetime.now().isoformat()

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)

            self.pr_time = seconds
            self.last_prediction_interval_seconds = seconds

            if self.camera_open and self.process == "prediction":
                self.timer.start(seconds * 1000)
                print(f"✅ Prediction timer updated immediately: {seconds} seconds")

            return json.dumps({
                "ok": True,
                "message": f"Prediction timing saved: {value} {unit}",
                "seconds": seconds
            })

        except Exception as e:
            return json.dumps({
                "ok": False,
                "message": str(e)
            })

    @pyqtSlot(str, result=str)
    def appendTraining(self, image_path):
        try:
            job_id, _ = self.get_job_from_config()

            if not job_id:
                return json.dumps({
                    "ok": False,
                    "message": "No job id selected"
                })

            if not image_path or not os.path.exists(image_path):
                return json.dumps({
                    "ok": False,
                    "message": "Selected image not found"
                })

            img = cv2.imread(image_path)

            if img is None:
                return json.dumps({
                    "ok": False,
                    "message": "Cannot read selected image"
                })


            predictor = StripColorPrediction()

            strips = predictor.detect_horizontal_strips(img)

            found_strip_count = len(strips)
            expected_strip_count = predictor.expected_strip_count

            if found_strip_count != expected_strip_count:

                message = (
                    f"Expected strip = {expected_strip_count}, "
                    f"but it has ({found_strip_count}), cannot be append"
                )

                print("❌", message)

                return json.dumps({
                    "ok": False,
                    "message": message
                })


            # Save into training folder
            saved_path = self.save_training_image(img, job_id)

            if not saved_path:
                return json.dumps({
                    "ok": False,
                    "message": "Failed to append image"
                })

            print("✅  ed image:", saved_path)

            # Retrain
            training_folder = self.get_training_job_folder(job_id)

            trainer = StripColorTraining()
            result = trainer.train(str(training_folder), job_id)

            if result.get("ok"):
                return json.dumps({
                    "ok": True,
                    "message": "Append completed",
                    "job_id": job_id,
                    "image_path": saved_path
                })

            return json.dumps({
                "ok": False,
                "message": result.get("message", "Training failed")
            })

        except Exception as e:
            print("❌ appendTraining error:", e)

            return json.dumps({
                "ok": False,
                "message": str(e)
            })
   
    @pyqtSlot(str,result=str)
    def startCamera(self,process):
        self.prediction_live = True
        self.process = process
        if not machine_status():
            return "Machine OFF"

        # For obseravtion - ignored frame details
        self.session_start_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        self.ignored_count = 0

        if self.camera_open:
            print("⚠️ Camera already running")
            return "Camera Already Running"

        print("🔥 Starting camera...")
        turn_on_whitelight()
        # turn_off_redlight()
        # turn_on_greenlight()
        print("🟢 Green light ON, 🔴 Red light OFF - camera started")

        job_id, _ = self.get_job_from_config()
        if job_id:
            self.load_db_counts_for_job(job_id)

        try:
            # self.camera = MindVisionCamera()
            exposure = self.get_saved_exposure()
            self.camera = MindVisionCamera(exposure_us=exposure)
            print("📷 Camera starting with exposure:", exposure)

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

            # print("✅ Using Webcam")
            self.apply_webcam_exposure(exposure)            

        self.camera_open = True

        # ── Signal Status: camera started → signal1 ON ──
        self.emit_signal_status(signal1=True)
        if process == "live_stream":
            self.timer.start(35)
        else:
            # Continue live updates
            self.pr_time = self.get_prediction_interval_seconds()
            self.last_prediction_interval_seconds = self.pr_time
            # print(f"⏱ Prediction interval: {self.pr_time} seconds")
            self.timer.start(self.pr_time * 1000)

        return "OK"
    
    @pyqtSlot()
    def turn_off_warning(self):
        try:
            turn_off_redlight()
            turn_off_bluelight()
        except Exception as e:
            print("Turn off the warning :", e)
    
    @pyqtSlot()
    def camera_stop(self):
        try:
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
            turn_off_whitelight()

            # ── Signal Status: camera stopped → all signals OFF ──
            self.emit_signal_status()

            self.session_end_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            if self.process == "prediction":
                self.save_session_txt()
                print("✅ Prediction session file created")
        except Exception as e:
            print("Camera Connection -",e)
    

    @pyqtSlot()
    def stopCamera(self):
        try:
            print("checking...123")
            self.prediction_live = False
            self.camera_stop()
        except Exception as e:
            print("Camera Connection Error",e)
        

    def save_session_txt(self):
        try:
            job_id, threshold = self.get_job_from_config()

            today = datetime.now().strftime("%Y%m%d")
            safe_job_id = job_id.replace(" ", "_")
            file_name = f"{safe_job_id}_{today}.txt"
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
        # self.sync_prediction_interval_from_settings()
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
            "status": "defect",
            "prediction_run":False
        }
        reset = reset_button()

        if reset:
            break_off()
            counts_data['reset_close'] = True
            # self.reset_click = True
        else:
            counts_data['reset_close'] = False
        
        machine = machine_status()
        # print(self.prediction_live)
        if (machine) and self.prediction_live:
            counts_data['prediction_run'] = True
        
        # print(counts_data,machine)
        self.counts_signal.emit(json.dumps(counts_data))
            

    def grab_frame(self):
        try:
            frame = None

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
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)

            # frame = cv2.imread(r"/home/texa_developer/Divya Data/i_sliver-design/strips.jpeg")
            # frame = cv2.imread(r"D:\Texa\sliver\sliver-design\Sliver_Data\WhatsApp Image 2026-04-29 at 2.33.25 PM.jpeg")

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
                turn_off_bluelight()
                print("🟢 GOOD: Green light ON, Red light OFF")

            if status == "strip missing":
                bad_strips = bad_count
                bad_strip_number = "missing"
                turn_off_greenlight()
                turn_on_bluelight()
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
                    raw_path = raw_folder / f"raw_{timestamp}.bmp"


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
                        # from classes.send_mail import send_email_with_attachments
                        import threading

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
                        # threading.Thread(
                        #     target=send_email_with_attachments,
                        #     args=(str(file_path), machine_no, frame_no, material, training_color, defect_time),
                        #     daemon=True
                        # ).start()
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

                        # print("✅ DEFECT REPORT SAVED")
                        # print("saved image path =", file_path)
                        # print("db image path =", bad_image_path)
                        self.emit_defect_payload(status, file_path, raw_path)
                        self.camera_stop()
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
            break_on()

        # Replace frame with processed image 
        # if processed_img is not None:
        #     self.current_frame = processed_img
        
        return status,processed_img, raw_img, bad_count, bad_indices
    
    def emit_defect_payload(self, status, file_path, raw_path):
        try:
            defect_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

            payload = {
                "status": status,
                "defect_type": status,
                "image_path": str(file_path),   # popup preview
                "raw_path": str(raw_path),      # append source
                "time": defect_time
            }

            self.defect_signal.emit(json.dumps(payload))

            # ── Signal Status: defect → signal6 ON, signal4 OFF, signal1 OFF
            #    signal3 only if strip missing
            is_missing = (status == "strip missing")
            self.emit_signal_status(
                signal1=False,
                signal6=True,
                signal4=False,
                signal3=is_missing,
            )

        except Exception as e:
            print("❌ emit_defect_payload error:", e)

    def emit_signal_status(self, **kwargs):
        """
        Emit the current ON/OFF state for all 7 signals to the JS left card.
        Only the keys passed will be True; everything else defaults to False.

        Usage examples:
            self.emit_signal_status(signal1=True, signal4=True)
            self.emit_signal_status()   # all OFF
        """
        payload = {
            "signal1": False,
            "signal2": False,
            "signal3": False,
            "signal4": False,
            "signal5": False,
            "signal6": False,
            "signal7": False,
        }
        payload.update(kwargs)
        self.current_signal_status = payload
        self.save_signal_status_to_settings(payload)
        self.signal_status_signal.emit(json.dumps(payload))

    def save_signal_status_to_settings(self, payload):
        try:
            config = {}
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

            signal_status = {
                "signal1": bool(payload.get("signal1", False)),
                "signal2": bool(payload.get("signal2", False)),
                "signal3": bool(payload.get("signal3", False)),
                "signal4": bool(payload.get("signal4", False)),
                "signal5": bool(payload.get("signal5", False)),
                "signal6": bool(payload.get("signal6", False)),
                "signal7": bool(payload.get("signal7", False)),
            }

            has_legacy_status = (
                "signal_status" in config or
                "signal_status_lastSaved" in config
            )
            if config.get("Signal Status") == signal_status and not has_legacy_status:
                return

            config.pop("signal_status", None)
            config.pop("signal_status_lastSaved", None)
            config["Signal Status"] = signal_status
            config["Signal Status Last Saved"] = datetime.now().isoformat()

            Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

        except Exception as e:
            print("❌ save_signal_status_to_settings error:", e)

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

            # if not job_id and jobs:
            #     job_id = jobs[0]

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

    @pyqtSlot(str, str, str, result=str)
    def saveShift(self, shift_name, start_time, end_time):
        try:
            # print("🔥 saveShift called")
            # print("shift_name =", shift_name)
            # print("start_time =", start_time)
            # print("end_time   =", end_time)

            result = create_new_shift_version(
                shift_name,
                start_time,
                end_time
            )

            print("✅ saveShift result =", result)

            return json.dumps(result)

        except Exception as e:
            print("❌ saveShift error =", e)
            return json.dumps({
                "ok": False,
                "message": str(e)
            })


    @pyqtSlot(result=str)
    def getShifts(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT 
                    id,
                    shift_name,
                    start_time,
                    end_time,
                    active,
                    created_at,
                    updated_at
                FROM SHIFT
                ORDER BY active DESC, id DESC
            """)

            rows = cursor.fetchall()
            conn.close()

            shifts = []

            for row in rows:
                shifts.append({
                    "id": row[0],
                    "shift_name": row[1],
                    "start_time": row[2],
                    "end_time": row[3],
                    "active": row[4],
                    "created_at": row[5],
                    "updated_at": row[6],
                })
    
            return json.dumps({
                "ok": True,
                "shifts": shifts
            })

        except Exception as e:
            return json.dumps({
                "ok": False,
                "shifts": [],
                "message": str(e)
            })


    def get_current_shift_name(self, cursor):
        try:
            now_time = datetime.now().strftime("%H:%M:%S")

            cursor.execute("""
                SELECT shift_name
                FROM SHIFT
                WHERE active = 1
                AND time(?) >= time(start_time)
                AND time(?) < time(end_time)
                LIMIT 1
            """, (now_time, now_time))

            row = cursor.fetchone()

            if row:
                return row[0]

            return ""

        except Exception as e:
            print("❌ get_current_shift_name error:", e)
            return ""

    def save_report_entry(self, result_status, bad_image_path="", total_strips=0, bad_strips=0, bad_strip_number=""):
        try:
            job_id, threshold = self.get_job_from_config()

            if not job_id:
                print("⚠️ No job_id found in config")
                return

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # ✅ Get current shift_name
            shift_name = self.get_current_shift_name(cursor)

            if not shift_name:
                print("⚠️ No active shift found")
                shift_name = "-"

            # ✅ Insert into REPORT
            cursor.execute("""
                INSERT INTO REPORT (
                    shift_name,
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
                shift_name,
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
                f"✅ Report row inserted: shift_name={shift_name}, job_id={job_id}, "
                f"threshold={threshold}, status={result_status}, image={bad_image_path}"
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
                rel_path = row[0]  # e.g. job_id/defect/defect_TIMESTAMP.jpg

                # Full path to the processed (display) image
                full_defect_path = str(PREDICTION_IMAGES_DIR / rel_path)

                # Derive raw path: job_id/defect_raw/raw_TIMESTAMP.bmp
                # rel_path format: job_id/defect/defect_TIMESTAMP.jpg
                import re
                raw_rel = re.sub(r'/defect/', '/defect_raw/', rel_path)
                raw_rel = re.sub(r'/defect_([^/]+)\.jpg$', r'/raw_\1.bmp', raw_rel)
                full_raw_path = str(PREDICTION_IMAGES_DIR / raw_rel)

                images.append({
                    "src": full_defect_path,
                    "raw_path": full_raw_path
                })

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

            # print("Returning counts =", data)
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

    # =============== CONTROLLER PAGE METHODS ========================
    @pyqtSlot(str, str, result=str)
    def cameraControl(self, action, value=""):
        try:
            if action == "getCameraDetails":
                config = {}

                if os.path.exists(self.config_path):
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)

                return json.dumps({
                    "ok": True,
                    "camera_name": config.get("camera_name", "MindVision"),
                    "min": int(config.get("min_exposure", 31)),
                    "max": int(config.get("max_exposure", 4063201))
                })
            if action == "getExposure":
                config = {}

                if os.path.exists(self.config_path):
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)

                return json.dumps({
                    "ok": True,
                    "value": config.get("exposure", 30000)
                })

            if action == "setExposure":
                exposure = int(value)

                config = {}
                if os.path.exists(self.config_path):
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)

                min_exp = int(config.get("min_exposure", 31))
                max_exp = int(config.get("max_exposure", 4063201))

                # ✅ Validation using JSON values
                if exposure < min_exp or exposure > max_exp:
                    return json.dumps({
                        "ok": False,
                        "message": f"Exposure must be between {min_exp} and {max_exp}"
                    })

                # ✅ Save back to JSON
                config["camera_name"] = config.get("camera_name", "MindVision")
                config["exposure"] = exposure
                config["min_exposure"] = min_exp
                config["max_exposure"] = max_exp

                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2)

                return json.dumps({
                    "ok": True,
                    "value": exposure
                })

            # ── Controller mode ────────────────────────────────────────────
            if action == "setMode":
                mode = value.strip().lower()   # "auto" | "manual"
                if mode not in ("auto", "manual"):
                    return json.dumps({"ok": False, "message": "Invalid mode"})
                config = {}
                if os.path.exists(self.config_path):
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                config["controller_mode"] = mode
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2)
                return json.dumps({"ok": True, "mode": mode})

            if action == "getControllerMode":
                config = {}
                if os.path.exists(self.config_path):
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                return json.dumps({"ok": True, "mode": config.get("controller_mode", "auto")})

            # ── I/O states (manual mode) ───────────────────────────────────
            if action == "getIOStates":
                config = {}
                if os.path.exists(self.config_path):
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                io = config.get("io_states", {})
                return json.dumps({
                    "ok": True,
                    "gripper":  bool(io.get("gripper",  False)),
                    "uv":       bool(io.get("uv",       False)),
                    "relay1":   bool(io.get("relay1",   False)),
                    "relay2":   bool(io.get("relay2",   False)),
                    "conveyor": bool(io.get("conveyor", False)),
                    "sensor":   bool(io.get("sensor",   False)),
                })

            if action == "getSignalStatus":
                config = {}
                if os.path.exists(self.config_path):
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                status = config.get("Signal Status", {})
                return json.dumps({
                    "ok": True,
                    "signal1": bool(status.get("signal1", False)),
                    "signal2": bool(status.get("signal2", False)),
                    "signal3": bool(status.get("signal3", False)),
                    "signal4": bool(status.get("signal4", False)),
                    "signal5": bool(status.get("signal5", False)),
                    "signal6": bool(status.get("signal6", False)),
                    "signal7": bool(status.get("signal7", False)),
                })

            if action in ("setGripper", "setUVLight", "setRelay1",
                          "setRelay2", "setConveyor", "setSensorLight"):
                on = value.strip().lower() == "true"
                key_map = {
                    "setGripper":     "gripper",
                    "setUVLight":     "uv",
                    "setRelay1":      "relay1",
                    "setRelay2":      "relay2",
                    "setConveyor":    "conveyor",
                    "setSensorLight": "sensor",
                }
                dev_key = key_map[action]
                config = {}
                if os.path.exists(self.config_path):
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                io = config.get("io_states", {})
                io[dev_key] = on
                config["io_states"] = io
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2)
                print(f"✅ IO {action} → {on}")
                return json.dumps({"ok": True, "device": dev_key, "value": on})

            # ── Signal Controls (write-only from JS right card) ────────────
            # Each action writes the signal state to hardware / config.
            # The Signal Status left card is driven purely by bridge signals
            # (counts_signal, defect_signal) and is never touched here.
            SIGNAL_ACTION_MAP = {
                "setWhiteLight":   "whitelight",
                "setUVLight2":     "uvlight",
                "setMachineBreak": "machinebreak",
                "setGreenLight":   "greenlight",
                "setYellowLight":  "yellowlight",
                "setRedLight":     "redlight",
                "setEmpty":        "empty",
            }
            if action in SIGNAL_ACTION_MAP:
                on = value.strip().lower() == "true"
                signal_key = SIGNAL_ACTION_MAP[action]

                # Persist to config
                config = {}
                if os.path.exists(self.config_path):
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                signals = config.get("Signal Controls", config.get("signal_states", {}))
                signals[signal_key] = on
                config.pop("signal_states", None)
                config["Signal Controls"] = signals
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2)

                # TODO: write to hardware relay here via modbus_relay_code
                # e.g. set_relay_output(signal_key, on)

                print(f"✅ Signal {action} ({signal_key}) → {on}")
                return json.dumps({"ok": True, "signal": signal_key, "value": on})

            return json.dumps({"ok": False, "message": f"Unknown action: {action}"})

        except Exception as e:
            return json.dumps({
                "ok": False,
                "message": str(e)
            })

    @pyqtSlot(result=str)
    def checkPlcConnection(self):
        try:
            return json.dumps({
                "ok": False,
                "message": "Not Connected"
            })
        except Exception as e:
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

    # def send_hourly_pdf_mail(self):
    #     try:
    #         from classes.invoice_pdf import InvoicePDFGenerator

    #         print("🔥 Hourly PDF generation started")
    #         end_time = datetime.now()
    #         start_time = end_time - timedelta(hours=1)

    #         start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
    #         end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

    #         print("⏰ Hourly PDF range:", start_time_str, "to", end_time_str)

    #         self.hourly_pdf_generator = InvoicePDFGenerator()
    #         self.hourly_pdf_generator.generate_pdf(
    #             parent=self.app_ref,
    #             finished_callback=self._send_pdf_after_generate,
    #             start_time=start_time_str,
    #             end_time=end_time_str
    #         )
    #         # self.hourly_pdf_generator.generate_pdf(
    #         #     parent=self.app_ref,
    #         #     finished_callback=self._send_pdf_after_generate
    #         # )

    #     except Exception as e:
    #         print("❌ send_hourly_pdf_mail error:", e)
    
    def parse_shift_datetime(self, base_date, time_value):
        raw_time = str(time_value).strip()

        if raw_time in ("24:00", "24:00:00"):
            return datetime.combine(base_date, datetime_time.min) + timedelta(days=1)

        if len(raw_time) == 5:
            raw_time = raw_time + ":00"

        parsed_time = datetime.strptime(raw_time[:8], "%H:%M:%S").time()
        return datetime.combine(base_date, parsed_time)

    def send_shift_pdf_mail(self):
        try:
            now = datetime.now()
            today = now.date()

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT shift_name, start_time, end_time
                FROM SHIFT
                WHERE active = 1
            """)

            rows = cursor.fetchall()
            conn.close()

            current_shift = None

            for shift_name, start_str, end_str in rows:
                for base_date in (today, today - timedelta(days=1)):
                    shift_start = self.parse_shift_datetime(base_date, start_str)
                    shift_end = self.parse_shift_datetime(base_date, end_str)

                    if shift_end <= shift_start:
                        shift_end = shift_end + timedelta(days=1)

                    if now >= shift_end and now < shift_end + timedelta(minutes=1):
                        current_shift = (shift_name, shift_start, shift_end)
                        break

                if current_shift:
                    break

            if not current_shift:
                return

            shift_name, start_time, end_time = current_shift

            shift_key = f"{shift_name}_{end_time.strftime('%Y%m%d_%H%M')}"

            if self.last_sent_shift_key == shift_key:
                print("⚠️ Shift PDF already sent:", shift_key)
                return

            self.last_sent_shift_key = shift_key

            save_shift_name = shift_name.replace(" ", "_").lower()
            self.current_shift_name = save_shift_name

            start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

            print("Shift PDF generation started")
            print("Shift           :", shift_name)
            print("Shift PDF Timing:", start_time_str, "to", end_time_str)

            self.current_shift_name = shift_name
            self.current_shift_date = start_time.strftime("%d-%m-%Y")

            self.hourly_pdf_generator = InvoicePDFGenerator()
            self.hourly_pdf_generator.generate_pdf(
                parent=self.app_ref,
                finished_callback=self._send_pdf_after_generate,
                start_time=start_time_str,
                end_time=end_time_str,
                force_report_start_time=start_time_str,
                force_report_end_time=end_time_str
            )
        except Exception as e:
            print("❌ send_shift_pdf_mail error:", e)


    def _send_pdf_after_generate(self, ok):
        try:
            if not ok:
                print("❌ Shift PDF generation failed. Mail not sent.")
                return

            from path import INVOICE_PDF, SHIFTWISE_PDF_REPORTS_DIR
            from classes.send_mail import send_last_generated_pdf
            from datetime import datetime
            import shutil
            import threading

            shift_date = getattr(self, "current_shift_date", datetime.now().strftime("%d-%m-%Y"))
            shift_name = getattr(self, "current_shift_name", "shift_report")
            safe_shift_name = str(shift_name).strip().lower().replace(" ", "_")
            save_pdf_path = SHIFTWISE_PDF_REPORTS_DIR / f"{shift_date}_{safe_shift_name}.pdf"

            shutil.copy2(str(INVOICE_PDF), str(save_pdf_path))

            print("✅ Shiftwise PDF saved:", save_pdf_path)

            threading.Thread(
                target=send_last_generated_pdf,
                daemon=True
            ).start()

            print("📧 Generated PDF mail triggered")

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

    @pyqtSlot()
    def goSettings(self):
        self.app_ref.load_page(SETTINGS_PAGE)
    #=====================================================================
    # 👉 467.89 GB = 100% (always)
    # 👉 94.9% is only used + free (incomplete data)
    # 👉 Remaining ~5.1% (23.84 GB) is:

    # system reserved
    # filesystem overhead
    # hidden usage
