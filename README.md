# Meter Bill Scheduler — Render Deployment

This repo contains a Flask web app (`app.py`) and a daily scheduler script (`main.py`) to fetch DESCO balance/consumption and email a CSV report.

## What you get
- **Web UI (Flask)**: configure credentials at `/config`, view status, start/stop monitoring.
- **Daily Cron Job**: runs `main.py` independently of the web UI and emails the CSV report.

## Quick Start (Render)
1. **Create a GitHub repo** and push this folder.
2. **Render One-Click** (with `render.yaml`):
   - In Render, click **New + → Blueprint** and point to your GitHub repo.
   - This will provision **two services**:
     - `meterbillscheduler-web` (Flask app)
     - `meterbillscheduler-cron` (Cron Job running daily at 17:50 Asia/Dhaka by default)
3. **Set environment variables** for both services:
   - `ACCOUNT_NUMBER`, `METER_NUMBER`, `SYSTEM_TYPE`
   - `EMAIL_FROM`, `EMAIL_TO`, `EMAIL_PASSWORD`
   - Optional: `EMAIL_SUBJECT`, `CSV_FILE`
4. **Deploy**:
   - The web app will be live at a Render URL.
   - The cron service will run daily and send the email with the CSV attachment.

## Manual Setup (without `render.yaml`)
- Create a **Web Service**:
  - Build: `pip install -r requirements.txt`
  - Start: `gunicorn app:app`
  - Add the environment variables listed above.
- Create a **Cron Job**:
  - Schedule: e.g. `50 17 * * *` for 17:50 Dhaka time.
  - Build: `pip install -r requirements.txt`
  - Start: `python main.py`
  - Add the same environment variables.

## Notes
- **Secrets**: Do **not** hardcode credentials in code. Use Render **Environment Variables**.
- **CSV persistence**: Files written to disk are ephemeral on Render. The script emails the CSV each run (recommended). For long-term storage, use a database or Google Sheets.
- **Web monitoring thread**: The Flask app has an internal scheduler thread. On free plans, sleeping instances may pause it. The Cron Job ensures reliability.
- **Time zone**: The cron expression is interpreted per Render service settings; verify it's `Asia/Dhaka` and adjust schedule as needed.
