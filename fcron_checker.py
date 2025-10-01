#!/usr/bin/env python3
import subprocess
import requests
import datetime
import re
import os

# ---------------- CONFIG ----------------
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/XXXXXXXXXXXX"
CHECK_MINUTES = 10  # Look this far back in logs

# ---------------- HELPERS ----------------
def send_discord_report(results):
    """Send a single embed summarizing all jobs."""
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
                "title": "🕒 Fcron Monitor Report",
                "description": f"Checked the last **{CHECK_MINUTES} minutes** of logs.",
                "color": color,
                "fields": fields,
                "footer": {
                    "text": f"fcron-monitor • {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                }
            }
        ]
    }

    try:
        requests.post(DISCORD_WEBHOOK, json=data, timeout=10)
    except Exception as e:
        print(f"[ERROR] Discord send failed: {e}")

def get_fcron_logs(minutes=10):
    """Fetch recent fcron logs from systemd or fallback to /var/log/fcron.log."""
    logs = []
    # Try journalctl first
    try:
        output = subprocess.check_output(
            ["journalctl", "-u", "fcron.service", "--since", f"{minutes}m ago", "--no-pager"],
            text=True,
            stderr=subprocess.DEVNULL
        )
        logs.extend(output.splitlines())
    except Exception:
        pass

    # Fallback to log file
    log_file = "/var/log/fcron.log"
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", errors="ignore") as f:
                logs.extend(f.readlines()[-500:])  # tail last 500 lines
        except Exception:
            pass

    return logs

def parse_fcron_logs(logs):
    """Parse fcron logs into job events."""
    events = []
    for line in logs:
        if re.search(r"fcron", line, re.IGNORECASE):
            events.append(line)
    return events

def main():
    logs = get_fcron_logs(CHECK_MINUTES)
    events = parse_fcron_logs(logs)
    results = []

    if not events:
        results.append({
            "job": "No fcron activity",
            "status": "missing",
            "message": "No fcron jobs ran in the last interval."
        })
    else:
        for e in events:
            job_match = re.search(r'CMD \((.*?)\)', e)
            job_name = job_match.group(1) if job_match else "Unknown job"
            if "EXIT STATUS" in e:
                exit_match = re.search(r'EXIT STATUS \((\d+)\)', e)
                if exit_match and exit_match.group(1) != "0":
                    results.append({
                        "job": job_name,
                        "status": "failed",
                        "message": f"```\n{e}\n```"
                    })
                else:
                    results.append({
                        "job": job_name,
                        "status": "success",
                        "message": "Ran successfully."
                    })
            else:
                # If no EXIT STATUS, assume ran successfully
                results.append({
                    "job": job_name,
                    "status": "success",
                    "message": "Ran successfully."
                })

    send_discord_report(results)

if __name__ == "__main__":
    main()
