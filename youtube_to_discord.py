import os
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import requests
import xml.etree.ElementTree as ET

STATE_FILE = Path("state.json")
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
YOUTUBE_CHANNEL_IDS = [
    ch.strip()
    for ch in os.getenv("YOUTUBE_CHANNEL_IDS", "").split(",")
    if ch.strip()
]
ROLE_ID = os.getenv("DISCORD_ROLE_ID", "").strip()
BOT_NAME = os.getenv("BOT_NAME", "YouTube Notifier").strip() or "YouTube Notifier"
BOT_AVATAR_URL = os.getenv("BOT_AVATAR_URL", "").strip()
FORCE_CHANNEL_ID = os.getenv("FORCE_CHANNEL_ID", "").strip()

YT_COLOR = 0xFF0000
RETRY_COUNT = 3
RETRY_DELAY = 5


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fail(msg: str):
    print(msg)
    sys.exit(1)


def get_feed_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(data: dict):
    data["last_updated"] = now_iso()
    STATE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def get_last_video_id(state: dict, channel_id: str):
    return state.get("channels", {}).get(channel_id, {}).get("video_id")


def set_last_video_id(state: dict, channel_id: str, video_id: str):
    state.setdefault("channels", {})
    state["channels"][channel_id] = {
        "video_id": video_id,
        "updated_at": now_iso()
    }


def fetch_with_retry(url: str, timeout: int = 30):
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            print(f"[Attempt {attempt}/{RETRY_COUNT}] Request failed: {e}")
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_DELAY)
    fail(f"Failed to fetch {url} after {RETRY_COUNT} attempts")


def parse_latest_video(feed_xml: str):
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/"
    }
    root = ET.fromstring(feed_xml)
    entry = root.find("atom:entry", ns)
    if entry is None:
        return None
    video_id = entry.findtext("yt:videoId", default="", namespaces=ns)
    title = entry.findtext("atom:title", default="New video", namespaces=ns)
    published = entry.findtext("atom:published", default="", namespaces=ns)
    link = entry.find("atom:link", ns)
    url = link.attrib.get("href") if link is not None else f"https://youtu.be/{video_id}"
    author = entry.find("atom:author", ns)
    channel_name = (
        author.findtext("atom:name", default="YouTube", namespaces=ns)
        if author is not None else "YouTube"
    )
    thumbnail = None
    group = entry.find("media:group", ns)
    if group is not None:
        thumb = group.find("media:thumbnail", ns)
        if thumb is not None:
            thumbnail = thumb.attrib.get("url")
    return {
        "video_id": video_id,
        "title": title,
        "url": url,
        "channel_name": channel_name,
        "thumbnail": thumbnail,
        "published": published,
    }


def send_to_discord(video, force: bool = False):
    mention = f"<@&{ROLE_ID}> " if ROLE_ID else ""
    label = "[FORCE] " if force else ""
    embed = {
        "title": video["title"],
        "url": video["url"],
        "description": f"Channel: **{video['channel_name']}**",
        "color": YT_COLOR,
        "footer": {"text": "YouTube RSS -> Discord"},
    }
    if video.get("published"):
        try:
            dt = datetime.fromisoformat(video["published"].replace("Z", "+00:00"))
            embed["timestamp"] = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass
    if video.get("thumbnail"):
        embed["image"] = {"url": video["thumbnail"]}
    payload = {
        "username": BOT_NAME,
        "content": f"{mention}{label}New video!",
        "embeds": [embed],
    }
    if BOT_AVATAR_URL:
        payload["avatar_url"] = BOT_AVATAR_URL
    for attempt in range(1, RETRY_COUNT + 1):
        try:
            r = requests.post(WEBHOOK_URL, json=payload, timeout=30)
            if r.status_code == 429:
                retry_after = r.json().get("retry_after", RETRY_DELAY)
                print(f"Discord rate limit. Waiting {retry_after}s...")
                time.sleep(float(retry_after))
                continue
            r.raise_for_status()
            return
        except requests.RequestException as e:
            print(f"[Attempt {attempt}/{RETRY_COUNT}] Discord send failed: {e}")
            if attempt < RETRY_COUNT:
                time.sleep(RETRY_DELAY)
    fail(f"Failed to send to Discord after {RETRY_COUNT} attempts")


def run_force(channel_id: str):
    print(f"[FORCE] Sending latest video from channel: {channel_id}")
    feed_url = get_feed_url(channel_id)
    resp = fetch_with_retry(feed_url)
    video = parse_latest_video(resp.text)
    if not video:
        fail(f"[FORCE] No videos found for channel: {channel_id}")
    print(f"[FORCE] Sending: {video['title']}")
    send_to_discord(video, force=True)
    state = load_state()
    set_last_video_id(state, channel_id, video["video_id"])
    save_state(state)
    print(f"[FORCE] Done. state.json updated at {state['last_updated']}")


def main():
    if not WEBHOOK_URL:
        fail("Missing DISCORD_WEBHOOK_URL")
    if FORCE_CHANNEL_ID:
        run_force(FORCE_CHANNEL_ID)
        return
    if not YOUTUBE_CHANNEL_IDS:
        fail("Missing YOUTUBE_CHANNEL_IDS")
    state = load_state()
    state_changed = False
    for channel_id in YOUTUBE_CHANNEL_IDS:
        print(f"Checking channel: {channel_id}")
        feed_url = get_feed_url(channel_id)
        resp = fetch_with_retry(feed_url)
        latest_video = parse_latest_video(resp.text)
        if not latest_video:
            print(f"No videos found for channel: {channel_id}")
            continue
        last_video_id = get_last_video_id(state, channel_id)
        current_id = latest_video["video_id"]
        if not last_video_id:
            set_last_video_id(state, channel_id, current_id)
            state_changed = True
            print(f"[{channel_id}] Initialized. Saved without notification: {latest_video['title']}")
            continue
        if current_id != last_video_id:
            send_to_discord(latest_video)
            set_last_video_id(state, channel_id, current_id)
            state_changed = True
            print(f"[{channel_id}] Sent new video: {latest_video['title']}")
        else:
            print(f"[{channel_id}] No new videos.")
    if state_changed:
        save_state(state)
        print(f"state.json updated at {state['last_updated']}")
    else:
        # Always update last_checked timestamp even if no new videos
        state["last_checked"] = now_iso()
        save_state(state)
        print(f"No changes. state.json last_checked updated at {state['last_updated']}")


if __name__ == "__main__":
    main()
