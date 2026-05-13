import json
import sqlite3
from path import DB_FILE


class ReportManager:
    def __init__(self, db_path=None):
        self.db_path = str(DB_FILE)

    def get_summary(self):
        """
        Returns:
        {
            "ok": True/False,
            "total": int,
            "good": int,
            "defective": int
        }
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Total inspected rows
            cursor.execute("SELECT COUNT(*) FROM REPORT")
            total = cursor.fetchone()[0] or 0

            # Good rows
            cursor.execute("""
                SELECT COUNT(*)
                FROM REPORT
                WHERE LOWER(COALESCE(result, '')) = 'good'
            """)
            good = cursor.fetchone()[0] or 0

            # Defective rows
            cursor.execute("""
                SELECT COUNT(*)
                FROM REPORT
                WHERE LOWER(COALESCE(result, '')) != 'good'
            """)
            defective = cursor.fetchone()[0] or 0

            conn.close()

            return {
                "ok": True,
                "total": total,
                "good": good,
                "defective": defective,
            }

        except Exception as e:
            print("❌ ReportManager.get_summary error:", e)
            return {
                "ok": False,
                "total": 0,
                "good": 0,
                "defective": 0,
                "message": str(e),
            }

    def get_summary_json(self):
        return json.dumps(self.get_summary())