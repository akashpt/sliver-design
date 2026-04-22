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
            threshold TEXT,
            result TEXT NOT NULL,
            total_strips INTEGER,
            bad_strips INTEGER,
            bad_strip_number TEXT,
            bad_image_path TEXT,
            created_time TEXT DEFAULT (datetime('now', 'localtime')),
            updated_time TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """)

        cursor.execute("PRAGMA table_info(REPORT)")
        columns = [row[1] for row in cursor.fetchall()]

        if "threshold" not in columns:
            cursor.execute("ALTER TABLE REPORT ADD COLUMN threshold TEXT")

        conn.commit()
        conn.close()

    except Exception as e:
        print("❌ DB Init Error:", e)