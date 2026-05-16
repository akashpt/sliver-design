import json
from classes.database import fetch_one


class ReportManager:
    def __init__(self, db_path=None):
        pass

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
            total_row = fetch_one("""
                SELECT COUNT(*)
                FROM REPORT
            """)

            total = total_row[0] if total_row else 0
            good_row = fetch_one("""
                SELECT COUNT(*)
                FROM REPORT
                WHERE LOWER(COALESCE(result, '')) = 'good'
            """)

            good = good_row[0] if good_row else 0

            defective_row = fetch_one("""
                SELECT COUNT(*)
                FROM REPORT
                WHERE LOWER(COALESCE(result, '')) != 'good'
            """)

            defective = defective_row[0] if defective_row else 0

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