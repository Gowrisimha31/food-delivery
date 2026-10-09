# score.py
# Step 9, part 2: SCORE the agent on the labelled test set.
#
# For every case collected by evaluate.py, it asks both the simple rules
# and the AI for a diagnosis, compares each with the correct answer,
# and writes a report to eval/report.md.
#
# Run:  python score.py           (rules + AI)
#       python score.py --no-ai   (rules only, no AI calls)

import glob
import json
import statistics
import sys
import time
from collections import defaultdict
import diagnoser

CASES_FOLDER = "eval/cases"
REPORT_FILE = "eval/report.md"
RESULTS_FILE = "eval/results.json"
PAUSE_BETWEEN_AI_CALLS = 4   # seconds, to stay under the free tier's rate limit


def load_cases():
    cases = []
    for path in sorted(glob.glob(f"{CASES_FOLDER}/case_*.json")):
        with open(path, encoding="utf-8") as f:
            cases.append(json.load(f))
    return cases


def percent(part, whole):
    return f"{part / whole:.0%}" if whole else "n/a"


def main():
    use_ai = "--no-ai" not in sys.argv and diagnoser.AI_PROVIDER == "gemini" and diagnoser.GEMINI_API_KEY
    cases = load_cases()
    if not cases:
        print("No cases found. Run evaluate.py first.")
        return
    print(f"Scoring {len(cases)} cases ({'rules + AI' if use_ai else 'rules only'})...\n")

    results = []
    for case in cases:
        row = {k: case[k] for k in ("case", "scenario", "expected_category", "expected_severity",
                                    "detected", "seconds_to_detect")}
        if case["detected"] and case["expected_category"]:
            ev = case["evidence"]

            rules = diagnoser.diagnose_with_rules(ev).model_dump()
            row["rules_category"] = rules["category"]
            row["rules_severity"] = rules["severity"]

            if use_ai:
                started = time.time()
                diagnosis, source = diagnoser.diagnose(ev)
                row["ai_seconds"] = round(time.time() - started, 1)
                row["ai_source"] = source
                row["ai_answered"] = source.startswith("gemini")
                row["ai_category"] = diagnosis["category"]
                row["ai_severity"] = diagnosis["severity"]
                row["ai_title"] = diagnosis["title"]
                row["ai_confidence"] = diagnosis["confidence"]
                mark = "✅" if row["ai_category"] == row["expected_category"] else "❌"
                note = "" if row["ai_answered"] else "  (AI unavailable, used rules)"
                print(f"  case {case['case']:>3}  {case['scenario']:<28} AI: {row['ai_category']:<26} {mark}{note}")
                time.sleep(PAUSE_BETWEEN_AI_CALLS)
            else:
                mark = "✅" if row["rules_category"] == row["expected_category"] else "❌"
                print(f"  case {case['case']:>3}  {case['scenario']:<28} rules: {row['rules_category']:<26} {mark}")
        results.append(row)

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    report = build_report(results, use_ai)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    print("\n" + report)
    print(f"Saved to {REPORT_FILE}")


def build_report(results, use_ai):
    faults = [r for r in results if r["expected_category"]]
    quiet = [r for r in results if not r["expected_category"]]
    detected = [r for r in faults if r["detected"]]
    times = [r["seconds_to_detect"] for r in detected]
    false_alarms = [r for r in quiet if r["detected"]]
    diagnosed = [r for r in detected if "rules_category" in r]

    lines = ["# Incident Agent: Evaluation Report", "",
             f"**Rounds:** {len(results)}  ({len(faults)} with a fault, {len(quiet)} with no fault)", "",
             "## 1. Detection", "",
             "| Metric | Result |", "|---|---|",
             f"| Faults detected | {len(detected)}/{len(faults)} ({percent(len(detected), len(faults))}) |",
             f"| False alarms (no-fault rounds) | {len(false_alarms)}/{len(quiet)} |"]
    if times:
        lines += [f"| Mean time to detect (MTTD) | {statistics.mean(times):.1f}s |",
                  f"| Median / slowest | {statistics.median(times):.1f}s / {max(times):.1f}s |"]

    lines += ["", "**Time to detect by scenario**", "", "| Scenario | Detected | Mean time |", "|---|---|---|"]
    by_scenario = defaultdict(list)
    for r in faults:
        by_scenario[r["scenario"]].append(r)
    for name, rows in sorted(by_scenario.items()):
        t = [r["seconds_to_detect"] for r in rows if r["detected"]]
        lines.append(f"| {name} | {len(t)}/{len(rows)} | {statistics.mean(t):.1f}s |" if t
                     else f"| {name} | 0/{len(rows)} | - |")

    lines += ["", "## 2. Diagnosis accuracy", ""]
    rules_ok = sum(r["rules_category"] == r["expected_category"] for r in diagnosed)
    rules_sev = sum(r["rules_severity"] == r["expected_severity"] for r in diagnosed)
    header = "| | Rules |" + (" AI |" if use_ai else "")
    lines += [header, "|---|---|" + ("---|" if use_ai else "")]

    if use_ai:
        ai_rows = [r for r in diagnosed if r.get("ai_answered")]
        ai_ok = sum(r["ai_category"] == r["expected_category"] for r in ai_rows)
        ai_sev = sum(r["ai_severity"] == r["expected_severity"] for r in ai_rows)
        lines += [
            f"| Correct category | {rules_ok}/{len(diagnosed)} ({percent(rules_ok, len(diagnosed))}) "
            f"| {ai_ok}/{len(ai_rows)} ({percent(ai_ok, len(ai_rows))}) |",
            f"| Correct severity | {rules_sev}/{len(diagnosed)} ({percent(rules_sev, len(diagnosed))}) "
            f"| {ai_sev}/{len(ai_rows)} ({percent(ai_sev, len(ai_rows))}) |",
        ]
        ai_times = [r["ai_seconds"] for r in ai_rows]
        fallbacks = len(diagnosed) - len(ai_rows)
        lines += ["", f"- **AI answered** {len(ai_rows)}/{len(diagnosed)} cases "
                      f"({fallbacks} fell back to rules because the AI was unavailable; "
                      "those are excluded from the AI column)."]
        if ai_times:
            lines.append(f"- **Mean AI diagnosis time:** {statistics.mean(ai_times):.1f}s")
    else:
        lines += [f"| Correct category | {rules_ok}/{len(diagnosed)} ({percent(rules_ok, len(diagnosed))}) |",
                  f"| Correct severity | {rules_sev}/{len(diagnosed)} ({percent(rules_sev, len(diagnosed))}) |"]

    lines += ["", "**Accuracy by scenario**", "",
              "| Scenario | Rules |" + (" AI |" if use_ai else ""),
              "|---|---|" + ("---|" if use_ai else "")]
    by_scenario = defaultdict(list)
    for r in diagnosed:
        by_scenario[r["scenario"]].append(r)
    for name, rows in sorted(by_scenario.items()):
        ok = sum(r["rules_category"] == r["expected_category"] for r in rows)
        line = f"| {name} | {ok}/{len(rows)} |"
        if use_ai:
            ai_rows = [r for r in rows if r.get("ai_answered")]
            ai_ok = sum(r["ai_category"] == r["expected_category"] for r in ai_rows)
            line += f" {ai_ok}/{len(ai_rows)} |"
        lines.append(line)

    mistakes = [r for r in diagnosed if r.get("ai_answered") and r["ai_category"] != r["expected_category"]]
    rule_mistakes = [r for r in diagnosed if r["rules_category"] != r["expected_category"]]
    lines += ["", "## 3. Mistakes (for error analysis)", ""]
    if use_ai:
        lines += ["**AI mistakes**", ""]
        lines += [f"- Case {r['case']} ({r['scenario']}): expected `{r['expected_category']}`, "
                  f"got `{r['ai_category']}`: \"{r['ai_title']}\"" for r in mistakes] or ["- none"]
        lines.append("")
    lines += ["**Rules mistakes**", ""]
    lines += [f"- Case {r['case']} ({r['scenario']}): expected `{r['expected_category']}`, "
              f"got `{r['rules_category']}`" for r in rule_mistakes] or ["- none"]
    missed = [r for r in faults if not r["detected"]]
    if missed or false_alarms:
        lines += ["", "**Detection mistakes**", ""]
        lines += [f"- Case {r['case']} ({r['scenario']}): not detected" for r in missed]
        lines += [f"- Case {r['case']}: false alarm with no fault" for r in false_alarms]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()