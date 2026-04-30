# import cv2
# import numpy as np
# import json
# from pathlib import Path


# class StripTexturePrediction:

#     def __init__(self, model_path):
#         self.model_path = Path(model_path)

#         self.expected_strip_count = 4
#         self.minimum_strip_gap = 35
#         self.center_crop_percent = 0.25

#         # Load model
#         with open(self.model_path, "r") as f:
#             self.model = json.load(f)

#     # ---------------- ROTATE ----------------
#     def rotate_image(self, img):
#         return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)

#     # ---------------- DETECT STRIPS ----------------
#     def detect_horizontal_strips(self, image):

#         gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

#         _, thresh = cv2.threshold(
#             gray, 0, 255,
#             cv2.THRESH_BINARY + cv2.THRESH_OTSU
#         )

#         if np.mean(thresh) > 150:
#             thresh = cv2.bitwise_not(thresh)

#         kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (60, 3))
#         mask = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

#         proj = np.sum(mask > 0, axis=1)
#         proj = np.convolve(proj, np.ones(15)/15, mode="same")

#         rows = np.argsort(proj)[::-1]
#         centers = []

#         for y in rows:
#             if proj[y] < 0.55 * np.max(proj):
#                 break

#             if all(abs(y - c) > self.minimum_strip_gap for c in centers):
#                 centers.append(y)

#             if len(centers) == self.expected_strip_count:
#                 break

#         centers = sorted(centers)

#         strips = []
#         for c in centers:

#             y1 = y2 = c
#             th = proj[c] * 0.5

#             while y1 > 0 and proj[y1] > th:
#                 y1 -= 1

#             while y2 < len(proj)-1 and proj[y2] > th:
#                 y2 += 1

#             mid = (y1 + y2) // 2
#             h = 25

#             strips.append((mid - h//2, mid + h//2))

#         return strips

#     # ---------------- FEATURE ----------------
#     def extract_texture(self, roi):

#         gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

#         # CLAHE
#         clahe = cv2.createCLAHE(5.0, (8, 8))
#         gray = clahe.apply(gray)

#         # Blur
#         gray = cv2.GaussianBlur(gray, (5, 5), 0)

#         # Variance
#         variance = float(np.var(gray))

#         # Entropy
#         hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
#         prob = hist / np.sum(hist)
#         prob = prob[prob > 0]
#         entropy = float(-np.sum(prob * np.log2(prob)))

#         return variance, entropy

#     # ---------------- PREDICT ----------------
#     def predict(self, image_path):

#         img = cv2.imread(str(image_path))
#         if img is None:
#             print("❌ Image not found")
#             return

#         img = self.rotate_image(img)
#         img = cv2.resize(img, (640, 480))

#         h, w = img.shape[:2]
#         margin = int(w * self.center_crop_percent)
#         x1, x2 = margin, w - margin

#         strips = self.detect_horizontal_strips(img)

#         if len(strips) != 4:
#             print("❌ Strip detection failed")
#             return

#         print("\n🔍 Prediction Results:\n")

#         for i, (y1, y2) in enumerate(strips, 1):

#             roi = img[y1:y2, x1:x2]

#             var, ent = self.extract_texture(roi)

#             stats = self.model["strip_stats"][str(i)]

#             # Normalize
#             norm_var = abs(var - stats["var_mean"]) / (stats["var_std"] + 1e-6)
#             norm_ent = abs(ent - stats["ent_mean"]) / (stats["ent_std"] + 1e-6)

#             # Score
#             score = 0.6 * norm_var + 0.4 * norm_ent

#             # Decision
#             if score > 2.0:
#                 label = "DEFECT"
#                 color = (0, 0, 255)
#             else:
#                 label = "NORMAL"
#                 color = (0, 255, 0)

#             print(f"S{i}: {label} | Var={var:.2f}, Ent={ent:.2f}, Score={score:.2f}")

#             # Draw result
#             cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
#             cv2.putText(img, f"S{i}:{label}", (x1, y1-5),
#                         cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

#         output_path = "output_result.jpg"
#         cv2.imwrite(output_path, img)

#         print(f"\n✅ Output saved: {output_path}")

# if __name__ == "__main__":

#     predictor = StripTexturePrediction(
#         model_path="/home/texa-developer/data/sliver/models/viscose_texture_18/viscose_texture_18.json"
#     )

#     predictor.predict(
#         image_path="/home/texa-developer/data/sliver-design/viscose_bad_images_18/img_20260418_155940_916315_crop.jpg"
#     )       





import cv2
import numpy as np
import json
from pathlib import Path

MODELS_DIR = Path("/home/texa-developer/data/sliver/models")

# from path import MODELS_DIR


class StripTexturePrediction:

    def __init__(self, texture_threshold=2.0):

        self.expected_strip_count = 8
        self.minimum_strip_gap = 35
        self.center_crop_percent = 0.25

        self.texture_threshold = texture_threshold

    # ---------------- LOAD MODEL ----------------
    def load_model(self, model_key):

        model_path = MODELS_DIR / model_key / f"{model_key}.json"

        if not model_path.exists():
            model_path = MODELS_DIR / model_key

        if not model_path.exists():
            return None

        with open(model_path, "r") as f:
            return json.load(f)

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
            threshold = peak_value * 0.5

            while y1 > 0 and projection[y1] > threshold:
                y1 -= 1

            while y2 < height - 1 and projection[y2] > threshold:
                y2 += 1

            fixed_height = 25
            mid = (y1 + y2) // 2

            new_y1 = max(0, mid - fixed_height // 2)
            new_y2 = min(height - 1, mid + fixed_height // 2)

            strips.append((new_y1, new_y2))

        return strips

    # ---------------- TEXTURE FEATURE ----------------
    def extract_texture(self, roi):

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        # CLAHE
        clahe = cv2.createCLAHE(5.0, (8, 8))
        gray = clahe.apply(gray)

        # Blur
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        # Variance
        variance = float(np.var(gray))

        # Entropy
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
        prob = hist / np.sum(hist)
        prob = prob[prob > 0]
        entropy = float(-np.sum(prob * np.log2(prob)))

        return variance, entropy

    # ---------------- PROCESS FRAME ----------------
    def process_frame(self, img, model_data):

        img = cv2.resize(img, (640, 480))
        height, width = img.shape[:2]

        margin = int(width * self.center_crop_percent)
        x_start, x_end = margin, width - margin

        vis = img.copy()
        strips = self.detect_horizontal_strips(img)

        if len(strips) != self.expected_strip_count:
            return "strip missing", vis, vis, 0, []

        results = []

        for i, (y1, y2) in enumerate(strips, 1):

            roi = img[y1:y2, x_start:x_end]

            if roi.size == 0:
                results.append("EMPTY")
                continue

            var, ent = self.extract_texture(roi)

            stats = model_data["strip_stats"].get(str(i), None)

            if stats is None:
                results.append("UNKNOWN")
                continue

            # -------- NORMALIZATION --------
            norm_var = abs(var - stats["var_mean"]) / (stats["var_std"] + 1e-6)
            norm_ent = abs(ent - stats["ent_mean"]) / (stats["ent_std"] + 1e-6)

            # -------- SCORE --------
            score = 0.6 * norm_var + 0.4 * norm_ent

            # -------- DECISION --------
            if score > self.texture_threshold:
                status = "DEFECT"
                color = (0, 0, 255)
            else:
                status = "GOOD"
                color = (0, 255, 0)

            # -------- DRAW --------
            cv2.rectangle(vis, (x_start, y1), (x_end, y2), color, 2)
            cv2.putText(
                vis,
                f"S{i} {status} (S={score:.2f})",
                (x_start + 5, max(20, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2
            )

            results.append(status)

        # -------- FINAL RESULT --------
        bad_strip_indices = [i for i, r in enumerate(results, 1) if r == "DEFECT"]
        bad_strip_count = len(bad_strip_indices)

        if bad_strip_count == 0:
            final_status = "good"
        else:
            final_status = "defect"

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



if __name__ == "__main__":

    model_key = "viscose_texture_18"

    image_path = "/home/texa-developer/data/sliver_delta/bad_yellow/yellow_1/img_0001.bmp"

    img = cv2.imread(image_path)

    if img is None:
        print("❌ Image not found")
        exit()

    predictor = StripTexturePrediction(texture_threshold=2.0)

    status, processed_img, raw_img, bad_count, bad_indices = predictor.process_image(
        img,
        model_key
    )

    print("\n🔍 FINAL RESULT")
    print("Status:", status)
    print("Bad strip count:", bad_count)
    print("Bad strips:", bad_indices)

    # Save output
    cv2.imwrite("output_result.jpg", processed_img)

    print("✅ Output saved: output_result.jpg")