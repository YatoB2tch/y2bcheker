import os
import json
import sys
import time
from pathlib import Path
import requests
import xml.etree.ElementTree as ET

STATE_FILE = Path("state.json")
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID", "").strip()
ROLE_ID = os.getenv("DISCORD_ROLE_ID", "").strip()
BOT_NAME = os.getenv("BOT_NAME", "YouTube Notifier").strip() or "YouTube Notifier"
BOT_AVATAR_URL = os.getenv("BOT_AVATAR_URL", "").strip()

YT_COLOR = 0xFF0000
RETRY_COUNT = 3
RETRY_DELAY = 5


def fail(msg: str):
    print(msg)
    sys.exit(1)


def get_feed_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def load_last_video_id():
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return data.get("video_id")
        except Exception:
            return None
    return None


def save_last_video_id(video_id: str):
    STATE_FILE.write_text(
        json.dumps({"video_id": video_id}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def fetch_with_retry(url: str, timeout: int = 30) -> requests.Response:
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
    title = entry.findtext("atom:title", default="Новое видео", namespaces=ns)
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


def send_to_discord(video):
    mention = f"<@&{ROLE_ID}> " if ROLE_ID else ""
    embed = {
        "title": video["title"],
        "url": video["url"],
        "description": f"Канал: **{video['channel_name']}**",
        "color": YT_COLOR,
        "footer": {"text": "YouTube RSS → Discord"},
    }
    if video.get("published"):
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(video["published"].replace("Z", "+00:00"))
            embed["timestamp"] = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass
    if video.get("thumbnail"):
        embed["image"] = {"url": video["thumbnail"]}
    payload = {
        "username": BOT_NAME,
        "content": f"{mention}Новое видео на канале!",
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


def main():
    if not WEBHOOK_URL:
        fail("Missing DISCORD_WEBHOOK_URL")
    if not YOUTUBE_CHANNEL_ID:
        fail("Missing YOUTUBE_CHANNEL_ID")
    print(f"Checking channel: {YOUTUBE_CHANNEL_ID}")
    feed_url = get_feed_url(YOUTUBE_CHANNEL_ID)
    resp = fetch_with_retry(feed_url)
    latest_video = parse_latest_video(resp.text)
    if not latest_video:
        fail("Не удалось найти видео в RSS.")
    last_video_id = load_last_video_id()
    current_id = latest_video["video_id"]
    if not last_video_id:
        save_last_video_id(current_id)
        print(f"Инициализация завершена. Последнее видео сохранено без отправки: {latest_video['title']}")
        return
    if current_id != last_video_id:
        send_to_discord(latest_video)
        save_last_video_id(current_id)
        print(f"Отправлено новое видео: {latest_video['title']}")
    else:
        print("Новых видео нет.")


if __name__ == "__main__":
    main()
