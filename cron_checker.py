#!/usr/bin/env python3
import subprocess
import requests
import datetime
import re
import os
import shutil

# ---------------- CONFIG ----------------
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/XXXXXXXXXXXXXXXXXXXXXXXXXx"
CHECK_MINUTES = 10  # Look this far back in logs

# ---------------- HELPERS ----------------
def send_discord_report(results):
    """Send a single embed summarizing all jobs."""
    # Decide embed color
    if any(r["status"] == "failed" for r in results):
        color = 0xE74C3C  # red
    elif any(r["status"] == "missing" for r in results):
        color = 0xE67E22  # orange
    else:
        color = 0x2ECC71  # green

    fields = []
    for r in results:
        status_icon = "✅" if r["status"] == "success" else "⚠️" if r["status"] == "missing" else "❌"
        fields.append({
            "name": f"{status_icon} {r['job']}",
            "value": r["message"],
            "inline": False
        })

    data = {
        "embeds": [
            {
                "title": "🕒 Cron/Fcron Monitor Report",
                "description": f"Checked the last **{CHECK_MINUTES} minutes** of logs.",
                "color": color,
                "fields": fields,
                "footer": {
                    "text": f"cron-monitor • {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                }
            }
        ]
    }

    try:
        requests.post(DISCORD_WEBHOOK, json=data, timeout=10)
    except Exception as e:
        print(f"[ERROR] Discord send failed: {e}")

def get_crontab():
    """Get current user's crontab entries if crontab exists."""
    if shutil.which("crontab") is None:
        print("[WARN] 'crontab' command not found, skipping user crontab fetch.")
        return []
    try:
        output = subprocess.check_output(["crontab", "-l"], text=True)
        jobs = []
        for line in output.splitlines():
            if line.strip() and not line.startswith("#"):
                jobs.append(line.strip())
        return jobs
    except subprocess.CalledProcessError:
        # no crontab entries
        return []

def detect_scheduler():
    """Detect whether cron, crond, or fcron is active."""
    services = ["cron.service", "crond.service", "fcron.service"]
    for svc in services:
        try:
            subprocess.check_output(["systemctl", "is-active", "--quiet", svc])
            return svc
        except subprocess.CalledProcessError:
            continue
    return None

def get_logs(minutes=10):
    """Fetch recent logs from systemd or fallback to log files."""
    svc = detect_scheduler()
    since = f"{minutes}m ago"

    if svc:
        try:
            output = subprocess.check_output(
                ["journalctl", "-u", svc, "--since", since, "--no-pager"],
                text=True,
                stderr=subprocess.DEVNULL
            )
            return output.splitlines()
        except Exception:
            pass

    # fallback to common log files
    log_files = ["/var/log/syslog", "/var/log/cron", "/var/log/fcron.log"]
    logs = []
    for lf in log_files:
        if os.path.exists(lf):
            try:
                with open(lf, "r", errors="ignore") as f:
                    logs.extend(f.readlines()[-500:])  # tail last 500 lines
            except Exception:
                pass
    return logs

def parse_logs(logs):
    """Parse logs into job run events."""
    events = []
    for line in logs:
        if re.search(r"(CRON|cron|fcron)", line):
            events.append(line)
    return events

def main():
    jobs = get_crontab()
    logs = get_logs(CHECK_MINUTES)
    events = parse_logs(logs)

    results = []

    if not jobs:
        results.append({
            "job": "No user crontab",
            "status": "missing",
            "message": "No crontab entries found or 'crontab' command missing."
        })

    for job in jobs:
        job_cmd = " ".join(job.split()[5:])  # extract command
        ran = any(job_cmd in e for e in events)

        if ran:
            results.append({
                "job": job_cmd,
                "status": "success",
                "message": f"Ran successfully in last {CHECK_MINUTES} minutes."
            })
        else:
            results.append({
                "job": job_cmd,
                "status": "missing",
                "message": "Did **not run** (but scheduled)."
            })

    # Check failures from logs
    for e in events:
        if "EXIT STATUS" in e and not re.search(r"EXIT STATUS \(0\)", e):
            results.append({
                "job": "Failure detected",
                "status": "failed",
                "message": f"```\n{e}\n```"
            })

    send_discord_report(results)

if __name__ == "__main__":
    main()
