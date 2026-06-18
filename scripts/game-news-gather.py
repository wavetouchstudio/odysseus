#!/usr/bin/env python3
"""Game Dev News Enricher — fetches live Reddit/Steam/YouTube data and injects
it into the 'Game Dev News Digest' research task prompt before Odysseus fires it.

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
# video titles (e.g. "Pirate Software 💜 Dev Stream"). An UnicodeEncodeError
# here would crash the script before it reaches the DB update step, silently
# breaking the scheduled chain. Force UTF-8 with lossy fallback instead.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Config ────────────────────────────────────────────────────────────────────
TASK_NAME = "Game Dev News Digest"
DB_PATH = Path(__file__).parent.parent / "data" / "app.db"
USER_AGENT = "OdysseusGameDevDigest/1.0 (scheduled research enricher)"

SUBREDDITS = [
    "gamedev",
    "unrealengine",
    "godot",
    "blender",
    "Unity3D",
    "pcgaming",
]

# channel_id: display_name
YOUTUBE_CHANNELS = {
    "UCBobmJyzsJ6Ll7UbfhI4iwQ": "Unreal Engine",
    "UCKIDvfZD1ZhY4_hhbotf7wA": "Godot Engine",
    "UCSMOQeBJ2RAnuFungnQOxLg": "Blender",
    "UCcw0KZs8oa3QgHnckw7EXXA": "Facepunch (S&box)",
    "UCr-5TdGkKszdbboXXsFZJTQ": "Game From Scratch",
    "UCqJ-Xo29CKyLTjn6z2XwYAw": "Game Maker's Toolkit",
    "UCMnULQ6F6kLDAHxofDWIbrw": "Pirate Software",
    "UC0JB7TSe49lg56u6qH8y_MQ": "GDC",
    "UCNvzD7Z-g64bPXxGzaQaa4g": "gameranx",
    "UCYbK_tjZ2OrIZFBvU6CCMiA": "Brackeys",
    "UCG08EqOAXJk_YXPDsAvReSg": "Unity",
    "UCKy1dAqELo0zrOtPkf0eTMw": "IGN",
    "UCZ7AeeVbyslLM_8-nVy2B8Q": "SkillUp",
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


# ── Steam ─────────────────────────────────────────────────────────────────────

def fetch_steam_top_played(limit: int = 15) -> list[dict]:
    """Most-played games right now, by concurrent users (SteamSpy)."""
    try:
        raw = _fetch("https://steamspy.com/api.php?request=top100in2weeks", timeout=12)
        data = json.loads(raw)
        items = sorted(data.values(), key=lambda g: g.get("ccu", 0), reverse=True)
        results = []
        for g in items[:limit]:
            name = g.get("name") or ""
            if name:
                results.append({"name": name, "ccu": g.get("ccu", 0)})
        return results
    except Exception as exc:
        print(f"  [warn] Steam top-played failed: {exc}", file=sys.stderr)
        return []


def fetch_steam_featured(category: str, limit: int = 15) -> list[dict]:
    """category: 'new_releases' or 'top_sellers' from Steam's storefront API."""
    try:
        raw = _fetch("https://store.steampowered.com/api/featuredcategories?cc=us&l=en", timeout=12)
        data = json.loads(raw)
        items = (data.get(category) or {}).get("items") or []
        results = []
        seen = set()
        for item in items:
            name = item.get("name") or ""
            if name and name not in seen:
                seen.add(name)
                results.append({"name": name})
            if len(results) >= limit:
                break
        return results
    except Exception as exc:
        print(f"  [warn] Steam {category} failed: {exc}", file=sys.stderr)
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
    steam_top_played: list[dict],
    steam_new_releases: list[dict],
    steam_top_sellers: list[dict],
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

    # Steam charts
    if steam_top_played:
        lines.append("## Steam — Most Played Right Now (by concurrent users)")
        for g in steam_top_played[:15]:
            lines.append(f"  * {g['name']} (ccu: {g['ccu']:,})")
        lines.append("")

    if steam_top_sellers:
        lines.append("## Steam — Top Sellers")
        for g in steam_top_sellers[:15]:
            lines.append(f"  * {g['name']}")
        lines.append("")

    if steam_new_releases:
        lines.append("## Steam — New Releases")
        for g in steam_new_releases[:15]:
            lines.append(f"  * {g['name']}")
        lines.append("")

    lines.append("=== END LIVE CONTEXT -- BEGIN DEEP RESEARCH ===")
    lines.append("")
    return "\n".join(lines)


# ── Core research prompt ──────────────────────────────────────────────────────

BASE_PROMPT = """Research the latest video game development and gaming industry news from the past 24 hours (with a rolling 7-day awareness window for context). The LIVE CONTEXT block above contains real-time signals from Reddit, Steam, and tracked YouTube channels — use it as your primary compass for what the community is actually discussing right now.

Cover ALL of the following categories with equal depth:

1. GAME ENGINE & TECHNOLOGY NEWS — Updates, version releases, and tooling/rendering announcements specifically for Unreal Engine, Godot, Blender, and S&Box (Facepunch's Source 2 platform). Also cover Unity and any other major engine news (rendering tech like Lumen/Nanite, new editor features, pricing/licensing changes).

2. NEW GAME RELEASES — Notable new releases, demos, and early access launches. Cross-reference with the Steam New Releases list above for what's actually dropping right now.

3. STEAM CHARTS & MARKET TRENDS — What's topping concurrent player counts and top-seller charts above? Any surprise breakout hits, dying trends, or notable chart movement?

4. PLAYER SENTIMENT & COMMUNITY TRENDS — What's driving discussion, hype, or backlash among players and developers right now (monetization controversies, beloved patches, viral clips, industry layoffs/drama)? Reference specific Reddit threads from the context above.

5. GAME DEV TOOLS & WORKFLOW — New or updated tools, plugins, and asset pipelines for Unreal, Godot, Blender, Unity, and S&Box specifically. AI-assisted dev tooling counts here too.

6. COMMUNITY BUZZ & YOUTUBE HIGHLIGHTS — What videos, devlogs, or talks are generating the most excitement? Reference specific YouTube videos from the context above by title and channel when relevant.

For Reddit content use targeted searches:
  site:reddit.com/r/gamedev [topic]
  site:reddit.com/r/unrealengine [topic]
  site:reddit.com/r/godot [topic]

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
    print(f"[game-news-gather] {datetime.now().isoformat()}")

    # 1. Reddit (stagger to avoid 429)
    reddit_data: dict[str, list[dict]] = {}
    for i, sub in enumerate(SUBREDDITS):
        if i > 0:
            time.sleep(random.uniform(3.0, 5.0))
        print(f"  Reddit r/{sub}...")
        reddit_data[sub] = fetch_reddit_hot(sub, limit=15)
        print(f"    -> {len(reddit_data[sub])} posts")

    # 2. Steam
    print("  Steam top played...")
    steam_top_played = fetch_steam_top_played(limit=15)
    print(f"    -> {len(steam_top_played)} games")

    print("  Steam top sellers...")
    steam_top_sellers = fetch_steam_featured("top_sellers", limit=15)
    print(f"    -> {len(steam_top_sellers)} games")

    print("  Steam new releases...")
    steam_new_releases = fetch_steam_featured("new_releases", limit=15)
    print(f"    -> {len(steam_new_releases)} games")

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
    context_block = build_context_block(reddit_data, steam_top_played, steam_new_releases, steam_top_sellers, all_videos)
    print(f"  Updating '{TASK_NAME}' task...")
    ok = update_task_prompt(context_block)
    if ok:
        total_videos = len(all_videos)
        print(f"[game-news-gather] Done. {total_videos} YT videos, {transcript_count} transcripts, Steam+Reddit injected.")
    else:
        print(f"[game-news-gather] WARNING: Task '{TASK_NAME}' not found.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
