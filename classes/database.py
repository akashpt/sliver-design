from path import DB_FILE
import sqlite3

def get_connection():
    return sqlite3.connect(str(DB_FILE))

def is_shift_time_overlapping(cursor, start_time, end_time, exclude_shift_name=None):
    if exclude_shift_name:
        cursor.execute("""
            SELECT id, shift_name
            FROM SHIFT
            WHERE active = 1
            AND LOWER(TRIM(shift_name)) != LOWER(TRIM(?))
            AND time(?) < time(end_time)
            AND time(?) > time(start_time)
        """, (exclude_shift_name, start_time, end_time))
    else:
        cursor.execute("""
            SELECT id, shift_name
            FROM SHIFT
            WHERE active = 1
            AND time(?) < time(end_time)
            AND time(?) > time(start_time)
        """, (start_time, end_time))

    return cursor.fetchone()

def create_new_shift_version(shift_name, start_time, end_time):
    try:
        shift_name = " ".join(str(shift_name).strip().split()).title()
        start_time = str(start_time).strip()
        end_time = str(end_time).strip()

        if not shift_name:
            return {
                "ok": False,
                "message": "Shift name is required"
            }

        if not start_time or not end_time:
            return {
                "ok": False,
                "message": "Start time and end time are required"
            }

        # Convert 09:00 to 09:00:00
        if len(start_time) == 5:
            start_time = start_time + ":00"

        if len(end_time) == 5:
            end_time = end_time + ":00"

        if start_time == end_time:
            return {
                "ok": False,
                "message": "Start time and end time cannot be same"
            }

        conn = get_connection()
        cursor = conn.cursor()

        # Check overlap with other active shifts only
        # Same shift name old timing is ignored because it will be disabled
        overlap = is_shift_time_overlapping(
            cursor,
            start_time,
            end_time,
            exclude_shift_name=shift_name
        )

        if overlap:
            conn.close()
            return {
                "ok": False,
                "message": f"Shift timing overlaps with active shift: {overlap[1]}"
            }

        # Disable old active same shift name
        cursor.execute("""
            UPDATE SHIFT
            SET active = 0, 
                updated_at = datetime('now', 'localtime')
            WHERE LOWER(TRIM(shift_name)) = LOWER(TRIM(?))
            AND active = 1
        """, (shift_name,))

        # Insert new active shift timing
        cursor.execute("""
            INSERT INTO SHIFT (shift_name, start_time, end_time, active)
            VALUES (?, ?, ?, 1)
        """, (shift_name, start_time, end_time))

        conn.commit()
        conn.close()

        return {
            "ok": True,
            "message": "New shift timing created",
            "shift_name": shift_name,
            "start_time": start_time,
            "end_time": end_time
        }

    except Exception as e:
        return {
            "ok": False,
            "message": str(e)
        }

# ================= DATABASE INIT =================
def init_db():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS REPORT (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shift_name TEXT,
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
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS SHIFT (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shift_name TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
        """)
        cursor.execute("SELECT COUNT(*) FROM SHIFT")
        shift_count = cursor.fetchone()[0]
        if shift_count == 0:
            default_shifts = [
                ("Shift 1", "09:00:00", "13:00:00"),
                ("Shift 2", "13:00:00", "17:00:00"),
                ("Shift 3", "17:00:00", "21:00:00"),
            ]

            for shift_name, start_time, end_time in default_shifts:
                overlap = is_shift_time_overlapping(cursor, start_time, end_time)

                if overlap:
                    print(f"❌ Shift overlap found. Skipped: {shift_name}")
                    continue

                cursor.execute("""
                    INSERT INTO SHIFT (shift_name, start_time, end_time, active)
                    VALUES (?, ?, ?, ?)
                """, (shift_name, start_time, end_time, 1))
        cursor.execute("PRAGMA table_info(SHIFT)")
        shift_columns = [row[1] for row in cursor.fetchall()]

        if "active" not in shift_columns:
            cursor.execute("ALTER TABLE SHIFT ADD COLUMN active INTEGER DEFAULT 1")

        cursor.execute("PRAGMA table_info(REPORT)")
        columns = [row[1] for row in cursor.fetchall()]

        if "threshold" not in columns:
            cursor.execute("ALTER TABLE REPORT ADD COLUMN threshold TEXT")
        if "shift_name" not in columns:
            cursor.execute("ALTER TABLE REPORT ADD COLUMN shift_name TEXT")

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