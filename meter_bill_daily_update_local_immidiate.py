import requests
import re
import urllib3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import csv
import os
from datetime import datetime, timedelta

# 🔧 USER CONFIGURATIONS

ACCOUNT_NUMBER = "33009712"
METER_NUMBER = "661120244943"
SYSTEM_TYPE = "tkdes"

BALANCE_URL = f"https://prepaid.desco.org.bd/api/{SYSTEM_TYPE}/customer/getBalance?accountNo={ACCOUNT_NUMBER}&meterNo={METER_NUMBER}"
CONSUMPTION_URL_TEMPLATE = f"https://prepaid.desco.org.bd/api/{SYSTEM_TYPE}/customer/getCustomerDailyConsumption?accountNo={ACCOUNT_NUMBER}&meterNo={METER_NUMBER}&dateFrom={{date}}&dateTo={{date}}"

EMAIL_FROM = "marufrishan@gmail.com"
EMAIL_TO = "marufhasanrishan@gmail.com"
EMAIL_PASSWORD = "qvzqubqvwshrwzex"
EMAIL_SUBJECT = "⚠️ DESCO Balance & Daily Usage"

CSV_FILE = "desco_consumption_log.csv"

RUN_IMMEDIATELY = True  # Set True to run once immediately and exit

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def send_email(balance, csv_file_path):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = EMAIL_SUBJECT

    body = f"""
    <html>
      <body>
        <p>Hello,</p>
        <p>Account No: <b>{ACCOUNT_NUMBER}</b><br>
           Meter No: <b>{METER_NUMBER}</b><br>
           System Type: <b>{SYSTEM_TYPE.upper()}</b>
        </p>
        <p>Your current DESCO prepaid balance is 
           <span style="color: red; font-weight: bold;">{balance:.2f} BDT</span>.
        </p>
        <p>Daily consumption has been updated in the attached file.<br>
           File Location (local): {os.path.abspath(csv_file_path)}
        </p>
        <p>Regards,<br>DESCO Monitor Script</p>
      </body>
    </html>
    """
    msg.attach(MIMEText(body, "html"))

    try:
        with open(csv_file_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={os.path.basename(csv_file_path)}")
            msg.attach(part)
    except Exception as e:
        print(f"❌ Failed to attach CSV file: {e}")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.send_message(msg)
            print("📧 Email notification sent with attachment.")
    except Exception as e:
        print("❌ Failed to send email:", e)


def get_balance():
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Referer": "https://prepaid.desco.org.bd/"
    }

    try:
        response = requests.get(BALANCE_URL, headers=headers, verify=False)
        if response.status_code == 200:
            match = re.search(r'"balance"\s*:\s*([\d.]+)', response.text)
            if match:
                return float(match.group(1))
        print("⚠️ Balance pattern not found.")
    except Exception as e:
        print("❌ Error fetching balance:", e)
    return None


def get_daily_consumption(target_date):
    date_str = target_date.strftime("%Y-%m-%d")
    url = CONSUMPTION_URL_TEMPLATE.format(date=date_str)
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    try:
        response = requests.get(url, headers=headers, verify=False)
        if response.status_code == 200:
            match = re.search(r'"consumedTaka"\s*:\s*([\d.]+)', response.text)
            if match:
                return float(match.group(1))
        print("⚠️ consumedTaka not found.")
    except Exception as e:
        print("❌ Error fetching consumption:", e)
    return None


def update_csv(date_str, consumed_taka, balance, file_path):
    rows = []
    file_exists = os.path.exists(file_path)

    if file_exists:
        with open(file_path, mode='r', newline='') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            rows = list(reader)

    updated = False
    for i, row in enumerate(rows):
        if row and row[0] == date_str:
            rows[i][2] = f"{balance:.2f}"
            updated = True
            break

    if not updated:
        rows.append([date_str, "0.00", f"{balance:.2f}"])

    rows.sort(key=lambda x: x[0])

    for i in range(len(rows)):
        if i == 0:
            rows[i][1] = "0.00"
        else:
            try:
                prev_balance = float(rows[i - 1][2])
                curr_balance = float(rows[i][2])
                diff = prev_balance - curr_balance
                rows[i][1] = f"{diff:.2f}"
            except:
                rows[i][1] = "0.00"

    with open(file_path, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "DailyConsumption(BDT)", "Balance(BDT)"])
        writer.writerows(rows)

    print(
        f"✅ CSV updated: {date_str} → {rows[-1][1]} BDT, Balance: {balance:.2f} BDT"
    )


def daily_check():
    balance = get_balance()
    prev_day = datetime.now() - timedelta(days=1)
    date_str = prev_day.strftime("%Y-%m-%d")
    consumed_taka = get_daily_consumption(prev_day)

    if balance is not None:
        if consumed_taka is None:
            consumed_taka = 0.0
        update_csv(date_str, consumed_taka, balance, CSV_FILE)
        send_email(balance, CSV_FILE)


if __name__ == "__main__":
    if RUN_IMMEDIATELY:
        print("🚀 Running DESCO monitor immediately.")
        daily_check()
