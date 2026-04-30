import cv2
import numpy as np
import json
from pathlib import Path


class StripColorTraining:

    def __init__(self, models_dir):
        self.models_dir = Path(models_dir)

        self.expected_strip_count = 4
        self.minimum_strip_gap = 35
        self.center_crop_percent = 0.25

    # ---------------- ROTATE IMAGE FIRST ----------------
    def rotate_image(self, img):
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    # #     # if direction is wrong, use:
    #     # return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

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

        max_proj = np.max(projection) if len(projection) > 0 else 0
        if max_proj <= 0:
            return []

        for y in sorted_rows:
            if projection[y] < 0.55 * max_proj:
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

            fixed_height = 15
            mid = (y1 + y2) // 2

            new_y1 = max(0, mid - fixed_height // 2)
            new_y2 = min(height - 1, mid + fixed_height // 2)

            strips.append((new_y1, new_y2))

        return strips

    # ---------------- VARIANCE FUNCTION ----------------
    def calculate_variance(self, roi):
        if roi is None or roi.size == 0:
            return None

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        clahe = cv2.createCLAHE(5.0, (8, 8))
        gray_clahe = clahe.apply(gray)

        variance_value = float(np.var(gray_clahe))
        return variance_value

    # ---------------- PROCESS IMAGE ----------------
    def process_image(self, img):
        # STEP 1: rotate first
        img = self.rotate_image(img)

        # STEP 2: then resize
        img = cv2.resize(img, (640, 480))

        height, width = img.shape[:2]

        margin = int(width * self.center_crop_percent)
        x_start, x_end = margin, width - margin

        strips = self.detect_horizontal_strips(img)

        if len(strips) != self.expected_strip_count:
            print(f"⚠ Detected {len(strips)} strips (expected {self.expected_strip_count})")

        strip_variance_values = {}

        for strip_id, (y1, y2) in enumerate(strips, 1):
            roi = img[y1:y2, x_start:x_end]

            variance_value = self.calculate_variance(roi)

            if variance_value is None:
                continue

            strip_variance_values.setdefault(str(strip_id), []).append(
                variance_value
            )

        return strip_variance_values

    # ---------------- TRAIN ----------------
    def train(self, folder_path, model_key):
        folder_path = Path(folder_path)

        if not folder_path.exists():
            return {"ok": False, "message": "Folder not found"}

        all_strip_data = {str(i): [] for i in range(1, self.expected_strip_count + 1)}

        image_extensions = [".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"]

        for image_path in folder_path.iterdir():
            if image_path.suffix.lower() not in image_extensions:
                continue

            print("Processing:", image_path.name)

            img = cv2.imread(str(image_path))
            if img is None:
                print("⚠ Could not read:", image_path.name)
                continue

            strip_variance = self.process_image(img)

            if len(strip_variance) != self.expected_strip_count:
                print(f"⚠ Skipping {image_path.name} because {self.expected_strip_count} strips not found")
                continue

            for strip_id, values in strip_variance.items():
                all_strip_data[strip_id].extend(values)

        material_folder = self.models_dir / model_key
        material_folder.mkdir(parents=True, exist_ok=True)

        output_file = material_folder / f"{model_key}.json"

        model_data = {
            "strip_variance_values": all_strip_data,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(model_data, f, indent=4)

        print("\n✅ Training Completed")
        print(f"📁 Saved at: {output_file}")

        return {"ok": True, "model_path": str(output_file)}


if __name__ == "__main__":
    trainer = StripColorTraining("/home/texa-developer/data/sliver-design/models")

    trainer.train(
        folder_path="/home/texa-developer/data/sliver_delta/4s_vsf_white",
        model_key="viscose_train_18"
    )