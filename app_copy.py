# app.py
import sys
import os
import sqlite3
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtCore import QUrl
from pathlib import Path
from classes.bridge import Bridge
from path import TEMPLATES_DIR,REPORT_PAGE,DB_FILE

IS_WINDOWS = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")

# ===============================
# Platform selection
# ===============================
if IS_LINUX:
    os.environ["QT_QPA_PLATFORM"] = "xcb"
elif IS_WINDOWS:
    os.environ["QT_QPA_PLATFORM"] = "windows"


if getattr(sys, 'frozen', False):
   
    base = Path(sys.executable).resolve().parent
    import cv2
    cv2_path = os.path.dirname(cv2.__file__)
    os.environ["QT_PLUGIN_PATH"] = os.path.join(cv2_path, "qt", "plugins")
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(cv2_path, "qt", "plugins", "platforms")

else:
    import cv2 as _cv2
    qt_plugin_path = os.path.join(os.path.dirname(_cv2.__file__), "qt", "plugins", "platforms")
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = qt_plugin_path

# ================= DATABASE INIT =================
def init_db():
    try:
        conn = sqlite3.connect(str(DB_FILE))
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS REPORT (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shift_id INTEGER,
            machine_no TEXT NOT NULL,
            job_id TEXT NOT NULL,
            result TEXT NOT NULL,
            total_strips INTEGER,
            bad_strips INTEGER,
            bad_strip_number TEXT,
            bad_image_path TEXT,
            created_time TEXT,
            updated_time TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """)

        conn.commit()
        conn.close()

        print("✅ Database + Tables initialized from app.py")
        print("📂 DB Path:", DB_FILE)

    except Exception as e:
        print("❌ DB Init Error:", e)

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Sliver Design System")
        self.resize(1200, 800)

        # WebEngine View
        self.view = QWebEngineView()
        self.setCentralWidget(self.view)

        # Bridge & WebChannel
        self.bridge = Bridge(self)
        self.channel = QWebChannel()
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        # Load finished handler
        self.view.loadFinished.connect(self.on_load_finished)

        # Load initial page
        self.load_page("index.html")

    def load_page(self, page_name: str):
        print(f"Switching to page: {page_name}")

        file_path = (TEMPLATES_DIR / page_name).resolve()

        if file_path.exists():
            self.view.setUrl(QUrl("about:blank"))
            self.view.load(QUrl.fromLocalFile(str(file_path)))
        else:
            print(f"❌ Page not found: {file_path}")

    def open_report_window(self):
        if (
            hasattr(self, "report_window")
            and self.report_window
            and self.report_window.isVisible()
        ):
            self.report_window.activateWindow()
            return

        self.report_window = QMainWindow()
        self.report_window.setWindowTitle("Report")
        self.report_window.setFixedSize(1000, 700)

        view = QWebEngineView()
        self.report_window.setCentralWidget(view)

        report_file = (REPORT_PAGE).resolve()

        if report_file.exists():
            view.load(QUrl.fromLocalFile(str(report_file)))
        else:
            print(f"❌ report.html not found: {report_file}")

        self.report_window.show()

    def closeEvent(self, event):
        self.bridge.stopCamera()  # Ask bridge to cleanup camera
        super().closeEvent(event)

    def on_load_finished(self):
        print("✅ Page loaded successfully")


# ------------------- MAIN -------------------
if __name__ == "__main__":
    init_db()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
