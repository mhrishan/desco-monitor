
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import json
import os
import threading
import time
from datetime import datetime, timedelta, time as dt_time
import requests
import re
import urllib3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import gspread
from oauth2client.service_account import ServiceAccountCredentials
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    from backports.zoneinfo import ZoneInfo

app = Flask(__name__)
app.secret_key = 'desco_monitor_secret_key_2024'

# Global variables for monitoring control
monitoring_thread = None
monitoring_active = False
last_run_status = {"status": "Not started", "last_run": None, "next_run": None}

# Configuration file path
CONFIG_FILE = 'config.json'

# Default configuration
DEFAULT_CONFIG = {
    "account_number": "33009712",
    "meter_number": "661120244943",
    "system_type": "tkdes",
    "google_sheet_name": "meter_bill",
    "google_sheet_url": "https://docs.google.com/spreadsheets/d/1GmafuiwpmGwKnk22tARy-9Jja1n9wSty556iLSR9lro/edit?usp=sharing",
    "service_account_file": "service_account.json",
    "email_from": "marufrishan@gmail.com",
    "email_to": "marufhasanrishan@gmail.com",
    "email_password": "qvzqubqvwshrwzex",
    "email_subject": "⚠️ DESCO Balance & Daily Usage",
    "timezone": "Asia/Dhaka",
    "run_hour": 17,
    "run_minute": 50
}

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return DEFAULT_CONFIG.copy()

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def get_google_sheet(config):
    try:
        scope = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(config['service_account_file'], scope)
        client = gspread.authorize(creds)
        sheet = client.open(config['google_sheet_name']).sheet1
        return sheet
    except Exception as e:
        print(f"❌ Error connecting to Google Sheets: {e}")
        return None

def send_email(balance, config):
    msg = MIMEMultipart()
    msg["From"] = config['email_from']
    msg["To"] = config['email_to']
    msg["Subject"] = config['email_subject']

    body = f"""
    <html>
      <body>
        <p>Hello,</p>
        <p>Account No: <b>{config['account_number']}</b><br>
           Meter No: <b>{config['meter_number']}</b><br>
           System Type: <b>{config['system_type'].upper()}</b>
        </p>
        <p>Your current DESCO prepaid balance is 
           <span style="color: red; font-weight: bold;">{balance:.2f} BDT</span>.
        </p>
        <p>Daily consumption has been updated in the Google Sheet.<br>
           👉 <a href="{config['google_sheet_url']}" target="_blank">View Google Sheet</a>
        </p>
        <p>Regards,<br>DESCO Monitor Script</p>
      </body>
    </html>
    """
    msg.attach(MIMEText(body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(config['email_from'], config['email_password'])
            server.send_message(msg)
            print("📧 Email notification sent with Google Sheet link.")
        return True
    except Exception as e:
        print("❌ Failed to send email:", e)
        return False

def get_balance(config):
    balance_url = f"https://prepaid.desco.org.bd/api/{config['system_type']}/customer/getBalance?accountNo={config['account_number']}&meterNo={config['meter_number']}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Referer": "https://prepaid.desco.org.bd/"
    }

    try:
        response = requests.get(balance_url, headers=headers, verify=False)
        if response.status_code == 200:
            match = re.search(r'"balance"\s*:\s*([\d.]+)', response.text)
            if match:
                return float(match.group(1))
        print("⚠️ Balance pattern not found.")
    except Exception as e:
        print("❌ Error fetching balance:", e)
    return None

def update_google_sheet(date_str, current_balance, config):
    sheet = get_google_sheet(config)
    if not sheet:
        return False

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
            return True

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
        return True
    except Exception as e:
        print("❌ Failed to update Google Sheet:", e)
        return False

def get_last_consumption_from_sheet(config):
    sheet = get_google_sheet(config)
    if not sheet:
        return 0.0

    try:
        all_data = sheet.get_all_values()
        if len(all_data) > 1:  # Skip header
            last_row = all_data[-1]
            if len(last_row) >= 2:
                return float(last_row[1])  # Daily consumption column
    except Exception as e:
        print(f"❌ Error reading consumption from Google Sheet: {e}")
    return 0.0

def daily_check(config):
    global last_run_status
    
    current_balance = get_balance(config)
    
    if current_balance is not None:
        # Use yesterday's date instead of today's
        date_str = (datetime.now() - timedelta(days=1)).strftime("%d-%m-%Y")
        sheet_updated = update_google_sheet(date_str, current_balance, config)
        email_sent = send_email(current_balance, config)
        
        # Get the actual last consumption from Google Sheet
        last_consumption = get_last_consumption_from_sheet(config)
        
        last_run_status = {
            "status": "Success" if (sheet_updated and email_sent) else "Partial failure",
            "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "balance": current_balance,
            "consumption": last_consumption
        }
    else:
        last_run_status = {
            "status": "Failed to fetch balance",
            "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

def monitoring_worker():
    global monitoring_active, last_run_status
    
    config = load_config()
    timezone = ZoneInfo(config['timezone'])
    run_time = dt_time(hour=config['run_hour'], minute=config['run_minute'])
    last_run_date = None
    
    print(f"⏱️ Scheduler active — running daily at {run_time.strftime('%H:%M')}")
    
    while monitoring_active:
        now = datetime.now(tz=timezone)
        
        # Calculate next run time
        next_run = datetime.combine(now.date(), run_time, tzinfo=timezone)
        if now.time() > run_time:
            next_run += timedelta(days=1)
        
        last_run_status["next_run"] = next_run.strftime("%Y-%m-%d %H:%M:%S")
        
        if now.time().hour == run_time.hour and now.time().minute == run_time.minute:
            if last_run_date != now.date():
                print("🔔 Running DESCO daily task...")
                daily_check(config)
                last_run_date = now.date()
                time.sleep(60)
        time.sleep(20)

@app.route('/')
def index():
    config = load_config()
    # Always get the latest consumption from Google Sheet for display
    if 'consumption' not in last_run_status or last_run_status['consumption'] is None:
        last_run_status['consumption'] = get_last_consumption_from_sheet(config)
    return render_template('index.html', config=config, status=last_run_status, monitoring_active=monitoring_active)

@app.route('/config', methods=['GET', 'POST'])
def config_page():
    if request.method == 'POST':
        config = {
            'account_number': request.form['account_number'],
            'meter_number': request.form['meter_number'],
            'system_type': request.form['system_type'],
            'google_sheet_name': request.form['google_sheet_name'],
            'google_sheet_url': request.form['google_sheet_url'],
            'service_account_file': request.form['service_account_file'],
            'email_from': request.form['email_from'],
            'email_to': request.form['email_to'],
            'email_password': request.form['email_password'],
            'email_subject': request.form['email_subject'],
            'timezone': request.form['timezone'],
            'run_hour': int(request.form['run_hour']),
            'run_minute': int(request.form['run_minute'])
        }
        save_config(config)
        flash('Configuration saved successfully!', 'success')
        return redirect(url_for('index'))
    
    config = load_config()
    return render_template('config.html', config=config)

@app.route('/start_monitoring')
def start_monitoring():
    global monitoring_thread, monitoring_active
    
    if not monitoring_active:
        monitoring_active = True
        monitoring_thread = threading.Thread(target=monitoring_worker, daemon=True)
        monitoring_thread.start()
        flash('Monitoring started successfully!', 'success')
    else:
        flash('Monitoring is already running!', 'warning')
    
    return redirect(url_for('index'))

@app.route('/stop_monitoring')
def stop_monitoring():
    global monitoring_active
    
    if monitoring_active:
        monitoring_active = False
        flash('Monitoring stopped successfully!', 'info')
    else:
        flash('Monitoring is not running!', 'warning')
    
    return redirect(url_for('index'))

@app.route('/run_now')
def run_now():
    config = load_config()
    daily_check(config)
    flash('Manual check completed!', 'success')
    return redirect(url_for('index'))

@app.route('/status')
def status():
    config = load_config()
    # Update consumption from Google Sheet before returning status
    current_status = last_run_status.copy()
    current_status['consumption'] = get_last_consumption_from_sheet(config)
    
    return jsonify({
        'monitoring_active': monitoring_active,
        'last_run_status': current_status
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
