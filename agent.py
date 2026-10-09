# agent.py
# The full incident agent:
#   detect (Part A) -> alert -> diagnose (Part B) -> ticket -> resolve
# Run this in the third terminal.

import json
import time
from datetime import datetime, timedelta, timezone
from detector import (LogReader, LOG_FILE, CHECK_EVERY_SECONDS, WINDOW_SECONDS,
                      measure_health, check_rules, gather_evidence, save_incident,
                      print_status, print_incident)
from diagnoser import diagnose
import notifier


def print_diagnosis(d, source):
    icons = {"SEV1": "🔴", "SEV2": "🟠", "SEV3": "🟡"}
    print(f'🤖 DIAGNOSIS  (by {source})')
    print(f'   {icons[d["severity"]]} {d["severity"]}: {d["title"]}')
    print(f'   Category:    {d["category"]}   (runbook {d["runbook"]}, confidence {d["confidence"]:.0%})')
    print(f'   Root cause:  {d["root_cause"]}')
    print(f'   Summary:     {d["summary"]}')
    print("   Evidence:")
    for e in d["evidence"][:5]:
        print(f"     - {e}")
    print("   Recommended actions:")
    for a in d["recommended_actions"]:
        flag = "  ⚠️ needs human approval" if a["requires_approval"] else ""
        print(f'     • {a["action"]}{flag}')


def handle_new_incident(window, history, health, problems):
    """Everything the agent does when a new incident starts."""
    evidence = gather_evidence(window, history, health, problems)
    path = save_incident(evidence)
    print_incident(evidence, path)

    # 1. Alert humans IMMEDIATELY, with the basic facts. Don't wait for the AI.
    notifier.slack_alert(evidence)

    # 2. Diagnose
    print("🤖 Diagnosing...")
    started = time.time()
    diagnosis, source = diagnose(evidence)
    evidence["diagnosis"] = diagnosis
    evidence["diagnosed_by"] = source
    evidence["diagnosis_seconds"] = round(time.time() - started, 1)
    print_diagnosis(diagnosis, source)

    # 3. Open a ticket, then share the diagnosis (with the ticket link)
    number, url = notifier.create_issue(evidence, diagnosis, source)
    notifier.slack_diagnosis(diagnosis, source, url)
    evidence["github_issue"] = url
    print("=" * 70 + "\n")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)

    return {"path": path, "title": diagnosis["title"], "issue_number": number,
            "issue_url": url, "started": time.time()}


def handle_resolved(incident):
    """Everything the agent does when the incident is over."""
    minutes = round((time.time() - incident["started"]) / 60, 1)
    print(f"\n✅ RESOLVED: {incident['title']} (lasted {minutes} min)")
    notifier.slack_resolved(incident["title"], minutes, incident["issue_url"])
    notifier.close_issue(incident["issue_number"], minutes)

    with open(incident["path"], "r", encoding="utf-8") as f:
        record = json.load(f)
    record["resolved_at"] = datetime.now(timezone.utc).isoformat()
    record["duration_minutes"] = minutes
    with open(incident["path"], "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    print()


def main():
    print(f"🤖 Incident agent watching {LOG_FILE}. Press Ctrl + C to stop.\n")
    reader = LogReader(LOG_FILE)
    history = []
    incident = None        # the incident currently open, if any
    healthy_checks = 0
    started = time.time()

    try:
        while True:
            time.sleep(CHECK_EVERY_SECONDS)
            now = datetime.now(timezone.utc)
            history += reader.read_new_lines()
            history = [e for e in history if e["_time"] >= now - timedelta(minutes=10)]
            window = [e for e in history if e["_time"] >= now - timedelta(seconds=WINDOW_SECONDS)]

            health = measure_health(window)
            problems = check_rules(health)

            if time.time() - started < WINDOW_SECONDS:
                print(f'{datetime.now().strftime("%H:%M:%S")}  ⏳ warming up...  '
                      f'requests so far={health["requests"]}')
                continue

            print_status(health, problems)

            if problems and incident is None:
                healthy_checks = 0
                incident = handle_new_incident(window, history, health, problems)
            elif problems:
                healthy_checks = 0
            elif incident is not None:
                healthy_checks += 1
                if healthy_checks >= 3:
                    handle_resolved(incident)
                    incident = None
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()