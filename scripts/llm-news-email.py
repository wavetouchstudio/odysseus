#!/usr/bin/env python3
"""LLM News Email — finds the most recent LLM News Digest research report
and emails it to the configured address via the Odysseus internal API.

Runs as a chained task after 'LLM News Digest' completes.
Requires ODYSSEUS_INTERNAL_TOKEN set in .env (loaded at Odysseus startup).
"""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
RESEARCH_DIR = Path(__file__).parent.parent / "data" / "deep_research"
ODYSSEUS_URL = "http://localhost:7000"
INTERNAL_TOKEN = "ody-internal-llmnews-script-runner"
OWNER = "deadlyjrmint@gmail.com"
EMAIL_TO = "wavetouchstudio@gmail.com"
RESEARCH_TASK_NAME = "LLM News Digest"

# ── Helpers ───────────────────────────────────────────────────────────────────

def find_latest_research() -> dict | None:
    """Find the most recently completed LLM News Digest research JSON."""
    best = None
    best_ts = 0.0
    for p in RESEARCH_DIR.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("owner") != OWNER:
            continue
        if d.get("status") not in ("done", "complete", "success"):
            continue
        # Only pick up LLM news reports (query contains our keywords)
        query = (d.get("query") or "").lower()
        if "llm" not in query and "open source" not in query and "open-source" not in query:
            continue
        ts = d.get("completed_at") or d.get("started_at") or 0
        if ts > best_ts:
            best_ts = ts
            best = d
    return best


def report_to_html(report_md: str, query: str, sources: list) -> str:
    """Wrap markdown report in basic HTML email body."""
    # Convert markdown headings and bullets to rough HTML
    lines = []
    for line in report_md.splitlines():
        if line.startswith("### "):
            lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("- ") or line.startswith("* "):
            lines.append(f"<li>{line[2:]}</li>")
        elif line.startswith("**") and line.endswith("**"):
            lines.append(f"<p><strong>{line[2:-2]}</strong></p>")
        elif line.strip() == "":
            lines.append("<br>")
        else:
            # Bold inline
            converted = line.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
            lines.append(f"<p>{converted}</p>")

    source_html = ""
    if sources:
        source_links = "".join(
            f'<li><a href="{s.get("url", "#")}">{s.get("title") or s.get("url", "source")}</a></li>'
            for s in sources[:20]
        )
        source_html = f"<hr><h3>Sources</h3><ul>{source_links}</ul>"

    now_str = datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M UTC")
    return f"""
<html><body style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; color: #222;">
<div style="background:#1a1a2e;color:#e0e0e0;padding:16px 24px;border-radius:8px 8px 0 0;">
  <h2 style="margin:0;font-size:18px;">LLM News Digest</h2>
  <p style="margin:4px 0 0;font-size:13px;opacity:0.7;">{now_str}</p>
</div>
<div style="padding:24px;border:1px solid #ddd;border-top:none;border-radius:0 0 8px 8px;">
{"".join(lines)}
{source_html}
</div>
</body></html>
"""


def send_via_odysseus(subject: str, body_html: str, body_text: str) -> bool:
    """POST to Odysseus /api/codex/emails/send using internal auth."""
    payload = json.dumps({
        "to": EMAIL_TO,
        "subject": subject,
        "body": body_text,
        "body_html": body_html,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{ODYSSEUS_URL}/api/codex/emails/send",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Odysseus-Internal-Token": INTERNAL_TOKEN,
            "X-Odysseus-Owner": OWNER,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
            print(f"  Email sent: {resp}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"  [error] HTTP {e.code}: {body[:300]}", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"  [error] Send failed: {exc}", file=sys.stderr)
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[llm-news-email] {datetime.now().isoformat()}")

    research = find_latest_research()
    if not research:
        print("[llm-news-email] No recent LLM News Digest found.", file=sys.stderr)
        sys.exit(1)

    report_md = research.get("result") or ""
    sources = research.get("sources") or []
    query = research.get("query") or "LLM News Digest"
    completed_at = research.get("completed_at") or 0

    if not report_md:
        print("[llm-news-email] Research result is empty.", file=sys.stderr)
        sys.exit(1)

    # Build subject with date
    date_str = datetime.now(timezone.utc).strftime("%b %d")
    subject = f"LLM News Digest — {date_str}"

    body_html = report_to_html(report_md, query, sources)
    body_text = report_md[:8000]  # plain text fallback

    print(f"  Report: {len(report_md)} chars, {len(sources)} sources")
    print(f"  Sending to: {EMAIL_TO}")

    ok = send_via_odysseus(subject, body_html, body_text)
    if ok:
        print("[llm-news-email] Done.")
    else:
        print("[llm-news-email] Email send failed.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
