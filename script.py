# ======================================================
# PART 1
# CONFIG + HELPERS + DOWNLOAD + HLS CREATION
# ======================================================

import os
import json
import requests
import time
import re
import subprocess
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

# ======================
# CONFIG
# ======================
INPUT_FILE = "input_movies.json"

PROJECT_DIR = "."
TEMP_VIDEO = os.path.join(PROJECT_DIR, "temp.mp4")

SEGMENTS_DIR = os.path.join(PROJECT_DIR, "hls_segments")
MOVIES_DIR = "movies"
MOVIES_FILE = "movies.json"

# ======================
# TELEGRAM CONFIG
# ======================
UPLOAD_BOTS = [
    "8522819598:AAFd20SQZ5G2CgadEtfATTGi191eacbMeUg",
    "8756092341:AAF84Kg1K3Ji7X16dQy5DETtoo-7BktbFyc",
    "8020744167:AAFw0RbWz_NGGfJNLvlO_O-gAU5xl9VLkgs",
    "8809309930:AAGq_qEv3e3TjKwU2lQf9pINVFxIV5KLYok",
    "8934970747:AAGNtsVG5MvtK5TxL5fFzyrLBIWjIG6CwwU",
    "8637056729:AAG7X4jOJRuA_t97x39W1bxz8NorIl-Aw-c",
    "8859983169:AAEx_7GkzxwrGlH33-I4Sq5ExzCFNe5lNmE",
    "6824663359:AAFJeyqimtZGUl5KifGnXnwbtJ6r2HO_1d0",
    "7737272178:AAGJVAH0mhz-0rdIpNyMms0QRyU5ynsJI3w",
    "7651528639:AAFW4poQ-NNbdqOSskr2mxsjZpkTeGcrRF4",
    "8651470873:AAEMq3GGKk9FBG60O6Vd_eH5V-1x0S6Pqc4",
    "7557078677:AAGQjGgkl7DzFGGKCguVm1mqu48X3oOpmjs",
    
]

CHAT_ID = "@stream1806"

# ======================
# WORKER URL
# ======================
WORKER_URL = "https://frosty-snow-1291.database1806.workers.dev"

# ======================
# HLS SETTINGS
# ======================
SEGMENT_DURATION = 5  # seconds

# ======================
# PARALLEL UPLOAD SETTINGS
# ======================
MAX_WORKERS_PER_BOT = 6

# ======================
# CREATE FOLDERS
# ======================
os.makedirs(PROJECT_DIR, exist_ok=True)
os.makedirs(SEGMENTS_DIR, exist_ok=True)
os.makedirs(MOVIES_DIR, exist_ok=True)

# ======================
# HELPERS
# ======================
def clean_name(name):
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("_")


# ======================
# DOWNLOAD VIDEO
# ======================
def download_video(url):
    print(f"⬇️ Downloading: {url}")

    for attempt in range(3):
        try:
            with requests.get(url, stream=True, timeout=20) as r:
                if r.status_code != 200:
                    raise Exception(f"Status {r.status_code}")

                with open(TEMP_VIDEO, "wb") as f:
                    for chunk in r.iter_content(1024 * 1024):
                        if chunk:
                            f.write(chunk)

            print("✅ Downloaded")
            return True

        except Exception as e:
            print(f"⚠️ Retry {attempt + 1}: {e}")
            time.sleep(2)

    print("❌ Download failed")
    return False


# ======================
# CREATE HLS FILES
# ======================
def create_hls(movie_name):
    """
    Create:
      - playlist.m3u8
      - segment000.ts
      - segment001.ts
      - ...
    """

    safe_name = clean_name(movie_name)

    # Clean segment folder
    if os.path.exists(SEGMENTS_DIR):
        shutil.rmtree(SEGMENTS_DIR)

    os.makedirs(SEGMENTS_DIR, exist_ok=True)

    playlist_path = os.path.join(SEGMENTS_DIR, "playlist.m3u8")
    segment_pattern = os.path.join(SEGMENTS_DIR, "segment%05d.ts")

    print("🎬 Creating HLS segments...")

    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", TEMP_VIDEO,

            # Re-encode for browser compatibility
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",

            "-c:a", "aac",
            "-b:a", "128k",
            "-ac", "2",

            # HLS settings
            "-f", "hls",
            "-hls_time", str(SEGMENT_DURATION),
            "-hls_playlist_type", "vod",
            "-hls_segment_filename", segment_pattern,

            playlist_path
        ],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError("FFmpeg HLS creation failed")

    print("✅ HLS created")

    segment_files = sorted(
        os.path.join(SEGMENTS_DIR, f)
        for f in os.listdir(SEGMENTS_DIR)
        if f.endswith(".ts")
    )

    if not segment_files:
        raise RuntimeError("No HLS segments were created")

    print(f"📦 Created {len(segment_files)} segments")

    return playlist_path, segment_files

# ======================================================
# PART 2
# MULTI-BOT UPLOAD + PLAYLIST GENERATION + CATALOG + MAIN
# ======================================================

# ======================
# SELECT BOT (ROUND ROBIN)
# ======================
def get_upload_bot(index):
    return UPLOAD_BOTS[index % len(UPLOAD_BOTS)]


# ======================
# UPLOAD SINGLE FILE
# ======================
def upload(file_path, index):
    """
    Upload one file (.ts segment) to Telegram.
    Handles retries and Telegram 429 rate limits.
    Returns Telegram file_id on success.
    """
    bot_token = get_upload_bot(index)
    api_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

    for attempt in range(3):
        try:
            with open(file_path, "rb") as f:
                response = requests.post(
                    api_url,
                    data={"chat_id": CHAT_ID},
                    files={"document": f},
                    timeout=300
                )

            data = response.json()

            # Success
            if data.get("ok"):
                bot_number = (index % len(UPLOAD_BOTS)) + 1

                print(
                    f"🚀 Uploaded segment "
                    f"{index} "
                    f"using bot #{bot_number}"
                )

                return data["result"]["document"]["file_id"]

            # Telegram error
            print(
                f"❌ Upload error for segment "
                f"{index}: {data}"
            )

            # Rate limit
            if data.get("error_code") == 429:
                retry_after = (
                    data.get("parameters", {})
                    .get("retry_after", 5)
                )

                print(
                    f"⏳ Rate limited. "
                    f"Waiting {retry_after} seconds..."
                )

                time.sleep(retry_after)

        except Exception as e:
            print(
                f"⚠️ Upload retry "
                f"{attempt + 1} for "
                f"segment {index}: {e}"
            )
            time.sleep(2)

    return None


# ======================
# UPLOAD ALL FILES (GUARANTEED)
# ======================
def upload_all_files(file_paths):
    """
    Upload all segments and retry until every file is uploaded.
    """
    total_files = len(file_paths)
    total_workers = MAX_WORKERS_PER_BOT * len(UPLOAD_BOTS)

    print(f"🚀 Starting uploads with {total_workers} workers...")
    print(f"📦 Total segments: {total_files}")

    uploaded = {}
    pending = list(range(total_files))
    round_number = 1

    while pending:
        print(f"\n🔄 Upload Round {round_number}")
        print(f"⏳ Remaining segments: {len(pending)}")

        failed = []
        workers = min(total_workers, len(pending))

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    upload,
                    file_paths[index],
                    index
                ): index
                for index in pending
            }

            for future in as_completed(futures):
                index = futures[future]

                try:
                    file_id = future.result()

                    if file_id:
                        uploaded[index] = {
                            "index": index,
                            "file_id": file_id
                        }
                    else:
                        failed.append(index)

                except Exception as e:
                    print(f"❌ Failed segment {index}: {e}")
                    failed.append(index)

        pending = sorted(failed)

        print(
            f"✅ Uploaded: {len(uploaded)}/{total_files} | "
            f"Remaining: {len(pending)}"
        )

        if pending:
            print("⏳ Waiting 5 seconds before retry...")
            time.sleep(5)

        round_number += 1

    print(f"\n🎉 All {total_files} segments uploaded successfully!")

    return [uploaded[i] for i in sorted(uploaded.keys())]


# ======================
# CREATE FINAL PLAYLIST
# ======================
def build_final_playlist(movie_name, uploaded_segments):
    """
    Generate a new .m3u8 playlist that points to
    Cloudflare Worker URLs using Telegram file_ids.
    """
    safe_name = clean_name(movie_name)
    playlist_name = f"{safe_name}.m3u8"
    playlist_path = os.path.join(MOVIES_DIR, playlist_name)

    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{SEGMENT_DURATION}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:VOD",
    ]

    for segment in uploaded_segments:
        file_id = segment["file_id"]

        lines.append(f"#EXTINF:{SEGMENT_DURATION:.1f},")
        lines.append(
            f"{WORKER_URL}/file_by_id/"
            f"{requests.utils.quote(file_id, safe='')}"
        )

    lines.append("#EXT-X-ENDLIST")

    with open(playlist_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"📝 Saved playlist → {playlist_path}")

    return playlist_name


# ======================
# PROCESS ONE MOVIE
# ======================
def process_movie(movie):
    name = movie["name"]
    year = movie["year"]
    source_url = movie["url"]

    print(f"\n🎬 Processing: {name} ({year})")

    # Remove previous temp video
    if os.path.exists(TEMP_VIDEO):
        os.remove(TEMP_VIDEO)

    # Download source video
    if not download_video(source_url):
        print("⛔ Skipping movie")
        return None

    # Create HLS playlist and segments
    _, segment_files = create_hls(name)

    # Upload all segments
    uploaded_segments = upload_all_files(segment_files)

    # Build final playlist pointing to Worker URLs
    playlist_name = build_final_playlist(
        name,
        uploaded_segments
    )

    return playlist_name


# ======================
# UPDATE movies.json
# ======================
def update_catalog(entries):
    if os.path.exists(MOVIES_FILE):
        with open(MOVIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"movies": []}

    # Prevent duplicates
    existing = {
        (item.get("name"), item.get("year")): item
        for item in data["movies"]
    }

    for entry in entries:
        if entry:
            existing[(entry["name"], entry["year"])] = entry

    data["movies"] = list(existing.values())

    # Sort alphabetically
    data["movies"].sort(
        key=lambda x: (
            x["name"].lower(),
            x["year"]
        )
    )

    # Save movies.json
    with open(MOVIES_FILE, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )

    print("📚 movies.json updated")


# ======================
# MAIN
# ======================
if __name__ == "__main__":
    print("🚀 Starting HLS pipeline...")

    # Load input_movies.json
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        movies_data = json.load(f)["movies"]

    catalog_entries = []

    # Process each movie
    for movie in movies_data:
        playlist_name = process_movie(movie)

        if not playlist_name:
            continue

        # GitHub raw URL for playlist
        playlist_url = (
            "https://raw.githubusercontent.com/"
            "saitarun1806/"
            "video-storing/main/"
            f"movies/{playlist_name}"
        )

        catalog_entries.append({
            "name": movie["name"],
            "year": movie["year"],
            "playlist": playlist_url
        })

    # Update movies.json
    update_catalog(catalog_entries)

    print("\n🎉 DONE!")
