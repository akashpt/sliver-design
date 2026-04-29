import re
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QUrl, QEventLoop, QTimer
from PyQt5.QtWebEngineWidgets import QWebEngineView
from path import (
    DB_FILE,
    REPORT_NEW,
    INVOICE_PDF,
    PREDICTION_IMAGES_DIR,
    IMG_DIR,
    TRAINING_SETTINGS_FILE,
    SETTINGS_FILE
)

class InvoicePDFGenerator:
    def __init__(self):
        self.db_path = str(DB_FILE)

    def _file_uri(self, path):
        path = Path(path)
        return path.resolve().as_uri() if path.exists() else ""

    def _read_training_settings(self):
        try:
            if Path(TRAINING_SETTINGS_FILE).exists():
                with open(TRAINING_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    # def _fetch_report_data(self):
    def _fetch_report_data(self, start_time=None, end_time=None):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        config_path = SETTINGS_FILE

        job_id = ""

        if Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                job_id = config.get("job_id", "").strip()

        print("PDF FILTER JOB_ID =", job_id)
        # 🔥 TIME FILTER LOGIC
        if start_time and end_time:
            date_condition = "created_time >= ? AND created_time < ?"
            time_params = (start_time, end_time)
        # else:
        #     date_condition = "date(created_time) = date('now', 'localtime')"
        #     time_params = ()
        #         cur.execute("SELECT COUNT(*) FROM REPORT WHERE job_id = ?", (job_id,))
        #         print("ONLY JOB ROWS =", cur.fetchone()[0])
        else:
            date_condition = "date(created_time) = date('now', 'localtime')"
            time_params = ()

        cur.execute("SELECT COUNT(*) FROM REPORT WHERE job_id = ?", (job_id,))
        print("ONLY JOB ROWS =", cur.fetchone()[0])

        cur.execute(f"""
            SELECT
                COUNT(*) AS inspected,
                SUM(CASE WHEN LOWER(COALESCE(result,'')) = 'good' THEN 1 ELSE 0 END) AS good,
                SUM(CASE WHEN LOWER(COALESCE(result,'')) IN ('defect','bad') THEN 1 ELSE 0 END) AS defective,
                SUM(CASE WHEN LOWER(COALESCE(result,'')) = 'strip missing' THEN 1 ELSE 0 END) AS missing,
                COALESCE(MAX(machine_no), '-') AS machine_no,
                ? AS job_id,
                COALESCE(MAX(threshold), '-') AS threshold,
                MIN(created_time) AS start_time,
                MAX(created_time) AS end_time
            FROM REPORT
            WHERE {date_condition}
            AND job_id = ?
        """, (job_id, *time_params, job_id))

        summary = cur.fetchone()
        print("PDF SUMMARY =", summary)

        cur.execute(f"""
            SELECT
                id,
                created_time,
                job_id,
                result,
                bad_strips,
                bad_strip_number,
                bad_image_path
            FROM REPORT
            WHERE {date_condition}
            AND job_id = ?
            AND LOWER(COALESCE(result,'')) IN ('defect','bad','strip missing')
            ORDER BY datetime(created_time) DESC
            LIMIT 20
        """,((*time_params, job_id)))

        defects = cur.fetchall()

        conn.close()
        return summary, defects

    def _replace_table(self, html, class_name, rows_html):
        pattern = rf'(<table class="{class_name}">)(.*?)(</table>)'
        return re.sub(pattern, rf'\1{rows_html}\3', html, flags=re.S)

    # def build_html(self):
    def build_html(self, start_time=None, end_time=None):
        html = Path(REPORT_NEW).read_text(encoding="utf-8")

        logo_path = self._file_uri(IMG_DIR / "logo" / "logo.png")
        html = re.sub(r'src=".*logo\.png"', f'src="{logo_path}"', html)

        training = self._read_training_settings()
        # summary, defects = self._fetch_report_data()
        summary, defects = self._fetch_report_data(start_time, end_time)

        inspected = summary[0] or 0
        good = summary[1] or 0
        defective = summary[2] or 0
        missing = summary[3] or 0
        machine_no = summary[4] or "-"
        job_id = summary[5] or "-"
        threshold = summary[6] or "-"
        start_time = summary[7] or "-"
        end_time = summary[8] or "-"

        today = datetime.now().strftime("%Y-%m-%d")
        generated = datetime.now().strftime("%d %B %Y %H:%M:%S")

        count = training.get("count", "-")
        yarn = training.get("yarn", "-")
        color = training.get("color", "-")

        summary_rows = f"""
        <tr><td>Date</td><td>{today}</td></tr>
        <tr><td>Machine Number</td><td>{machine_no}</td></tr>
        <tr><td>Material Name</td><td>{job_id}</td></tr>
        <tr><td>Yarn</td><td>{yarn}</td></tr>
        <tr><td>Color</td><td>{color}</td></tr>
        <tr><td>Start Time</td><td>{start_time}</td></tr>
        <tr><td>End Time</td><td>{end_time}</td></tr>
        """
        breakdown_rows = f"""
        <tr>
        <th>Total Inspected</th>
        <th>Good</th>
        <th>Strip Defect</th>
        <th>Strip Missing</th>
        </tr>
        <tr>
        <td>{inspected}</td>
        <td>{good}</td>
        <td>{defective}</td>
        <td>{missing}</td>
        </tr>
        """

        defect_rows = ""
        if defects:
            for i, row in enumerate(defects, start=1):
                _id, created_time, job, result, bad_strips, bad_strip_number, img_path = row

                image_uri = ""
                if img_path:
                    full_img = PREDICTION_IMAGES_DIR / img_path
                    image_uri = self._file_uri(full_img)

                defect_type = f"{result}"
                if bad_strip_number:
                    defect_type += f" | Strip: {bad_strip_number}"

                img_tag = f'<img src="{image_uri}" alt="Defect" />' if image_uri else "-"

                defect_rows += f"""
                <tr>
                  <td>{i}</td>
                  <td>{created_time}</td>
                  <td>{job}</td>
                  <td>{img_tag}</td>
                  <td>{defect_type}</td>
                </tr>
                """
        else:
            defect_rows = """
            <tr>
              <td colspan="5">No defects found today</td>
            </tr>
            """

        html = self._replace_table(html, "summary-table", summary_rows)
        html = self._replace_table(html, "breakdown-table", breakdown_rows)

        html = re.sub(
            r'(<tbody>)(.*?)(</tbody>)',
            rf'\1{defect_rows}\3',
            html,
            flags=re.S
        )

        html = re.sub(
            r'Generated:.*?TEXA Yarn',
            f'Generated: {generated} &nbsp;&nbsp; | &nbsp;&nbsp; TEXA Yarn',
            html,
            flags=re.S
        )

        return html

    # def generate_pdf(self, parent=None, finished_callback=None):
    def generate_pdf(self, parent=None, finished_callback=None, start_time=None, end_time=None):
        try:
            print("🔥 Invoice PDF generation started")
            print("Output PDF:", INVOICE_PDF)

            # html = self.build_html()
            html = self.build_html(start_time, end_time)

            pdf_path = Path(INVOICE_PDF)
            pdf_path.parent.mkdir(parents=True, exist_ok=True)

            # from path import TEMPLATES_DIR
            temp_html = REPORT_NEW
            temp_html.write_text(html, encoding="utf-8")    
            print("Temp HTML:", temp_html)

            self.view = QWebEngineView(parent)
            self.page = self.view.page()
            self.finished_callback = finished_callback

            def pdf_finished(file_path, success):
                print("PDF finished:", file_path, success)

                ok = False
                if success and pdf_path.exists() and pdf_path.stat().st_size > 0:
                    print("✅ New PDF size:", pdf_path.stat().st_size)
                    ok = True
                else:
                    print("❌ PDF not created correctly")

                if self.finished_callback:
                    self.finished_callback(ok)

                self.view.deleteLater()

            def html_loaded(ok):
                print("HTML loaded:", ok)

                if not ok:
                    if self.finished_callback:
                        self.finished_callback(False)
                    return

                with open(pdf_path, "wb") as f:
                    f.write(b"")

                print("🧹 Old PDF content cleared")
                print("✅ Calling printToPdf...")

                QTimer.singleShot(1000, lambda: self.page.printToPdf(str(pdf_path)))

            self.page.loadFinished.connect(html_loaded)
            self.page.pdfPrintingFinished.connect(pdf_finished)

            self.view.load(QUrl.fromLocalFile(str(temp_html.resolve())))

        except Exception as e:
            print("❌ generate_pdf error:", e)
            if finished_callback:
                finished_callback(False)







        # <tr><td>Counts</td><td>{count}</td></tr>
        # <tr><td>Threshold</td><td>{threshold}</td></tr>
        # <tr><td>Total Inspected</td><td>{inspected}</td></tr>
        # <tr><td>Good</td><td>{good}</td></tr>
        # <tr><td>Defective</td><td>{defective}</td></tr>
        # SUM(CASE WHEN LOWER(COALESCE(result,'')) IN ('defect','bad','strip missing') THEN 1 ELSE 0 END) AS defective,