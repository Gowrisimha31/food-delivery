# notifier.py
# The agent's "hands": the actions it is allowed to take on its own.
#   1. Post messages to a Slack channel
#   2. Open, update and close GitHub issues (tickets)
#
# These are SAFE actions: they tell people about a problem but never
# change the system itself. Risky actions (restart, rollback) are only
# ever suggested, for a human to approve.
#
# If Slack or GitHub isn't set up, or is down, the agent carries on
# without it. An alerting tool must never crash because of its alerts.

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")          # like "yourname/food-delivery"
GITHUB_API_URL = os.getenv("GITHUB_API_URL", "https://api.github.com")

TIMEOUT_SECONDS = 10
SEVERITY_ICONS = {"SEV1": "🔴", "SEV2": "🟠", "SEV3": "🟡"}


# ---------- Slack ----------

def send_slack(text):
    """Posts a message to Slack. Returns True if it worked."""
    if not SLACK_WEBHOOK_URL:
        print("   (Slack not configured, skipping)")
        return False
    try:
        response = httpx.post(SLACK_WEBHOOK_URL, json={"text": text}, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        print("   📣 Posted to Slack")
        return True
    except Exception as error:
        print(f"   ⚠️ Slack failed: {type(error).__name__}: {str(error)[:120]}")
        return False


def slack_alert(evidence):
    """The FIRST message: sent immediately, before the AI has finished."""
    lines = [f"🚨 *Incident detected* in food-app"]
    lines += [f"• {p}" for p in evidence["problems"]]
    failing = [name for name, ep in evidence["health"]["endpoints"].items()
               if ep["server_errors"] > 0 or ep["p95_latency_ms"] > 1000]
    if failing:
        lines.append(f"Affected: {', '.join(failing)}")
    if evidence["top_errors"]:
        top = evidence["top_errors"][0]
        lines.append(f"Top error: `{top['error'][:120]}` ({top['count']}x)")
    lines.append("_🤖 AI diagnosis in progress..._")
    return send_slack("\n".join(lines))


def slack_diagnosis(diagnosis, source, issue_url=None):
    """The SECOND message: the AI's diagnosis and recommended actions."""
    d = diagnosis
    lines = [
        f"{SEVERITY_ICONS[d['severity']]} *{d['severity']}: {d['title']}*",
        f"*Category:* {d['category']}  ·  *Runbook:* {d['runbook']}  ·  *Confidence:* {d['confidence']:.0%}",
        f"*Root cause:* {d['root_cause']}",
        "*Recommended actions:*",
    ]
    for a in d["recommended_actions"]:
        flag = "  ⚠️ _needs human approval_" if a["requires_approval"] else ""
        lines.append(f"• {a['action']}{flag}")
    if issue_url:
        lines.append(f"*Ticket:* {issue_url}")
    lines.append(f"_Diagnosed by {source}_")
    return send_slack("\n".join(lines))


def slack_resolved(title, minutes, issue_url=None):
    """The LAST message: the incident is over."""
    text = f"✅ *Resolved:* {title}\nDuration: {minutes} min"
    if issue_url:
        text += f"\nTicket closed: {issue_url}"
    return send_slack(text)


# ---------- GitHub issues ----------

def _github_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
    }


def _github_ready():
    if not (GITHUB_TOKEN and GITHUB_REPO):
        print("   (GitHub not configured, skipping)")
        return False
    return True


def issue_body(evidence, diagnosis, source):
    """Writes the ticket, in Markdown, so a human can pick it up and act."""
    d = diagnosis
    actions = "\n".join(
        f"- [ ] {a['action']}" + (" ⚠️ **needs approval**" if a["requires_approval"] else "")
        for a in d["recommended_actions"]
    )
    evidence_list = "\n".join(f"- {e}" for e in d["evidence"])
    endpoints = "\n".join(
        f"| `{name}` | {ep['requests']} | {ep['server_errors']} | {ep['p95_latency_ms']} ms |"
        for name, ep in evidence["health"]["endpoints"].items()
    )
    errors = "\n".join(f"- `{e['error'][:200]}` ({e['count']}x)" for e in evidence["top_errors"]) or "- none"
    deploys = "\n".join(
        f"- {x['time'][:19]} · {x['message']} · version {x['version']}"
        for x in evidence["recent_deployments"]
    ) or "- none in the last 10 minutes"

    return f"""## {d['severity']}: {d['title']}

**Detected:** {evidence['detected_at'][:19]} UTC
**Category:** `{d['category']}` · **Runbook:** {d['runbook']} · **Confidence:** {d['confidence']:.0%}

### Summary
{d['summary']}

### Likely root cause
{d['root_cause']}

### Evidence
{evidence_list}

### Recommended actions
{actions}

<details><summary>Raw detector data</summary>

**Problems detected:** {'; '.join(evidence['problems'])}

| Endpoint | Requests | 5xx | p95 |
|---|---|---|---|
{endpoints}

**Top errors**
{errors}

**Recent deployments**
{deploys}
</details>

---
_Opened automatically by the incident agent. Diagnosed by {source}._
"""


def create_issue(evidence, diagnosis, source):
    """Opens a ticket. Returns (issue number, link), or (None, None)."""
    if not _github_ready():
        return None, None
    try:
        response = httpx.post(
            f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/issues",
            headers=_github_headers(),
            json={
                "title": f"[{diagnosis['severity']}] {diagnosis['title']}",
                "body": issue_body(evidence, diagnosis, source),
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        issue = response.json()
        print(f"   🎫 Opened GitHub issue #{issue['number']}: {issue['html_url']}")
        return issue["number"], issue["html_url"]
    except Exception as error:
        print(f"   ⚠️ GitHub failed: {type(error).__name__}: {str(error)[:120]}")
        return None, None


def close_issue(number, minutes):
    """Adds a 'resolved' comment and closes the ticket."""
    if not number or not _github_ready():
        return False
    try:
        base = f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/issues/{number}"
        httpx.post(f"{base}/comments", headers=_github_headers(), timeout=TIMEOUT_SECONDS,
                   json={"body": f"✅ The app has been healthy again for 3 checks in a row. "
                                 f"Incident lasted {minutes} min. Closing automatically. "
                                 f"Please add a short write-up of what was done."}
                   ).raise_for_status()
        httpx.patch(base, headers=_github_headers(), timeout=TIMEOUT_SECONDS,
                    json={"state": "closed", "state_reason": "completed"}).raise_for_status()
        print(f"   🎫 Closed GitHub issue #{number}")
        return True
    except Exception as error:
        print(f"   ⚠️ GitHub close failed: {type(error).__name__}: {str(error)[:120]}")
        return False