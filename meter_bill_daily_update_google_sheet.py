import requests
import re
import urllib3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 🔧 USER CONFIGURATIONS

ACCOUNT_NUMBER = "33009712"
METER_NUMBER = "661120244943"
SYSTEM_TYPE = "tkdes"
GOOGLE_SHEET_NAME = "meter_bill"
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1GmafuiwpmGwKnk22tARy-9Jja1n9wSty556iLSR9lro/edit?usp=sharing"

BALANCE_URL = f"https://prepaid.desco.org.bd/api/{SYSTEM_TYPE}/customer/getBalance?accountNo={ACCOUNT_NUMBER}&meterNo={METER_NUMBER}"

EMAIL_FROM = "marufrishan@gmail.com"
EMAIL_TO = "marufhasanrishan@gmail.com"
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_SUBJECT = "⚠️ DESCO Balance & Daily Usage"

# 🛡 Disable warnings for insecure HTTPS
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 🔐 Google Sheets authorization
SERVICE_ACCOUNT_FILE = "service_account.json"
scope = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
client = gspread.authorize(creds)
sheet = client.open(GOOGLE_SHEET_NAME).sheet1


def send_email(balance):
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
        <p>Daily consumption has been updated in the Google Sheet.<br>
           👉 <a href="{GOOGLE_SHEET_URL}" target="_blank">View Google Sheet</a>
        </p>
        <p>Regards,<br>DESCO Monitor Script</p>
      </body>
    </html>
    """
    msg.attach(MIMEText(body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.send_message(msg)
            print("📧 Email notification sent with Google Sheet link.")
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


def update_google_sheet(date_str, current_balance):
    try:
        # Get all rows
        all_data = sheet.get_all_values()
        if not all_data or all_data[0][0].lower() != "date":
            sheet.insert_row(["Date", "DailyConsumption(BDT)", "Balance(BDT)"], 1)
            all_data = sheet.get_all_values()

        # Check if yesterday's date already exists
        dates = [row[0] for row in all_data[1:]]  # Exclude header
        if date_str in dates:
            print("🟡 Yesterday's date already exists in sheet. Skipping update.")
            return

        # Get last valid numeric balance
        prev_balance = None
        for row in reversed(all_data[1:]):  # Skip header
            if len(row) >= 3:
                try:
                    prev_balance = float(row[2])
                    break
                except ValueError:
                    continue  # Skip invalid row

        if prev_balance is None:
            consumed = 0.00
            print("⚠️ No previous valid balance found. Setting consumed = 0.00")
        else:
            consumed = round(prev_balance - current_balance, 2)

        # Append new row
        sheet.append_row([date_str, f"{consumed:.2f}", f"{current_balance:.2f}"])
        print("✅ Google Sheet updated:", [date_str, f"{consumed:.2f}", f"{current_balance:.2f}"])
    except Exception as e:
        print("❌ Failed to update Google Sheet:", e)


def daily_check():
    current_balance = get_balance()
    if current_balance is not None:
        # Use yesterday’s date instead of today’s
        date_str = (datetime.now() - timedelta(days=1)).strftime("%d-%m-%Y")
        update_google_sheet(date_str, current_balance)
        send_email(current_balance)


if __name__ == "__main__":
    print("🚀 Running DESCO monitor immediately.")
    daily_check()

