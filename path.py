import sys
from pathlib import Path

# =====================================================
# CORE PATH HELPERS
# =====================================================


def app_path() -> Path:
    """
    Read-only application path
    - Normal run   → project root
    - PyInstaller  → _MEIPASS
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def run_path() -> Path:
    """
    Read/write runtime path
    - Normal run   → project root
    - PyInstaller  → exe folder
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


# =====================================================
# READ-ONLY (BUNDLED) PATHS
# =====================================================

APP_DIR = app_path()


# STATIC FILES
STATIC_DIR = APP_DIR / "static"
CSS_DIR = STATIC_DIR / "css"
JS_DIR = STATIC_DIR / "script"
IMG_DIR = STATIC_DIR / "img"
FONTS_DIR = STATIC_DIR / "fonts"
WEBFONTS_DIR = STATIC_DIR / "webfonts"

# TEMPLATES
TEMPLATES_DIR = APP_DIR / "templates"

INDEX_PAGE = TEMPLATES_DIR / "index.html"
TRAINING_PAGE = TEMPLATES_DIR / "training.html"
CONTROLLER_PAGE = TEMPLATES_DIR / "controller.html"
REPORT_PAGE = TEMPLATES_DIR / "report.html"
SLIVER_PDF_PAGE = TEMPLATES_DIR / "sliver_invoice.html"
EMAIL_PAGE = TEMPLATES_DIR / "email.html"
# CONFIG (READ-ONLY SDK FILES)
CONFIG_DIR = APP_DIR / "camera_sdk"


# =====================================================
# READ / WRITE (RUNTIME) PATHS
# =====================================================

RUN_DIR = run_path()

# App-specific runtime folder
RUN_DIR = RUN_DIR / "Sliver_Data"
RUN_DIR.mkdir(parents=True, exist_ok=True)

# DATA DIRECTORIES
DATA_DIR = RUN_DIR / "data"
TRAINING_IMAGES_DIR = DATA_DIR / "training_images"
PREDICTION_IMAGES_DIR = DATA_DIR / "prediction_images"


#USER CONFIG
USER_CONFIG_FILE = RUN_DIR / "settings.json"
#STORAGE
STORAGE_FILE = RUN_DIR / "storage.json"
#INVOICE
INVOICE_PDF = RUN_DIR / "belt-invoice.pdf"

# DATABASE
DB_FILE = RUN_DIR / "sliver.db"

# MODELS
MODELS_DIR = RUN_DIR / "models"
DEFAULT_MODEL = MODELS_DIR / "best.pt"

# SETTINGS FILES
SETTINGS_FILE = RUN_DIR / "settings.json"
TRAINING_SETTINGS_FILE = RUN_DIR / "training_settings.json"
CONTROLLER_SETTINGS_FILE = RUN_DIR / "controller_setting.json"


# SIGNAL FILES
SIGNAL_FILE = RUN_DIR / "signal.txt"
COUNT_FILE = RUN_DIR / "count.txt"


# =====================================================
# ENSURE DIRECTORIES
# =====================================================

DATA_DIR.mkdir(parents=True, exist_ok=True)
TRAINING_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
PREDICTION_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# =====================================================
# DEFAULT FILES (SAFE INIT)
# =====================================================

if not SIGNAL_FILE.exists():
    SIGNAL_FILE.write_text("", encoding="utf-8")

if not COUNT_FILE.exists():
    COUNT_FILE.write_text("0", encoding="utf-8")

if not USER_CONFIG_FILE.exists():
    USER_CONFIG_FILE.write_text("{}", encoding="utf-8")

if not STORAGE_FILE.exists():
    STORAGE_FILE.write_text("{}", encoding="utf-8")