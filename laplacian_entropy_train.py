# import cv2
# import numpy as np
# import json
# from pathlib import Path


# class StripTextureTraining:

#     def __init__(self, models_dir):
#         self.models_dir = Path(models_dir)

#         self.expected_strip_count = 4
#         self.minimum_strip_gap = 35
#         self.center_crop_percent = 0.25

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

#     # ---------------- FEATURE (UPDATED) ----------------
#     def extract_texture(self, roi):

#         gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

#         # CLAHE
#         clahe = cv2.createCLAHE(5.0, (8, 8))
#         gray = clahe.apply(gray)

#         # Gaussian Blur
#         gray = cv2.GaussianBlur(gray, (5, 5), 0)

#         # Variance
#         variance = float(np.var(gray))

#         # Entropy
#         hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
#         prob = hist / np.sum(hist)
#         prob = prob[prob > 0]
#         entropy = float(-np.sum(prob * np.log2(prob)))

#         return variance, entropy

#     # ---------------- TRAIN ----------------
#     def train(self, folder_path, model_key):

#         folder_path = Path(folder_path)

#         # store strip-wise data
#         all_var = {str(i): [] for i in range(1, 5)}
#         all_ent = {str(i): [] for i in range(1, 5)}

#         print("🔄 Training started...\n")

#         for img_path in folder_path.iterdir():

#             if img_path.suffix.lower() not in [".jpg", ".png", ".bmp"]:
#                 continue

#             print("Processing:", img_path.name)

#             img = cv2.imread(str(img_path))
#             if img is None:
#                 continue

#             img = self.rotate_image(img)
#             img = cv2.resize(img, (640, 480))

#             h, w = img.shape[:2]
#             margin = int(w * self.center_crop_percent)
#             x1, x2 = margin, w - margin

#             strips = self.detect_horizontal_strips(img)

#             if len(strips) != 4:
#                 print("⚠ Skipping:", img_path.name)
#                 continue

#             for i, (y1, y2) in enumerate(strips, 1):

#                 roi = img[y1:y2, x1:x2]

#                 var, ent = self.extract_texture(roi)

#                 all_var[str(i)].append(var)
#                 all_ent[str(i)].append(ent)

#                 print(f"{img_path.name} | S{i} → Var={var:.2f}, Ent={ent:.2f}")

#         # -------- CALCULATE STATS --------
#         strip_stats = {}

#         for i in range(1, 5):
#             key = str(i)

#             if len(all_var[key]) > 0:
#                 strip_stats[key] = {
#                     "var_mean": float(np.mean(all_var[key])),
#                     "var_std": float(np.std(all_var[key])),
#                     "ent_mean": float(np.mean(all_ent[key])),
#                     "ent_std": float(np.std(all_ent[key]))
#                 }

#         # -------- SAVE MODEL --------
#         model = {
#             "strip_stats": strip_stats
#         }

#         save_dir = self.models_dir / model_key
#         save_dir.mkdir(parents=True, exist_ok=True)

#         with open(save_dir / f"{model_key}.json", "w") as f:
#             json.dump(model, f, indent=4)

#         print("\n✅ Training Completed")
#         print(f"📁 Model saved at: {save_dir}")


# if __name__ == "__main__":

#     # 1. Create object
#     trainer = StripTextureTraining(
#         models_dir="/home/texa-developer/data/sliver/models"
#     )

#     # 2. Run training (ONLY GOOD IMAGES)
#     trainer.train(
#         folder_path="/home/texa-developer/data/sliver-design/viscose_images_18/img_20260418_154641_814220.bmp",
#         model_key="viscose_texture_18"
#     )




import cv2
import numpy as np
import json
from pathlib import Path


class StripTextureTraining:

    def __init__(self, models_dir, strip_count=8):

        self.models_dir = Path(models_dir)

        self.expected_strip_count = strip_count
        self.minimum_strip_gap = 35
        self.center_crop_percent = 0.25

    # ---------------- ROTATE ----------------
    # def rotate_image(self, img):
    #     return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)

    # ---------------- DETECT STRIPS ----------------
    def detect_horizontal_strips(self, image):

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        _, thresh = cv2.threshold(
            gray, 0, 255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        if np.mean(thresh) > 150:
            thresh = cv2.bitwise_not(thresh)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (60, 3))
        mask = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        proj = np.sum(mask > 0, axis=1)

        # 🔥 improved smoothing
        proj = np.convolve(proj, np.ones(25)/25, mode="same")

        rows = np.argsort(proj)[::-1]
        centers = []

        for y in rows:
            # 🔥 lower threshold for low contrast strips
            if proj[y] < 0.35 * np.max(proj):
                break

            if all(abs(y - c) > self.minimum_strip_gap for c in centers):
                centers.append(y)

            if len(centers) == self.expected_strip_count:
                break

        centers = sorted(centers)

        strips = []
        for c in centers:

            y1 = y2 = c
            th = proj[c] * 0.5

            while y1 > 0 and proj[y1] > th:
                y1 -= 1

            while y2 < len(proj)-1 and proj[y2] > th:
                y2 += 1

            mid = (y1 + y2) // 2
            h = 25

            strips.append((mid - h//2, mid + h//2))

        return strips

    # ---------------- FEATURE ----------------
    def extract_texture(self, roi):

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        clahe = cv2.createCLAHE(5.0, (8, 8))
        gray = clahe.apply(gray)

        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        variance = float(np.var(gray))

        hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
        prob = hist / np.sum(hist)
        prob = prob[prob > 0]
        entropy = float(-np.sum(prob * np.log2(prob)))

        return variance, entropy

    # ---------------- TRAIN ----------------
    def train(self, folder_path, model_key):

        folder_path = Path(folder_path)

        all_var = {str(i): [] for i in range(1, self.expected_strip_count+1)}
        all_ent = {str(i): [] for i in range(1, self.expected_strip_count+1)}

        print("🔄 Training started...\n")

        for img_path in folder_path.iterdir():

            if img_path.suffix.lower() not in [".jpg", ".png", ".bmp"]:
                continue

            print("Processing:", img_path.name)

            img = cv2.imread(str(img_path))
            if img is None:
                continue

            # img = self.rotate_image(img)
            img = cv2.resize(img, (640, 480))

            h, w = img.shape[:2]
            margin = int(w * self.center_crop_percent)
            x1, x2 = margin, w - margin

            strips = self.detect_horizontal_strips(img)

            print("Detected strips:", len(strips))

            # 🔥 strict check (now OK since fixed count)
            if len(strips) != self.expected_strip_count:
                print("⚠ Skipping:", img_path.name)
                continue

            for i, (y1, y2) in enumerate(strips, 1):

                roi = img[y1:y2, x1:x2]

                if roi.size == 0:
                    continue

                var, ent = self.extract_texture(roi)

                all_var[str(i)].append(var)
                all_ent[str(i)].append(ent)

                print(f"{img_path.name} | S{i} → Var={var:.2f}, Ent={ent:.2f}")

        # -------- CALCULATE STATS --------
        strip_stats = {}

        for i in range(1, self.expected_strip_count+1):

            key = str(i)

            if len(all_var[key]) == 0:
                continue

            strip_stats[key] = {
                "var_mean": float(np.mean(all_var[key])),
                "var_std": max(0.01, float(np.std(all_var[key]))),   # 🔥 safety
                "ent_mean": float(np.mean(all_ent[key])),
                "ent_std": max(0.01, float(np.std(all_ent[key])))    # 🔥 safety
            }

        # -------- SAVE MODEL --------
        model = {
            "strip_stats": strip_stats,
            "strip_count": self.expected_strip_count
        }

        save_dir = self.models_dir / model_key
        save_dir.mkdir(parents=True, exist_ok=True)

        with open(save_dir / f"{model_key}.json", "w") as f:
            json.dump(model, f, indent=4)

        print("\n✅ Training Completed")
        print(f"📁 Model saved at: {save_dir}")


# ---------------- MAIN ----------------
if __name__ == "__main__":

    trainer = StripTextureTraining(
        models_dir="/home/texa-developer/data/sliver-design/models",
        strip_count=8   # 🔥 SET HERE (4 / 6 / 8)
    )

    trainer.train(
        folder_path="/home/texa-developer/data/sliver_delta/good_test_imgs",
        model_key="viscose_texture_18"
    )