from path import DB_FILE
import sqlite3

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