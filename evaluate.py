# evaluate.py
# Step 9, part 1: COLLECT a labelled test set.
#
# Runs many rounds of "break the app on purpose, see if it's detected".
# Because WE choose which switch to flip, we know the correct answer for
# every round. Each round's evidence is saved with that answer (a "label")
# into eval/cases/, so the diagnosis can be scored afterwards by score.py.
#
# Before running:  Terminal 1 = app, Terminal 2 = traffic.py,
#                  STOP agent.py (so 30 test incidents don't spam Slack/GitHub).
# Run:             python evaluate.py 20      (20 rounds; default 20)

import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
import httpx
from detector import (LogReader, LOG_FILE, CHECK_EVERY_SECONDS, WINDOW_SECONDS,
                      measure_health, check_rules, gather_evidence)

APP_URL = "http://127.0.0.1:8000"
CASES_FOLDER = "eval/cases"
DETECT_TIMEOUT_SECONDS = 60      # if not detected within this, count as missed
HEALTHY_TIMEOUT_SECONDS = 120    # max wait for the app to recover between rounds

# Each scenario: which switches to flip, and the CORRECT answer (the label).
SCENARIOS = {
    "payment_gateway_down": {
        "switches": ["payment_gateway_down"],
        "expected_category": "payment_gateway_outage", "expected_severity": "SEV1"},
    "slow_database": {
        "switches": ["slow_database"],
        "expected_category": "database_slow", "expected_severity": "SEV2"},
    "db_connections_exhausted": {
        "switches": ["db_connections_exhausted"],
        "expected_category": "db_connection_exhaustion", "expected_severity": "SEV1"},
    "bad_deploy": {
        "switches": ["bad_deploy"],
        "expected_category": "bad_deployment", "expected_severity": "SEV2"},
    # The trap: a deploy + rollback happens first, THEN the gateway fails.
    # The correct answer is the gateway, not the deployment.
    "trap_rollback_then_gateway": {
        "setup": ["bad_deploy"],
        "switches": ["payment_gateway_down"],
        "expected_category": "payment_gateway_outage", "expected_severity": "SEV1"},
    # Nothing is broken. The detector should NOT raise an alarm.
    "no_fault": {
        "switches": [],
        "expected_category": None, "expected_severity": None},
}

client = httpx.Client(base_url=APP_URL, timeout=10)
reader = LogReader(LOG_FILE)
history = []


def chaos(action, name=""):
    path = "/chaos/reset" if action == "reset" else f"/chaos/{name}/{action}"
    client.post(path).raise_for_status()


def current_window():
    """Reads new log lines and returns (window, health, problems)."""
    global history
    now = datetime.now(timezone.utc)
    history += reader.read_new_lines()
    history = [e for e in history if e["_time"] >= now - timedelta(minutes=10)]
    window = [e for e in history if e["_time"] >= now - timedelta(seconds=WINDOW_SECONDS)]
    health = measure_health(window)
    return window, health, check_rules(health)


def wait_until_healthy():
    """Waits until the app has looked healthy for 3 checks in a row."""
    healthy_in_a_row, waited = 0, 0
    while healthy_in_a_row < 3:
        if waited > HEALTHY_TIMEOUT_SECONDS:
            raise RuntimeError("App didn't recover. Is traffic.py running?")
        time.sleep(CHECK_EVERY_SECONDS)
        waited += CHECK_EVERY_SECONDS
        _, _, problems = current_window()
        healthy_in_a_row = 0 if problems else healthy_in_a_row + 1


def run_round(number, name):
    scenario = SCENARIOS[name]
    chaos("reset")
    print(f"\n[{number}] {name}: waiting for the app to be healthy...")
    wait_until_healthy()

    # The trap's setup: a deployment, then a rollback, then recovery
    for switch in scenario.get("setup", []):
        print(f"     setup: {switch} on for 10s, then rolled back")
        chaos("on", switch)
        time.sleep(10)
        chaos("off", switch)
        wait_until_healthy()

    # Break it, and start the stopwatch
    for switch in scenario["switches"]:
        chaos("on", switch)
    started = time.time()

    detected, evidence = False, None
    while time.time() - started < DETECT_TIMEOUT_SECONDS:
        time.sleep(CHECK_EVERY_SECONDS)
        window, health, problems = current_window()
        if problems:
            detected = True
            evidence = gather_evidence(window, history, health, problems)
            break
    seconds_to_detect = round(time.time() - started, 1) if detected else None
    chaos("reset")

    if scenario["expected_category"] is None:
        outcome = "FALSE ALARM ❌" if detected else "correctly quiet ✅"
    else:
        outcome = f"detected in {seconds_to_detect}s ✅" if detected else "MISSED ❌"
    print(f"     {outcome}")

    return {
        "case": number,
        "scenario": name,
        "expected_category": scenario["expected_category"],
        "expected_severity": scenario["expected_severity"],
        "detected": detected,
        "seconds_to_detect": seconds_to_detect,
        "evidence": evidence,
    }


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    os.makedirs(CASES_FOLDER, exist_ok=True)

    # A balanced, shuffled list: go through every scenario once (in a random
    # order) before repeating any, so each appears about equally often
    names = []
    while len(names) < rounds:
        batch = list(SCENARIOS)
        random.shuffle(batch)
        names += batch
    names = names[:rounds]

    print(f"Running {rounds} rounds (about {rounds * 1.5:.0f} minutes). "
          "Keep app + traffic running. Ctrl + C to stop early.")
    start_number = len(os.listdir(CASES_FOLDER)) + 1
    try:
        for i, name in enumerate(names):
            number = start_number + i
            case = run_round(number, name)
            with open(f"{CASES_FOLDER}/case_{number:03d}.json", "w", encoding="utf-8") as f:
                json.dump(case, f, indent=2)
    except KeyboardInterrupt:
        print("\nStopped early. Cases collected so far are saved.")
    finally:
        try:
            chaos("reset")
        except Exception:
            pass
    print(f"\nDone. Cases are in {CASES_FOLDER}/. Now run:  python score.py")


if __name__ == "__main__":
    main()