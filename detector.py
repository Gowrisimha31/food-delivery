# detector.py
# Part A of the AI agent: the "smoke detector".
# Run it in a THIRD terminal. Every few seconds it reads the newest lines
# of logs/app.log, measures the app's health, and raises an alarm when
# something looks wrong. It then gathers the evidence an engineer
# (or the AI, in Part B) would need to diagnose the problem.
#
# No AI is used here. Just counting and simple rules.

import json
import os
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

LOG_FILE = "logs/app.log"
INCIDENT_FOLDER = "incidents"

CHECK_EVERY_SECONDS = 5     # how often to check health
WINDOW_SECONDS = 30         # look at the last 30 seconds of activity

# The rules. If any of these are broken, something is wrong.
RULES = {
    "max_server_error_rate": 0.03,  # more than 3% of requests failing with 5xx
    "min_server_errors": 3,         # ...and at least 3 of them (ignore one-offs)
    "max_p95_latency_ms": 1000,     # the slowest 5% of requests take over 1 second
    "min_requests_expected": 3,     # fewer than this in the window = app has gone quiet
}


# ---------- Reading the log file ----------

class LogReader:
    """Reads only the NEW lines added to the log since last time.

    Made robust for reading a file while another program is writing it:
      - counts position in bytes (reliable on every operating system)
      - only uses COMPLETE lines; a half-written last line is kept and
        finished on the next read, instead of being lost
      - if the file is briefly locked (e.g. by OneDrive or antivirus),
        it just tries again on the next check instead of crashing
    """

    def __init__(self, path):
        self.path = path
        # Start from the end of the file: we only care about what happens next
        self.position = os.path.getsize(path) if os.path.exists(path) else 0
        self.unfinished = b""   # a half-written line, waiting for its end

    def read_new_lines(self):
        try:
            if not os.path.exists(self.path):
                return []
            if os.path.getsize(self.path) < self.position:
                # The log file was rotated (started fresh): read it from the top
                self.position, self.unfinished = 0, b""
            with open(self.path, "rb") as f:
                f.seek(self.position)
                data = f.read()
                self.position = f.tell()
        except OSError:
            return []   # file busy right now; try again next check

        # Split off any half-written last line and keep it for next time
        data = self.unfinished + data
        complete, _, self.unfinished = data.rpartition(b"\n")

        entries = []
        for raw in complete.splitlines():
            try:
                entry = json.loads(raw.decode("utf-8"))
                entry["_time"] = datetime.fromisoformat(entry["timestamp"])
                entries.append(entry)
            except (json.JSONDecodeError, UnicodeDecodeError, KeyError, ValueError):
                pass  # skip anything that isn't a proper log line
        return entries


# ---------- Measuring health ----------

def percentile(values, pct):
    if not values:
        return 0
    values = sorted(values)
    index = min(len(values) - 1, int(len(values) * pct / 100))
    return values[index]


def short_error(entry):
    """Turns a long error into one short line, e.g. 'KeyError: 3'."""
    error = entry.get("error", "")
    if error:
        return error.strip().splitlines()[-1][:200]
    return entry.get("message", "")


def measure_health(entries):
    # Lines that describe a finished request have a "status" and "path"
    requests = [e for e in entries if "status" in e and "path" in e]
    server_errors = [r for r in requests if r["status"] >= 500]
    client_errors = [r for r in requests if 400 <= r["status"] < 500]
    latencies = [r.get("duration_ms", 0) for r in requests]

    # Break the numbers down per endpoint, e.g. "POST /orders"
    endpoints = {}
    for r in requests:
        name = f'{r.get("method", "?")} {r["path"]}'
        # Treat /orders/5/track and /orders/9/track as the same endpoint
        name = "/".join("{id}" if part.isdigit() else part for part in name.split("/"))
        ep = endpoints.setdefault(name, {"requests": 0, "server_errors": 0, "latencies": []})
        ep["requests"] += 1
        ep["latencies"].append(r.get("duration_ms", 0))
        if r["status"] >= 500:
            ep["server_errors"] += 1
    for ep in endpoints.values():
        ep["p95_latency_ms"] = percentile(ep.pop("latencies"), 95)

    return {
        "requests": len(requests),
        "server_errors": len(server_errors),
        "client_errors": len(client_errors),
        "server_error_rate": round(len(server_errors) / len(requests), 3) if requests else 0,
        "p50_latency_ms": percentile(latencies, 50),
        "p95_latency_ms": percentile(latencies, 95),
        "endpoints": endpoints,
    }


def check_rules(health):
    """Returns a list of reasons something looks wrong (empty = healthy)."""
    problems = []
    if (health["server_error_rate"] > RULES["max_server_error_rate"]
            and health["server_errors"] >= RULES["min_server_errors"]):
        problems.append(f'High server error rate: {health["server_error_rate"]:.0%} '
                        f'({health["server_errors"]} of {health["requests"]} requests)')
    if health["p95_latency_ms"] > RULES["max_p95_latency_ms"]:
        problems.append(f'High latency: p95 is {health["p95_latency_ms"]} ms')
    if health["requests"] < RULES["min_requests_expected"]:
        problems.append(f'Traffic dropped: only {health["requests"]} requests in {WINDOW_SECONDS}s')
    return problems


# ---------- Gathering evidence ----------

def gather_evidence(window, history, health, problems):
    """Collects everything needed to diagnose the problem."""
    # Error lines that explain WHAT went wrong. We skip plain summary lines
    # like "POST /orders -> 503", which only repeat the status code.
    errors = [e for e in window
              if e.get("level") == "ERROR" and ("error" in e or "status" not in e)]
    error_counts = Counter(short_error(e) for e in errors)

    # Deployments in the last 10 minutes ("what changed recently?")
    ten_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
    deployments = [
        {"time": e["timestamp"], "message": e["message"],
         "version": e.get("version"), "change": e.get("change")}
        for e in history
        if e["message"] in ("Deployment completed", "Rollback completed")
        and e["_time"] >= ten_minutes_ago
    ]

    # A few complete error lines, so the details aren't lost
    samples = [{k: v for k, v in e.items() if not k.startswith("_")} for e in errors[-3:]]
    for s in samples:
        if "error" in s:
            s["error"] = s["error"][-600:]  # keep the end of long tracebacks

    return {
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "window_seconds": WINDOW_SECONDS,
        "problems": problems,
        "health": health,
        "top_errors": [{"error": msg, "count": n} for msg, n in error_counts.most_common(5)],
        "recent_deployments": deployments,
        "sample_error_logs": samples,
    }


def save_incident(evidence):
    os.makedirs(INCIDENT_FOLDER, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(INCIDENT_FOLDER, f"incident_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)
    return path


# ---------- Printing ----------

def print_status(health, problems):
    now = datetime.now().strftime("%H:%M:%S")
    state = "🔴 UNHEALTHY" if problems else "🟢 healthy  "
    print(f'{now}  {state}  requests={health["requests"]:<4} '
          f'5xx={health["server_error_rate"]:.0%}  p95={health["p95_latency_ms"]} ms')


def print_incident(evidence, path):
    print("\n" + "=" * 70)
    print("🚨 INCIDENT DETECTED")
    for p in evidence["problems"]:
        print(f"   • {p}")
    print("\n   Endpoints in the last", WINDOW_SECONDS, "seconds:")
    for name, ep in evidence["health"]["endpoints"].items():
        print(f'     {name:<28} requests={ep["requests"]:<4} '
              f'5xx={ep["server_errors"]:<4} p95={ep["p95_latency_ms"]} ms')
    if evidence["top_errors"]:
        print("\n   Most common errors:")
        for e in evidence["top_errors"]:
            print(f'     {e["count"]}x  {e["error"]}')
    if evidence["recent_deployments"]:
        print("\n   Recent deployments:")
        for d in evidence["recent_deployments"]:
            print(f'     {d["time"][11:19]}  {d["message"]}  version={d["version"]}')
    print(f"\n   Evidence saved to {path}")
    print("=" * 70 + "\n")


# ---------- The main loop ----------

def main():
    print(f"Watching {LOG_FILE}. Checking every {CHECK_EVERY_SECONDS}s, "
          f"looking at the last {WINDOW_SECONDS}s. Press Ctrl + C to stop.\n")
    reader = LogReader(LOG_FILE)
    history = []           # all log entries from the last 10 minutes
    incident_open = False  # are we in the middle of an incident?
    healthy_checks = 0     # how many healthy checks in a row
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

            # Wait for the window to fill before judging the app
            if time.time() - started < WINDOW_SECONDS:
                print(f'{datetime.now().strftime("%H:%M:%S")}  ⏳ warming up...  '
                      f'requests so far={health["requests"]}')
                continue

            print_status(health, problems)

            if problems and not incident_open:
                incident_open = True
                healthy_checks = 0
                evidence = gather_evidence(window, history, health, problems)
                path = save_incident(evidence)
                print_incident(evidence, path)
            elif problems:
                healthy_checks = 0   # still broken; don't raise a duplicate alarm
            elif incident_open:
                healthy_checks += 1
                if healthy_checks >= 3:
                    incident_open = False
                    print("\n✅ RESOLVED: the app has been healthy for 3 checks in a row.\n")
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()