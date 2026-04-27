import cv2
import numpy as np
import json
from pathlib import Path

from path import MODELS_DIR


class StripColorTraining:

    def __init__(self):
        
        self.expected_strip_count = 8
        self.minimum_strip_gap = 35
        self.center_crop_percent = 0.25

    # ---------------- DETECT STRIPS ----------------
    def detect_horizontal_strips(self, image):

        height, width = image.shape[:2]

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        _, thresh = cv2.threshold(
            gray, 0, 255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        if np.mean(thresh) > 150:
            thresh = cv2.bitwise_not(thresh)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (60, 3))
        mask = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        projection = np.sum(mask > 0, axis=1)
        projection = np.convolve(projection, np.ones(15) / 15, mode="same")

        sorted_rows = np.argsort(projection)[::-1]
        strip_centers = []

        for y in sorted_rows:
            if projection[y] < 0.55 * np.max(projection):
                break

            if all(abs(y - c) > self.minimum_strip_gap for c in strip_centers):
                strip_centers.append(y)

            if len(strip_centers) == self.expected_strip_count:
                break

        strip_centers = sorted(strip_centers)

        strips = []
        for center_y in strip_centers:

            y1, y2 = center_y, center_y
            peak_value = projection[center_y]
            threshold_value = peak_value * 0.5

            while y1 > 0 and projection[y1] > threshold_value:
                y1 -= 1

            while y2 < height - 1 and projection[y2] > threshold_value:
                y2 += 1

            fixed_height = 12
            mid = (y1 + y2) // 2

            new_y1 = max(0, mid - fixed_height // 2)
            new_y2 = min(height - 1, mid + fixed_height // 2)

            strips.append((new_y1, new_y2))

        return strips

    # ---------------- PROCESS IMAGE ----------------
    def process_image(self, img):

        img = cv2.resize(img, (640, 480))
        height, width = img.shape[:2]
        
        margin = int(width * self.center_crop_percent)
        x_start, x_end = margin, width - margin

        strips = self.detect_horizontal_strips(img)

        strip_lab_values = {}

        for strip_id, (y1, y2) in enumerate(strips, 1):

            roi = img[y1:y2, x_start:x_end]

            if roi.size == 0:
                continue
            
            '''
            # ================= SAVE EACH STRIP =================
            strip_folder = Path("output_strips") / image_name.split('.')[0]
            strip_folder.mkdir(parents=True, exist_ok=True)

            strip_path = strip_folder / f"strip_{strip_id}.png"
            cv2.imwrite(str(strip_path), roi)
            # ===================================================
            '''

            # -------- LAB MEAN --------
            lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
            
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(5.0, (8, 8))
            l_clahe = clahe.apply(l)
            final_lab = cv2.merge([l_clahe, a, b])

            mean_L = float(np.mean(final_lab[:, :, 0]))
            mean_A = float(np.mean(final_lab[:, :, 1]))
            mean_B = float(np.mean(final_lab[:, :, 2]))

            strip_lab_values.setdefault(str(strip_id), []).append(
                [mean_L, mean_A, mean_B]
            )

        return strip_lab_values

    # ---------------- TRAIN ----------------
    def train(self, folder_path, model_key):

        folder_path = Path(folder_path)

        if not folder_path.exists():
            return {"ok": False, "message": "Folder not found"}

        all_strip_data = {str(i): [] for i in range(1, 9)}

        image_extensions = [".jpg", ".jpeg", ".png", ".bmp"]

        # -------- STEP 1: COLLECT LAB VALUES --------
        for image_path in folder_path.iterdir():

            if image_path.suffix.lower() not in image_extensions:
                continue

            print("Processing:", image_path.name)

            img = cv2.imread(str(image_path))
            if img is None:
                continue

            strip_lab = self.process_image(img)

            for strip_id, values in strip_lab.items():
                all_strip_data[strip_id].extend(values)
        
        # -------- STEP 2: SAVE JSON --------
        material_folder = MODELS_DIR / model_key
        material_folder.mkdir(parents=True, exist_ok=True)

        output_file = material_folder / f"{model_key}.json"

        model_data = {
            "strip_lab_values": all_strip_data,
        }

        with open(output_file, "w") as f:
            json.dump(model_data, f, indent=4)

        print("\n✅ Training Completed")

        return {"ok": True}