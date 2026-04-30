import cv2
import numpy as np
import json
from pathlib import Path


class StripColorPrediction:

    def __init__(self, models_dir, variance_threshold=250.0):
        self.models_dir = Path(models_dir)

        self.expected_strip_count = 4
        self.minimum_strip_gap = 35
        self.center_crop_percent = 0.35

        self.variance_threshold = variance_threshold

    # ---------------- LOAD MODEL ----------------
    def load_model(self, model_key):
        model_path = self.models_dir / model_key / f"{model_key}.json"

        if not model_path.exists():
            return None

        with open(model_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ---------------- ROTATE IMAGE FIRST ----------------
    def rotate_image(self, img):
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    #     # if wrong, use:
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
        cv2.imwrite("debug_gray.png", gray)  # Debug: Save the grayscale image

        clahe = cv2.createCLAHE(5.0, (8, 8))
        gray_clahe = clahe.apply(gray)
        cv2.imwrite("debug_clahe.png", gray_clahe)  # Debug: Save the CLAHE image

        variance_value = float(np.var(gray_clahe))
        cv2.imwrite("debug_variance.png", cv2.convertScaleAbs(gray_clahe))  # Debug: Save the variance image
        return variance_value

    # ---------------- PROCESS FRAME ----------------
    def process_frame(self, img, model_data):
        # rotate first
        img = self.rotate_image(img)

        # then resize
        img = cv2.resize(img, (640, 480))
        height, width = img.shape[:2]

        margin = int(width * self.center_crop_percent)
        x_start, x_end = margin, width - margin

        vis = img.copy()
        strips = self.detect_horizontal_strips(img)

        if len(strips) != self.expected_strip_count:
            print(f"⚠ Detected {len(strips)} strips (expected {self.expected_strip_count})")
            return "error", vis, vis, 0, []

        strip_variance_values = model_data["strip_variance_values"]

        results = []

        for i, (y1, y2) in enumerate(strips, 1):
            roi = img[y1:y2, x_start:x_end]

            test_variance = self.calculate_variance(roi)

            if test_variance is None:
                results.append("EMPTY")
                continue

            ref_list = strip_variance_values.get(str(i), [])

            if len(ref_list) == 0:
                results.append("UNKNOWN")
                continue

            ref_mean = float(np.mean(ref_list))
            diff = abs(test_variance - ref_mean)

            if diff <= self.variance_threshold:
                status = "GOOD"
                color = (0, 255, 0)
            else:
                status = "DEFECT"
                color = (0, 0, 255)

            cv2.rectangle(vis, (x_start, y1), (x_end, y2), color, 2)
            cv2.putText(
                vis,
                f"S{i} {status} (V={test_variance:.2f}, D={diff:.2f})",
                (x_start + 5, max(20, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1
            )

            print(
                f"Strip {i} | Test={test_variance:.2f} | "
                f"RefMean={ref_mean:.2f} | Diff={diff:.2f} | {status}"
            )

            results.append(status)

        bad_strip_indices = [i for i, r in enumerate(results, 1) if r == "DEFECT"]
        bad_strip_count = len(bad_strip_indices)

        final_status = "good" if bad_strip_count == 0 else "defect"

        raw_img = img
        processed_img = vis

        return final_status, processed_img, raw_img, bad_strip_count, bad_strip_indices

    # ---------------- PROCESS IMAGE ----------------
    def process_image(self, img, model_key):
        model_data = self.load_model(model_key)

        if model_data is None:
            print("❌ MODEL NOT FOUND")
            vis = img.copy()
            return "error", vis, img, 0, []

        return self.process_frame(img, model_data)

    # ---------------- PREDICT FROM IMAGE PATH ----------------
    def predict_from_image_path(self, image_path, model_key, save_path=None, show=True):
        img = cv2.imread(str(image_path))

        if img is None:
            raise ValueError(f"❌ Failed to read image: {image_path}")

        status, processed_img, raw_img, bad_strip_count, bad_strip_indices = self.process_image(img, model_key)

        print(f"\n🖼 Image: {image_path}")
        print(f"✅ Final status: {status}")
        print(f"✅ Bad strip count: {bad_strip_count}")
        print(f"✅ Bad strip indices: {bad_strip_indices}")

        if save_path is not None:
            cv2.imwrite(str(save_path), processed_img)
            print(f"✅ Output saved at: {save_path}")

        if show:
            # cv2.imshow("Variance Prediction", processed_img)
            # cv2.waitKey(0)
            # cv2.destroyAllWindows()
            cv2.imwrite("output_debug.bmp", processed_img)
            print("✅ Image saved as output_debug.bmp")

        return status, processed_img, raw_img, bad_strip_count, bad_strip_indices


if __name__ == "__main__":
    predictor = StripColorPrediction(
        models_dir="/home/texa-developer/data/sliver/models",
        variance_threshold=100.0
    )

    predictor.predict_from_image_path("/home/texa-developer/data/sliver_delta/4s_vsf_white/train_20260417_113056_965408.bmp",
        model_key="viscose_train_18",
        save_path="/home/texa-developer/data/sliver/output_predictionnew50.bmp",
        show=True
    )