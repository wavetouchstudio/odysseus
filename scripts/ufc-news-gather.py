#!/usr/bin/env python3
"""UFC News Enricher — fetches live Reddit/Wikipedia/YouTube data and injects
it into the 'UFC News Digest' research task prompt before Odysseus fires it.

Schedule: 5 minutes before the Odysseus research task (via Odysseus run_script action).
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import threading
import time
import random
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Windows consoles default to cp1252, which can't encode emoji that show up in
# video titles or fighter names with diacritics (e.g. "Ankalaev vs. Ćirković").
# An UnicodeEncodeError here would crash the script before it reaches the DB
# update step, silently breaking the scheduled chain. Force UTF-8 instead.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Config ────────────────────────────────────────────────────────────────────
TASK_NAME = "UFC News Digest"
DB_PATH = Path(__file__).parent.parent / "data" / "app.db"
USER_AGENT = "OdysseusUFCDigest/1.0 (scheduled research enricher)"

SUBREDDITS = [
    "MMA",
    "ufc",
    "Sherdog",
]

# channel_id: display_name
YOUTUBE_CHANNELS = {
    "UCIhQvpinmS8Eq6PrQ021DKQ": "THE MMA GURU",
    "UC_1TBgZ5FuGSdRlrrnyJU7w": "Daniel Cormier",
    "UCRlvF4jIeBWqXJDGNXfPyVw": "Chael Sonnen",
    "UCVOdVp54jLrFhRUm4S29HeA": "Ariel Helwani (Uncrowned)",
    "UCO4AcsPKEkIqDmbeiZLfd1A": "ESPN MMA",
    "UCxQfUu6vIJGZDODSwhr0m9w": "MMA Junkie",
    "UCzXkqrWMWa29miU2QqN6Odg": "Helen Yee Sports",
    "UCvgfXK4nTYKudb0rFR6noLA": "UFC (official)",
    "UCNrEHIf8QmKK-cAag4YxIXQ": "Submission Radio",
    "UC4f1JueVgo5t9HSmobCRPug": "MMA Fighting",
}

# Fetch transcript for videos published within this many hours
TRANSCRIPT_WINDOW_HOURS = 48
# Max words of transcript to include per video
TRANSCRIPT_MAX_WORDS = 500
# Max videos to fetch transcripts for (to keep runtime reasonable)
TRANSCRIPT_MAX_VIDEOS = 5

# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch(url: str, timeout: int = 10) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


# ── Reddit ────────────────────────────────────────────────────────────────────

def fetch_reddit_hot(subreddit: str, limit: int = 15) -> list[dict]:
    url = f"https://www.reddit.com/r/{subreddit}/hot/.rss?limit={limit}"
    try:
        raw = _fetch(url)
        root = ET.fromstring(raw)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        posts = []
        skip = {s.lower() for s in SUBREDDITS} | {subreddit.lower()}
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            link_el = entry.find("atom:link", ns)
            title = _strip_html(title_el.text or "") if title_el is not None else ""
            link = (link_el.attrib.get("href") or "") if link_el is not None else ""
            if title and title.lower() not in skip:
                posts.append({"title": title, "url": link})
        return posts
    except Exception as exc:
        print(f"  [warn] r/{subreddit} RSS failed: {exc}", file=sys.stderr)
        return []


# ── UFC event schedule (Wikipedia) ──────────────────────────────────────────

def _clean_wikitext(text: str) -> str:
    text = re.sub(r"\{\{dts\|(\d+)\|([A-Za-z]+)\|(\d+)\}\}", r"\2 \3, \1", text)
    text = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"<ref.*", "", text, flags=re.DOTALL)
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    return text.strip()


def fetch_ufc_schedule(limit: int = 10) -> list[dict]:
    """Upcoming UFC events from Wikipedia's 'List of UFC events' Scheduled
    events table — event name, date, venue, location. No API key needed."""
    try:
        url = (
            "https://en.wikipedia.org/w/api.php?action=parse"
            "&page=List_of_UFC_events&prop=wikitext&section=3&format=json"
        )
        raw = _fetch(url, timeout=12)
        data = json.loads(raw)
        wikitext = data["parse"]["wikitext"]["*"]

        rows: list[list[str]] = []
        current: list[str] = []
        for line in wikitext.split("\n"):
            line = line.strip()
            if line.startswith("|-"):
                if current:
                    rows.append(current)
                current = []
            elif line.startswith("|") and not line.startswith("|}"):
                current.append(line.lstrip("|").strip())
        if current:
            rows.append(current)

        events = []
        for r in rows:
            if len(r) < 4:
                continue
            event, date, venue, location = (_clean_wikitext(c) for c in r[:4])
            if event:
                events.append({"event": event, "date": date, "venue": venue, "location": location})
            if len(events) >= limit:
                break
        return events
    except Exception as exc:
        print(f"  [warn] UFC schedule fetch failed: {exc}", file=sys.stderr)
        return []


# ── YouTube ───────────────────────────────────────────────────────────────────

def fetch_youtube_channel(channel_id: str, channel_name: str, window_hours: int = 168) -> list[dict]:
    """Fetch recent videos via YouTube RSS. Returns videos published within window_hours."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    try:
        raw = _fetch(url, timeout=10)
        root = ET.fromstring(raw)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
            "media": "http://search.yahoo.com/mrss/",
        }
        videos = []
        for entry in root.findall("atom:entry", ns):
            vid_el = entry.find("yt:videoId", ns)
            title_el = entry.find("atom:title", ns)
            published_el = entry.find("atom:published", ns)
            video_id = (vid_el.text or "").strip() if vid_el is not None else ""
            title = (title_el.text or "").strip() if title_el is not None else ""
            published_str = (published_el.text or "").strip() if published_el is not None else ""
            if not video_id or not title:
                continue
            try:
                published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except Exception:
                published = None
            age_hours = None
            if published:
                age_hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600
                if published < cutoff:
                    continue
            videos.append({
                "video_id": video_id,
                "title": title,
                "channel": channel_name,
                "published": published_str,
                "age_hours": age_hours,
                "url": f"https://youtu.be/{video_id}",
            })
        return videos
    except Exception as exc:
        print(f"  [warn] YouTube RSS {channel_name} failed: {exc}", file=sys.stderr)
        return []


def fetch_transcript_excerpt(video_id: str, max_words: int = 500, timeout: int = 15) -> str:
    """Fetch first max_words words of transcript. Returns empty string on failure
    or if the call exceeds `timeout` seconds (the underlying library has no
    built-in timeout and can hang indefinitely when YouTube throttles us).

    Uses a daemon thread rather than ThreadPoolExecutor: a non-daemon worker
    thread that's still blocked on the network call when we give up on it
    would otherwise keep the whole process alive at exit (Python waits for
    all non-daemon threads to finish before exiting)."""
    result: dict[str, str] = {}

    def _do_fetch() -> None:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            api = YouTubeTranscriptApi()
            transcript = api.fetch(video_id)
            words_collected = []
            for snippet in transcript:
                words_collected.extend(snippet.text.split())
                if len(words_collected) >= max_words:
                    break
            result["text"] = " ".join(words_collected[:max_words])
        except Exception:
            result["text"] = ""

    thread = threading.Thread(target=_do_fetch, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    if thread.is_alive():
        print(f"  [warn] transcript fetch for {video_id} timed out after {timeout}s", file=sys.stderr)
        return ""
    return result.get("text", "")


# ── Context builder ───────────────────────────────────────────────────────────

def build_context_block(
    reddit_data: dict[str, list[dict]],
    ufc_schedule: list[dict],
    youtube_videos: list[dict],
) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        f"=== LIVE COMMUNITY CONTEXT (fetched {now_str}) ===",
        "",
        "Use the following live data as primary signals to guide your research.",
        "Cross-reference these topics with web search for full details and sources.",
        "",
    ]

    # YouTube section (first — high signal)
    if youtube_videos:
        lines.append("## YouTube — Recent Videos from Tracked Channels")
        lines.append("(Videos published in the past 7 days; transcripts included for past 48h)")
        lines.append("")
        by_channel: dict[str, list[dict]] = {}
        for v in youtube_videos:
            by_channel.setdefault(v["channel"], []).append(v)
        for ch, vids in by_channel.items():
            lines.append(f"  [{ch}]")
            for v in vids:
                age_tag = ""
                if v.get("age_hours") is not None:
                    h = v["age_hours"]
                    age_tag = f" ({int(h)}h ago)" if h < 48 else f" ({int(h/24)}d ago)"
                lines.append(f"    * {v['title']}{age_tag}")
                lines.append(f"      {v['url']}")
                if v.get("transcript_excerpt"):
                    lines.append(f"      TRANSCRIPT EXCERPT: {v['transcript_excerpt']}")
                lines.append("")
        lines.append("")

    # Reddit sections
    for sub, posts in reddit_data.items():
        if posts:
            lines.append(f"## r/{sub} — Hot Posts Right Now")
            for p in posts[:12]:
                lines.append(f"  * {p['title']}")
            lines.append("")

    # UFC schedule
    if ufc_schedule:
        lines.append("## UFC — Upcoming Event Schedule")
        for e in ufc_schedule:
            lines.append(f"  * {e['event']} — {e['date']} — {e['venue']}, {e['location']}")
        lines.append("")

    lines.append("=== END LIVE CONTEXT -- BEGIN DEEP RESEARCH ===")
    lines.append("")
    return "\n".join(lines)


# ── Core research prompt ──────────────────────────────────────────────────────

BASE_PROMPT = """Research the latest UFC and MMA news, gossip, and storylines from the past 24 hours (with a rolling 7-day awareness window for context). The LIVE CONTEXT block above contains real-time signals from Reddit, Wikipedia's UFC event schedule, and tracked YouTube channels — use it as your primary compass for what the MMA community is actually discussing right now.

Cover ALL of the following categories with equal depth:

1. EVENT SCHEDULE & CARD LINEUPS — What's on the upcoming UFC schedule (cross-reference the schedule list above)? Any newly finalized or changed card lineups, main/co-main event confirmations, or venue changes?

2. MATCHUP ANNOUNCEMENTS & BOOKING NEWS — Newly announced fights, title shots, short-notice replacements, and contract/booking drama (fighters turning down fights, callouts that led to bookings, etc.).

3. FIGHT PREDICTIONS & ANALYSIS — What are analysts, ex-fighters, and the community predicting for upcoming bouts? Pull specific predictions and analysis from Daniel Cormier, Chael Sonnen, MMA Junkie, ESPN MMA, and similar voices in the context above, plus Reddit consensus/disagreement.

4. DRAMA, GOSSIP & FACE-OFFS — Call-outs, trash talk, press conference and weigh-in face-off drama, beefs between fighters (or between fighters and Dana White/UFC management), suspensions, and locker-room controversy.

5. INTERVIEWS & BEHIND-THE-SCENES — Notable interviews and exclusive access content from Ariel Helwani, Helen Yee, Submission Radio, MMA Fighting, and official UFC channels — fighter state-of-mind, training camp updates, injury news.

6. COMMUNITY BUZZ & YOUTUBE HIGHLIGHTS — What videos, podcast episodes, or clips are generating the most excitement or backlash right now? Reference specific YouTube videos from the context above by title and channel when relevant.

For Reddit content use targeted searches:
  site:reddit.com/r/MMA [topic]
  site:reddit.com/r/ufc [topic]
  site:reddit.com/r/Sherdog [topic]

Produce a structured Markdown report with a section per category, key findings bolded, and source links for all claims."""


# ── DB update ─────────────────────────────────────────────────────────────────

def update_task_prompt(context_block: str) -> bool:
    full_prompt = context_block + BASE_PROMPT
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        cur.execute(
            "UPDATE scheduled_tasks SET prompt=?, updated_at=? WHERE name=? AND owner=?",
            (full_prompt, datetime.utcnow().isoformat(), TASK_NAME, "deadlyjrmint@gmail.com"),
        )
        rows_updated = cur.rowcount
        conn.commit()
        conn.close()
        return rows_updated > 0
    except Exception as exc:
        print(f"[error] DB update failed: {exc}", file=sys.stderr)
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[ufc-news-gather] {datetime.now().isoformat()}")

    # 1. Reddit (stagger to avoid 429)
    reddit_data: dict[str, list[dict]] = {}
    for i, sub in enumerate(SUBREDDITS):
        if i > 0:
            time.sleep(random.uniform(3.0, 5.0))
        print(f"  Reddit r/{sub}...")
        reddit_data[sub] = fetch_reddit_hot(sub, limit=15)
        print(f"    -> {len(reddit_data[sub])} posts")

    # 2. UFC schedule
    print("  UFC event schedule (Wikipedia)...")
    ufc_schedule = fetch_ufc_schedule(limit=10)
    print(f"    -> {len(ufc_schedule)} upcoming events")

    # 3. YouTube — collect all recent videos
    print("  YouTube channels...")
    all_videos: list[dict] = []
    for channel_id, channel_name in YOUTUBE_CHANNELS.items():
        vids = fetch_youtube_channel(channel_id, channel_name, window_hours=168)
        print(f"    {channel_name}: {len(vids)} videos in past 7d")
        all_videos.extend(vids)

    # 4. Fetch transcripts for fresh videos (past 48h), up to limit
    fresh_videos = sorted(
        [v for v in all_videos if v.get("age_hours") is not None and v["age_hours"] <= TRANSCRIPT_WINDOW_HOURS],
        key=lambda v: v["age_hours"],
    )
    transcript_count = 0
    for v in fresh_videos:
        if transcript_count >= TRANSCRIPT_MAX_VIDEOS:
            break
        print(f"  Transcript: {v['channel']} - {v['title'][:50]}...")
        excerpt = fetch_transcript_excerpt(v["video_id"], max_words=TRANSCRIPT_MAX_WORDS)
        if excerpt:
            v["transcript_excerpt"] = excerpt
            transcript_count += 1
            print(f"    -> {len(excerpt.split())} words")
        else:
            print(f"    -> no transcript available")
        time.sleep(1.0)

    # 5. Build context and inject into task
    context_block = build_context_block(reddit_data, ufc_schedule, all_videos)
    print(f"  Updating '{TASK_NAME}' task...")
    ok = update_task_prompt(context_block)
    if ok:
        total_videos = len(all_videos)
        print(f"[ufc-news-gather] Done. {total_videos} YT videos, {transcript_count} transcripts, schedule+Reddit injected.")
    else:
        print(f"[ufc-news-gather] WARNING: Task '{TASK_NAME}' not found.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
