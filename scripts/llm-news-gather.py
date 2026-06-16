#!/usr/bin/env python3
"""LLM News Enricher — fetches live Reddit/HuggingFace/YouTube data and injects
it into the 'LLM News Digest' research task prompt before Odysseus fires it.

Schedule: 5 minutes before the Odysseus research task (via Odysseus run_script action).
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
import random
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
TASK_NAME = "LLM News Digest"
DB_PATH = Path(__file__).parent.parent / "data" / "app.db"
USER_AGENT = "OdysseusLLMDigest/1.0 (scheduled research enricher)"

SUBREDDITS = [
    "LocalLLaMA",
    "MachineLearning",
    "singularity",
    "artificial",
]

# channel_id: display_name
YOUTUBE_CHANNELS = {
    "UCPix8N6PMRI4KzgyjuZeF0g": "Fahd Mirza",
    "UCRW08KcTVjXEmBzBsVl7XjA": "Stefan 3D AI",
    "UCSPkiRjFYpz-8DY-aF_1wRg": "The AI Grid",
    "UCawZsQWqfGSbCI5yjkdVkTA": "Matthew Berman",
    "UChpleBmo18P08aKCIgti38g": "MreFlow",
    "UCIgnGlGkVRhd4qNFcEwLL4A": "The AI Search",
    "UC5LTm52VaiV-5Q3C-txWVGQ": "AI Revolution X",
    "UC6Bo2Gquf86J5VU6K2-12bw": "Sabine Hossenfelder",
    "UCZa18YV7qayTh-MRIrBhDpA": "Dwarkesh Patel",
    "UCYO_jab_esuFRV4b17AJtAw": "Andrej Karpathy",
    "UCHmD-oSpV0sNfAUnpYpj8KA": "Yannic Kilcher",
    "UCruC3Lkt_-StdHlPiyWbPSg": "Trelis Research",
    "UCNJ1Ymd5yFuUPtn21xtRbbw": "AI Explained",
    "UC2Xd-TjJByJyK2w1zNwY0zQ": "Fireship",
    "UCRGb8yCnI5-upL3hT4oiOZw": "Pixel Artistry",
    # Recommended additions
    "UCpV_X0VrL8-jg3t6wYGS-1g": "1littlecoder",
    "UCQALLeQPoZdZC4JNUboVEUg": "sentdex",
    "UCCtwvVWj4lvPO573Kn8fosw": "World of AI",
    "UCMT1Aw4R4nf_sFNDeuJqc6w": "AI Warehouse",
    "UCeRjipR4_SsCddq9VZ2AeKg": "LlamaIndex",
    "UCUOIpszFPlxiKQq3ZBBRnbw": "Dave Shapiro",
    "UCfOvNb3xj28SNqPQ_JIbumg": "Code4AI",
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
        skip = {subreddit.lower(), "localllama", "machinelearning", "singularity", "artificial"}
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


# ── HuggingFace ───────────────────────────────────────────────────────────────

def fetch_hf_trending(limit: int = 20) -> list[dict]:
    try:
        raw = _fetch("https://huggingface.co/api/trending", timeout=12)
        data = json.loads(raw)
        results = []
        for item in (data.get("recentlyTrending") or [])[:limit]:
            repo = item.get("repoData") or {}
            model_id = repo.get("id") or ""
            pipeline = repo.get("pipeline_tag") or "?"
            likes = repo.get("likes") or 0
            if model_id:
                results.append({"id": model_id, "type": pipeline, "likes": likes})
        return results
    except Exception as exc:
        print(f"  [warn] HF trending failed: {exc}", file=sys.stderr)
        return []


def fetch_hf_new_models(hours: int = 24, limit: int = 20) -> list[dict]:
    try:
        url = (
            "https://huggingface.co/api/models"
            "?sort=lastModified&direction=-1&limit=50&filter=text-generation"
        )
        raw = _fetch(url, timeout=12)
        models = json.loads(raw)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        results = []
        for m in models:
            last_mod = m.get("lastModified") or ""
            try:
                ts = datetime.fromisoformat(last_mod.replace("Z", "+00:00"))
                if ts < cutoff:
                    continue
            except Exception:
                pass
            model_id = m.get("modelId") or m.get("id") or ""
            likes = m.get("likes") or 0
            if model_id:
                results.append({"id": model_id, "likes": likes, "lastModified": last_mod})
        return results[:limit]
    except Exception as exc:
        print(f"  [warn] HF new models failed: {exc}", file=sys.stderr)
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


def fetch_transcript_excerpt(video_id: str, max_words: int = 500) -> str:
    """Fetch first max_words words of transcript. Returns empty string on failure."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, CouldNotRetrieveTranscript
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id)
        words_collected = []
        for snippet in transcript:
            words_collected.extend(snippet.text.split())
            if len(words_collected) >= max_words:
                break
        excerpt = " ".join(words_collected[:max_words])
        return excerpt
    except Exception:
        return ""


# ── Context builder ───────────────────────────────────────────────────────────

def build_context_block(
    reddit_data: dict[str, list[dict]],
    hf_trending: list[dict],
    hf_new: list[dict],
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

    # HF trending
    if hf_trending:
        lines.append("## HuggingFace Trending Models")
        text_gen = [m for m in hf_trending if "text" in m["type"].lower() or m["type"] in ("?", "")]
        other = [m for m in hf_trending if m not in text_gen]
        if text_gen:
            lines.append("  Text/LLM:")
            for m in text_gen[:10]:
                lines.append(f"    * {m['id']} (likes: {m['likes']:,})")
        if other:
            lines.append("  Other AI:")
            for m in other[:5]:
                lines.append(f"    * {m['id']} [{m['type']}] (likes: {m['likes']:,})")
        lines.append("")

    if hf_new:
        lines.append("## HuggingFace — New Text-Gen Models (past 24h)")
        for m in hf_new[:15]:
            lines.append(f"  * {m['id']} (likes: {m['likes']:,})")
        lines.append("")

    lines.append("=== END LIVE CONTEXT -- BEGIN DEEP RESEARCH ===")
    lines.append("")
    return "\n".join(lines)


# ── Core research prompt ──────────────────────────────────────────────────────

BASE_PROMPT = """Research the latest AI and LLM news from the past 24 hours (with a rolling 7-day awareness window for context). The LIVE CONTEXT block above contains real-time signals from Reddit, HuggingFace, and tracked YouTube channels — use it as your primary compass for what the community is actually discussing right now.

Cover ALL of the following categories with equal depth:

1. OPEN SOURCE MODEL RELEASES — New model drops, version updates, and architecture announcements (Llama, Qwen, Mistral, Phi, Gemma, DeepSeek, Yi, etc.). Cross-reference with HuggingFace trending and recent pushes listed above.

2. QUANTIZATIONS & DISTILLATIONS — Popular GGUF/AWQ/EXL2/GPTQ quants and distilled models getting traction. What are r/LocalLLaMA users actually running and recommending? Any warnings about bad distillations?

3. CLOSED / FRONTIER MODELS — Updates, benchmarks, API changes, pricing, or capability announcements from OpenAI, Anthropic, Google DeepMind, Meta, xAI, Mistral, Cohere, and similar labs.

4. OPEN SOURCE AI TOOLS & PROJECTS — New releases or major updates to inference engines, fine-tuning frameworks, RAG tools, agent frameworks, UI frontends, and adjacent OSS projects (llama.cpp, vllm, ollama, Jan, LM Studio, koboldcpp, ComfyUI, etc.)

5. COMMUNITY BUZZ & YOUTUBE HIGHLIGHTS — What models, quants, or projects are generating the most excitement? Reference specific YouTube videos from the context above by title and channel when relevant. Include notable debates, controversies, or viral benchmark results.

For Reddit content use targeted searches:
  site:reddit.com/r/LocalLLaMA [topic]
  site:reddit.com/r/MachineLearning [topic]

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
    print(f"[llm-news-gather] {datetime.now().isoformat()}")

    # 1. Reddit (stagger to avoid 429)
    reddit_data: dict[str, list[dict]] = {}
    for i, sub in enumerate(SUBREDDITS):
        if i > 0:
            time.sleep(random.uniform(3.0, 5.0))
        print(f"  Reddit r/{sub}...")
        reddit_data[sub] = fetch_reddit_hot(sub, limit=15)
        print(f"    -> {len(reddit_data[sub])} posts")

    # 2. HuggingFace
    print("  HF trending...")
    hf_trending = fetch_hf_trending(limit=25)
    print(f"    -> {len(hf_trending)} models")

    print("  HF new models (24h)...")
    hf_new = fetch_hf_new_models(hours=24, limit=20)
    print(f"    -> {len(hf_new)} new models")

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
    context_block = build_context_block(reddit_data, hf_trending, hf_new, all_videos)
    print(f"  Updating '{TASK_NAME}' task...")
    ok = update_task_prompt(context_block)
    if ok:
        total_videos = len(all_videos)
        print(f"[llm-news-gather] Done. {total_videos} YT videos, {transcript_count} transcripts, HF+Reddit injected.")
    else:
        print(f"[llm-news-gather] WARNING: Task '{TASK_NAME}' not found.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
