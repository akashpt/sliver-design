import re
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QUrl, QEventLoop, QTimer
from PyQt5.QtWebEngineWidgets import QWebEnginePage

from path import (
    DB_FILE,
    SLIVER_PDF_PAGE,
    INVOICE_PDF,
    PREDICTION_IMAGES_DIR,
    IMG_DIR,
    TRAINING_SETTINGS_FILE,
    USER_CONFIG_FILE
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

    def _fetch_report_data(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        config_path = USER_CONFIG_FILE

        job_id = ""

        if Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                job_id = config.get("job_id", "").strip()

        print("PDF FILTER JOB_ID =", job_id)
        cur.execute("SELECT COUNT(*) FROM REPORT WHERE job_id = ?", (job_id,))
        print("ONLY JOB ROWS =", cur.fetchone()[0])

        cur.execute("""
            SELECT
                COUNT(*) AS inspected,
                SUM(CASE WHEN LOWER(COALESCE(result,'')) = 'good' THEN 1 ELSE 0 END) AS good,
                SUM(CASE WHEN LOWER(COALESCE(result,'')) IN ('defect','bad','strip missing') THEN 1 ELSE 0 END) AS defective,
                COALESCE(MAX(machine_no), '-') AS machine_no,
                ? AS job_id,
                COALESCE(MAX(threshold), '-') AS threshold,
                MIN(created_time) AS start_time,
                MAX(created_time) AS end_time
            FROM REPORT
            WHERE date(created_time) = date('now', 'localtime')
            AND job_id = ?
        """, (job_id, job_id))

        summary = cur.fetchone()
        print("PDF SUMMARY =", summary)

        cur.execute("""
            SELECT
                id,
                created_time,
                job_id,
                result,
                bad_strips,
                bad_strip_number,
                bad_image_path
            FROM REPORT
            WHERE date(created_time) = date('now', 'localtime')
            AND job_id = ?
            AND LOWER(COALESCE(result,'')) IN ('defect','bad','strip missing')
            ORDER BY datetime(created_time) DESC
            LIMIT 20
        """, (job_id,))

        defects = cur.fetchall()

        conn.close()
        return summary, defects

    def _replace_table(self, html, class_name, rows_html):
        pattern = rf'(<table class="{class_name}">)(.*?)(</table>)'
        return re.sub(pattern, rf'\1{rows_html}\3', html, flags=re.S)

    def build_html(self):
        html = Path(SLIVER_PDF_PAGE).read_text(encoding="utf-8")

        logo_path = self._file_uri(IMG_DIR / "logo" / "logo.png")
        html = html.replace('src="img/logo.png"', f'src="{logo_path}"')

        training = self._read_training_settings()
        summary, defects = self._fetch_report_data()

        inspected = summary[0] or 0
        good = summary[1] or 0
        defective = summary[2] or 0
        machine_no = summary[3] or "-"
        job_id = summary[4] or "-"
        threshold = summary[5] or "-"
        start_time = summary[6] or "-"
        end_time = summary[7] or "-"

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
        <tr><td>Counts</td><td>{count}</td></tr>
        <tr><td>Threshold</td><td>{threshold}</td></tr>
        <tr><td>Total Inspected</td><td>{inspected}</td></tr>
        <tr><td>Good</td><td>{good}</td></tr>
        <tr><td>Defective</td><td>{defective}</td></tr>
        <tr><td>Start Time</td><td>{start_time}</td></tr>
        <tr><td>End Time</td><td>{end_time}</td></tr>
        """

        breakdown_rows = f"""
        <tr><th style="width: 50%">Category</th><th>Count</th></tr>
        <tr><td><strong>Total Inspected</strong></td><td style="font-size: 15.5pt; font-weight: 700">{inspected}</td></tr>
        <tr><td>Good</td><td>{good}</td></tr>
        <tr><td>Defective</td><td>{defective}</td></tr>
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

    def generate_pdf(self):
        try:
            print("🔥 Invoice PDF generation started")
            # print("HTML Template:", SLIVER_PDF_PAGE)
            print("Output PDF:", INVOICE_PDF)
            # ✅ Always remove old PDF before generating new PDF
            pdf_path = Path(INVOICE_PDF)
            if pdf_path.exists():
                try:
                    pdf_path.unlink()
                    print("🗑 Old invoice PDF deleted")
                except Exception as e:
                    print("❌ Cannot delete old PDF:", e)
                    return False
                        

            html = self.build_html()

            # temp_html = Path(INVOICE_PDF).parent / "dynamic_sliver_invoice.html"
            # temp_html.write_text(html, encoding="utf-8")
            # print("Temp HTML:", temp_html)

            page = QWebEnginePage()
            loop = QEventLoop()
            result = {"ok": False}

            def save_pdf(pdf_data):
                try:
                    with open(INVOICE_PDF, "wb") as f:
                        f.write(bytes(pdf_data))

                    size = Path(INVOICE_PDF).stat().st_size
                    print("PDF size:", size)

                    result["ok"] = size > 0
                except Exception as e:
                    print("❌ save_pdf error:", e)

                if loop.isRunning():
                    loop.quit()

            def html_loaded(ok):
                print("HTML loaded:", ok)

                if not ok:
                    loop.quit()
                    return

                print("✅ Calling printToPdf bytes...")
                QTimer.singleShot(1000, lambda: page.printToPdf(save_pdf))

            def timeout():
                print("⚠️ PDF timeout reached")
                result["ok"] = False

                if loop.isRunning():
                    loop.quit()

            # def timeout():
            #     print("⚠️ PDF timeout reached")

            #     if Path(INVOICE_PDF).exists() and Path(INVOICE_PDF).stat().st_size > 0:
            #         print("✅ Existing PDF found")
            #         result["ok"] = True
            #         loop.quit()
            #         return
            #     else:
            #         print("❌ PDF not created")

            #     loop.quit()

            page.loadFinished.connect(html_loaded)
            # page.load(QUrl.fromLocalFile(str(temp_html.resolve())))
            base_url = QUrl.fromLocalFile(str(Path(SLIVER_PDF_PAGE).parent.resolve()) + "/")
            page.setHtml(html, base_url)

            QTimer.singleShot(20000, timeout)
            loop.exec_()

            return result["ok"]

        except Exception as e:
            print("❌ generate_pdf error:", e)
            return False