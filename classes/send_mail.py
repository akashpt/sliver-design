import smtplib
import os
import time
from path import EMAIL_PAGE
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders


def load_email_template():
    with open(EMAIL_PAGE, "r", encoding="utf-8") as file:
        return file.read()

def send_email_with_attachments(attachments_path,machine_no="",frame_no="",material="",color="",defect_time="",retries=3,wait_seconds=5):
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SENDER_EMAIL = "divyadharsinimurugesan@gmail.com"
    SENDER_PASSWORD = "jbfg kjeh wtld uajn"
    # RECIPIENT_EMAILS = [
    #     "sniyas8675@gmail.com",
    #     "manojg0795@gmail.com",
    #     "nishanthchakkra@gmail.com"
    # ]
    RECIPIENT_EMAILS = [
        "divyadharsinimurugesan@gmail.com",
        "aarthysm05@gmail.com"
        
        
    ]
    # from datetime import datetime
# "sniyas8675@gmail.com","kalaiselvi29778@gmail.com"
    # timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

    
    # subject = " Bad Images Report"
    # # body = f"Dear Team,\n\nPlease find attached the defect report and bad images report for review.\n\nDrawing Frame No: 3 \nCurrently running metiral: Radha\nMetiral Color: Yellow\n\nBest Regards,\nYour Automated System\n\nDate Time :{timestamp}\n\nDefect images attached below:"
    # html_template = load_email_template()

    # body = html_template.format(
    #     frame_no=3,
    #     material="Radha",
    #     color="Yellow",
    #     datetime=timestamp
    # )

    subject = "Bad Images Report"

    html_template = load_email_template()

    body = html_template.format(
        machine_no=machine_no if machine_no != "" else "-",
        frame_no=frame_no if frame_no != "" else "-",
        material=material if material else "-",
        color=color if color else "-",
        datetime=defect_time if defect_time else "-"
    )
    # attachments = ["Lycra_Defect_Report.pdf", "bad_images_report.pdf"]
    attachments = [attachments_path]

    for attempt in range(retries):
        try:
            msg = MIMEMultipart()
            msg['From'] = SENDER_EMAIL
            msg['To'] = ", ".join(RECIPIENT_EMAILS)
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'html'))

            for file in attachments:
                if os.path.exists(file):
                    with open(file, "rb") as attachment:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(attachment.read())
                        encoders.encode_base64(part)
                        part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(file)}")
                        msg.attach(part)

            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAILS, msg.as_string())
            server.quit()

            time.sleep(3)  # Ensure email delivery flush
            print("✅ Email sent successfully with attachments!")
            return True  # Exit function if success

        except Exception as e:
            print(f"❌ Attempt {attempt+1} failed: {e}")
            time.sleep(wait_seconds)  # Wait before retry

    print("❌ All attempts failed. Email not sent.")
    return False  # All retries failed

def delete_bad_images(folder_path):
    if os.path.exists(folder_path):
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            try:
                if os.path.isfile(file_path) and filename.endswith((".jpg", ".png",".tiff")):
                    os.remove(file_path)
                    print(f"🗑 Deleted: {filename}")
            except Exception as e:
                print(f"❌ Error deleting {filename}: {e}")
        print("✅ All bad images deleted successfully.")
    else:
        print("⚠️ Warning: 'bad_images' folder does not exist.")

# ✅ Trigger only if email is sent
#send_email_with_attachments()
#delete_bad_images("bad_images")
def send_last_generated_pdf():
    from path import INVOICE_PDF
    from datetime import datetime

    pdf_path = str(INVOICE_PDF)

    if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) == 0:
        print("❌ Last generated PDF not found or empty:", pdf_path)
        return False

    return send_email_with_attachments(
        pdf_path,
        machine_no="M1",
        frame_no="-",
        material="Hourly Invoice Report",
        color="-",
        defect_time=datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    )
