
import cv2
import base64
import json
import os
from datetime import datetime
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer
# from classes.mindvision import MindVisionCamera
from path import INDEX_PAGE, TRAINING_PAGE, SETTINGS_FILE, TRAINING_SETTINGS_FILE


class Bridge(QObject):

    frame_signal         = pyqtSignal(str)
    counts_signal        = pyqtSignal(str)
    defect_images_signal = pyqtSignal(str)

    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

        # Camera
        self.camera          = None
        self.cap             = None
        self.use_mindvision  = False
        self.camera_open     = False

        # Track current job so detection logic can call update_counts easily
        self.current_job_id  = ""

        # Frame timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.grab_frame)
        self.timer.timeout.connect(self.process_loop) 

       

    # ====================== SETTINGS HELPERS ======================

    def load_settings(self):
        """Load the full settings.json. Returns {} on any error."""
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            return {}
        except Exception as e:
            print("❌ load_settings error:", e)
            return {}

    def save_settings(self, settings: dict):
        """Save the full settings dict to settings.json."""
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print("❌ save_settings error:", e)

    def ensure_product(self, settings: dict, job_id: str):
        """
        Make sure the product key exists in settings with the correct structure.
        Never resets existing counts.
        """
        if job_id and job_id not in settings:
            settings[job_id] = {
                "jobId": job_id,
                "threshold": "",
                "counts": {
                    "inspected": 0,
                    "good": 0,
                    "defective": 0,
                    "lastUpdated": datetime.now().isoformat()
                }
            }
        return settings

    # ====================== CAMERA ======================

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

        except Exception as e:
            print("⚠️ MindVision not available:", e)
            self.camera       = None
            self.use_mindvision = False

            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                print("❌ Webcam not available")
                return "Camera not available"

            print("✅ Using Webcam")

        self.camera_open = True
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

    def grab_frame(self):
        try:
            frame = None

            # ── MindVision ──────────────────────────────────────────
            if self.use_mindvision and self.camera:
                frame = self.camera.get_frame()
                if frame is None:
                    print("⚠️ MindVision lost → switching to webcam")
                    self.use_mindvision = False
                    self.cap = cv2.VideoCapture(0)
                    return

            # ── Webcam ──────────────────────────────────────────────
            elif self.cap:
                ret, frame = self.cap.read()
                if not ret:
                    return
            else:
                return

            # ── Rotate ──────────────────────────────────────────────
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

            # ── Save current frame reference ─────────────────────────
            self.current_frame = frame.copy()

            # ── Send to UI ───────────────────────────────────────────
            _, buffer = cv2.imencode(".jpg", frame)
            jpg = base64.b64encode(buffer).decode("utf-8")
            self.frame_signal.emit(jpg)

            # ── Run detection (uncomment when ready) ─────────────────
            # if self.detector:
            #     self.run_detection()

        except Exception as e:
            print("❌ grab_frame error:", e)

    def process_loop(self):
                try:
                    # 🎥 FRAME
                    self.grab_frame()

                    # 📊 AUTO COUNT LOGIC (DEMO / AI HOOK)
                    if self.current_job_id:
                        import random
                        is_defect = random.random() < 0.3

                        if is_defect:
                            self.update_counts(self.current_job_id, 1, 0, 1)
                        else:
                            self.update_counts(self.current_job_id, 1, 1, 0)

                except Exception as e:
                    print("❌ process_loop error:", e)

    # ====================== CONFIGURATION ======================

    @pyqtSlot(result=str)
    def current_job_id(self):
        """
        Returns the last used job + its threshold + all available
        jobs and thresholds for the dropdowns.

        settings.json structure:
        {
            "_last_job": "Product A",
            "Product A": { jobId, threshold, counts },
            ...
        }
        """
        settings      = self.load_settings()
        last_job      = settings.get("_last_job", "")
        last_threshold = ""

        if last_job and last_job in settings:
            last_threshold = settings[last_job].get("threshold", "")

        data = {
            "job_id":    last_job,
            "threshold": last_threshold,
            "data": {
                "jobs":       ["Product A", "Product B", "Product C"],
                "thresholds": [1, 2, 3, 4, 5, 6],
            },
        }
        return json.dumps(data)

    @pyqtSlot(str, str, result=str)
    def saveUserConfig(self, job_id, threshold):
        """
        Saves the selected job + threshold.
        Creates a new product entry if it doesn't exist.
        NEVER resets existing counts.
        Also stores _last_job so the UI can restore it on next launch.
        """
        try:
            settings = self.load_settings()
            settings = self.ensure_product(settings, job_id)

            # Update threshold only — counts are never touched here
            if job_id:
                settings[job_id]["threshold"] = threshold

            # Remember last used job for next launch
            settings["_last_job"] = job_id

            self.save_settings(settings)
            self.current_job_id = job_id  # keep in memory for detection

            print("✅ Config saved — Job:", job_id, "| Threshold:", threshold)

            return json.dumps({"status": "success", "jobId": job_id})

        except Exception as e:
            print("❌ saveUserConfig error:", e)
            return json.dumps({"status": "error", "message": str(e)})

    # ====================== COUNTS ======================

    @pyqtSlot(str, result=str)
    def get_counts(self, job_id):
        """
        Returns the current counts for a product from the JSON file.
        Does NOT reset counts — only reads and returns them.
        Emits counts_signal so the UI updates immediately.
        """
        try:
            settings = self.load_settings()
            settings = self.ensure_product(settings, job_id)

            # If we created a new entry, persist it
            self.save_settings(settings)

            counts = settings[job_id].get("counts", {})
            counts.setdefault("inspected", 0)
            counts.setdefault("good", 0)
            counts.setdefault("defective", 0)

            result = {
                "jobId":     job_id,
                "inspected": counts["inspected"],
                "good":      counts["good"],
                "defective": counts["defective"],
                "lastUpdated": counts.get("lastUpdated", "")
            }

            json_data = json.dumps(result)
            self.counts_signal.emit(json_data)  # push to UI
            return json_data

        except Exception as e:
            print("❌ get_counts error:", e)
            return json.dumps({"status": "error", "message": str(e)})

    @pyqtSlot(str, int, int, int, result=str)
    def update_counts(self, job_id, inspected_delta, good_delta, defective_delta):
        """
        Called by detection logic to INCREMENT counts for a specific product.
        Pass deltas (how many to add), not absolute values.

        Example — item passed:
            self.update_counts(job_id, 1, 1, 0)

        Example — item failed:
            self.update_counts(job_id, 1, 0, 1)

        Saves to JSON and emits counts_signal so the UI updates live.
        """
        try:
            settings = self.load_settings()
            settings = self.ensure_product(settings, job_id)

            counts = settings[job_id].setdefault("counts", {})
            counts["inspected"]  = counts.get("inspected",  0) + inspected_delta
            counts["good"]       = counts.get("good",       0) + good_delta
            counts["defective"]  = counts.get("defective",  0) + defective_delta
            counts["lastUpdated"] = datetime.now().isoformat()

            settings[job_id]["counts"] = counts
            self.save_settings(settings)

            result = {
                "jobId":     job_id,
                "inspected": counts["inspected"],
                "good":      counts["good"],
                "defective": counts["defective"],
                "lastUpdated": counts["lastUpdated"]
            }

            json_data = json.dumps(result)
            self.counts_signal.emit(json_data)  # push live update to UI
            return json_data

        except Exception as e:
            print("❌ update_counts error:", e)
            return json.dumps({"status": "error", "message": str(e)})

    # ====================== DEFECT IMAGES ======================

    @pyqtSlot(result=str)
    def get_defect_images(self):
        """
        Returns existing defect images for the current session.
        Also emits defect_images_signal for real-time push.
        """
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
        json_data = json.dumps(data)
        self.defect_images_signal.emit(json_data)
        return json_data

    def emit_new_defect(self, image_base64_or_url: str):
        """
        Call this from detection logic when a NEW defect image is available.
        Pushes a single new defect image to the UI in real time.

        Example:
            self.emit_new_defect("data:image/jpeg;base64,/9j/4AAQ...")
            # or a URL:
            self.emit_new_defect("https://...")
        """
        data = {"images": [image_base64_or_url]}
        self.defect_images_signal.emit(json.dumps(data))

    # ====================== TRAINING ======================

    @pyqtSlot(str)
    def saveTrainingSession(self, json_str: str):
        try:
            data = json.loads(json_str)
            record = {
                "jobId":   data.get("jobId",  ""),
                "count":   data.get("count",  ""),
                "yarn":    data.get("yarn",   ""),
                "color":   data.get("color",  ""),
                "savedAt": datetime.now().isoformat(timespec="seconds"),
            }

            with open(TRAINING_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2)

            print(f"✅ Training session saved: {record['jobId']}")

        except Exception as e:
            print(f"❌ saveTrainingSession error: {e}")

    # ====================== NAVIGATION ======================

    @pyqtSlot()
    def goHome(self):
        self.app_ref.load_page(INDEX_PAGE)

    @pyqtSlot()
    def goReport(self):
        self.app_ref.open_report_window()

    @pyqtSlot()
    def goTraining(self):
        self.app_ref.load_page(TRAINING_PAGE)