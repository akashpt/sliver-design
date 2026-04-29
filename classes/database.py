from path import DB_FILE
import sqlite3

def get_connection():
    return sqlite3.connect(str(DB_FILE))

# ================= DATABASE INIT =================
def init_db():
    try:
        conn = get_connection()
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



# ---------------------------
# INSERT / UPDATE / DELETE
# ---------------------------
def execute(query, values=None):
    try:
        conn = get_connection()
        cur = conn.cursor()

        if values is not None:
            cur.execute(query, values)
        else:
            cur.execute(query)

        conn.commit()

        q = query.strip().lower()

        if q.startswith("insert"):
            # print(cur.lastrowid)
            return cur.lastrowid          # ✅ inserted row id

        if q.startswith("update") or q.startswith("delete"):
            return cur.rowcount           # ✅ affected rows count

        return True

    except Exception as e:
        print("DB execute error:", e)
        return False
    finally:
        if conn:
            conn.close()

# ---------------------------
# FETCH ONE
# ---------------------------
def fetch_one(query, values=None):
    try:
        """
        Returns a single row.
        """
        conn = get_connection()
        cur = conn.cursor()

        if values:
            cur.execute(query, values)
        else:
            cur.execute(query)

        row = cur.fetchone()
        conn.close()
        return row
    except Exception as e:
        print(e)
        return False

# ---------------------------
# FETCH ALL
# ---------------------------
def fetch_all(query, values=None):
    try:
        """
        Returns all rows.
        """
        conn = get_connection()
        cur = conn.cursor()

        if values:
            cur.execute(query, values)
        else:
            cur.execute(query)

        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(e)
        return False

# ---------------------------
# FETCH MANY
# ---------------------------
def fetch_many(query, size=10, values=None):
    try:
        """
        Returns N rows.
        """
        conn = get_connection()
        cur = conn.cursor()

        if values:
            cur.execute(query, values)
        else:
            cur.execute(query)

        rows = cur.fetchmany(size)
        conn.close()
        return rows
    except Exception as e:
        print(e)
        return False