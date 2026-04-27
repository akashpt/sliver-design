import cv2
import numpy as np
import json
from pathlib import Path

from path import MODELS_DIR

# raw_img is an optional output (defect raw frame without annotation).
# If not used, it can be removed — but ensure all return formats
# (process_frame) return remove raw_img, len(strip) return remove one vis, and (model not found) return remove one img.

class StripColorPrediction:

    def __init__(self, color_threshold=2.0):

        self.expected_strip_count = 8
        self.minimum_strip_gap = 35
        self.center_crop_percent = 0.25
        self.color_threshold = color_threshold

    # ---------------- LOAD MODEL ----------------

    def load_model(self, model_key):
        try:
        
            model_path = MODELS_DIR / model_key / f"{model_key}.json"

            if not model_path.exists():
                model_path = MODELS_DIR / model_key

            if not model_path.exists():
                return None

            with open(model_path, "r") as f:
                return json.load(f)
        except Exception as e:
            print("Load Model Error :",e)

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

            fixed_height = 12
            mid = (y1 + y2) // 2

            new_y1 = max(0, mid - fixed_height // 2)
            new_y2 = min(height - 1, mid + fixed_height // 2)

            strips.append((new_y1, new_y2))

        return strips

    # ---------------- DELTA E ----------------
    def delta_e(self, lab1, lab2):
        return np.sqrt(np.sum((np.array(lab1) - np.array(lab2)) ** 2))

    # ---------------- PROCESS IMAGE ----------------
    def process_frame(self, img, model_data):
        full_img = img.copy()
        img = cv2.resize(img, (640, 480))
        height, width = img.shape[:2]
        
        margin = int(width * self.center_crop_percent)
        x_start, x_end = margin, width - margin

        vis = img.copy()
        strips = self.detect_horizontal_strips(img)

        if len(strips) != self.expected_strip_count:
                found = len(strips)
                expected = self.expected_strip_count

                msg = f"Strip Missing  |  Found: {found} / Expected: {expected}"

                overlay = vis.copy()

                bar_height = 60

                # --- Top full-width bar ---
                cv2.rectangle(overlay, (0, 0), (width, bar_height), (20, 20, 20), -1)

                # --- Transparency ---
                cv2.addWeighted(overlay, 0.6, vis, 0.4, 0, vis)

                # --- Text settings ---
                font = cv2.FONT_HERSHEY_SIMPLEX
                scale = 0.7
                thickness = 2

                (text_w, text_h), _ = cv2.getTextSize(msg, font, scale, thickness)

                # --- Center text ---
                text_x = (width - text_w) // 2
                text_y = (bar_height + text_h) // 2 - 5

                # --- Optional white outline (for better visibility) ---
                cv2.putText(vis, msg, (text_x, text_y), font, scale, (255, 255, 255), 3, cv2.LINE_AA)

                # --- Main RED text ---
                cv2.putText(vis, msg, (text_x, text_y), font, scale, (0, 0, 255), 2, cv2.LINE_AA)

                return "strip missing", vis, vis, 0, []


        strip_lab_values = model_data["strip_lab_values"]
        
        threshold = self.color_threshold

        results = []

        for i, (y1, y2) in enumerate(strips, 1):

            roi = img[y1:y2, x_start:x_end]

            if roi.size == 0:
                results.append("EMPTY")
                continue

            # -------- BACKGROUND DETECTION --------
            gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

            # dark pixels = background
            bg_mask = gray_roi < 45

            # find background contours - Find Connected Background Regions
            contours, _ = cv2.findContours(
                bg_mask.astype(np.uint8),
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            for cnt in contours:
                area = cv2.contourArea(cnt)

                if area > 10:   # ignore tiny noise
                    bx, by, bw, bh = cv2.boundingRect(cnt)

                    # convert ROI coords -> full image coords
                    cv2.rectangle(
                        vis,
                        (x_start + bx, y1 + by),
                        (x_start + bx + bw, y1 + by + bh),
                        (0, 0, 255),   # red
                        2
                    )

                    print("frame ignored because of bg")

                    return "ignored", vis, img, 0, []

            # -------- LAB MEAN --------
            lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)

            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(5.0, (8, 8))
            l_clahe = clahe.apply(l)
            final_lab = cv2.merge([l_clahe, a, b])

            test_lab = [
                float(np.mean(final_lab[:, :, 0])),
                float(np.mean(final_lab[:, :, 1])),
                float(np.mean(final_lab[:, :, 2]))
            ]

            ref_list = strip_lab_values.get(str(i), [])

            if len(ref_list) == 0:
                results.append("UNKNOWN")
                continue

            # -------- ΔE --------
            dE_list = [self.delta_e(ref, test_lab) for ref in ref_list]
            min_dE = min(dE_list)

            # -------- DECISION --------
            if min_dE <= threshold:
                status = "GOOD"
                color = (0, 255, 0)
            else:
                status = "DEFECT"
                color = (0, 0, 255)

            # -------- DRAW --------
            cv2.rectangle(vis, (x_start, y1), (x_end, y2), color, 2)
            cv2.putText(
                vis,
                f"S{i} {status} (dE={min_dE:.2f})",
                (x_start + 5, max(20, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2
            )

            results.append(status)

        print("frame entered prediction")

        # -------- FINAL return --------
        bad_strip_indices = [i for i, r in enumerate(results, 1) if r == "DEFECT"]
        bad_strip_count = len(bad_strip_indices)

        if bad_strip_count == 0:
            status = "good"
        else:
            status = "defect"
            
        # raw_img = img
        processed_img = vis

        return status, processed_img, full_img, bad_strip_count, bad_strip_indices

    # ---------------- ----------------
    def process_image(self, img, model_key):
        model_data = self.load_model(model_key)

        if model_data is None:
            print("❌ MODEL NOT FOUND")
            vis = img.copy()
            return "error", vis, img, 0, []

        return self.process_frame(img, model_data)

