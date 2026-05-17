# ======================================================
# TELEGRAM MULTI-BOT PARALLEL VIDEO UPLOADER
# ======================================================

import os
import json
import base64
import gzip
import requests
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# ======================
# CONFIG
# ======================
INPUT_FILE = "input_movies.json"

PROJECT_DIR = "."
TEMP_VIDEO = os.path.join(PROJECT_DIR, "temp.mp4")

JSON_DIR = os.path.join(PROJECT_DIR, "json_chunks")
MOVIES_DIR = "movies"
MOVIES_FILE = "movies.json"

# ======================
# TELEGRAM CONFIG (MULTI-BOT)
# Replace with your own bot tokens
# ======================
UPLOAD_BOTS = [
    "8522819598:AAFd20SQZ5G2CgadEtfATTGi191eacbMeUg",
    "8756092341:AAF84Kg1K3Ji7X16dQy5DETtoo-7BktbFyc",
    "8020744167:AAFw0RbWz_NGGfJNLvlO_O-gAU5xl9VLkgs",
]
CHAT_ID = "@stream1806" # or channel ID

# ======================
# CHUNK SETTINGS
# ======================
MAX_JSON_SIZE = 20 * 1024 * 1024      # 20 MB safe JSON size
INITIAL_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB binary chunks

# ======================
# PARALLEL UPLOAD SETTINGS
# ======================
MAX_WORKERS_PER_BOT = 20  # 20 concurrent uploads per bot

# ======================
# CREATE FOLDERS
# ======================
os.makedirs(PROJECT_DIR, exist_ok=True)
os.makedirs(JSON_DIR, exist_ok=True)
os.makedirs(MOVIES_DIR, exist_ok=True)


def clean_name(name):
    """Convert movie name to a safe filename."""
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("_")


def download_video(url):
    """Download source video to TEMP_VIDEO."""
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


def encode(data):
    """Compress binary data with gzip and encode as base64."""
    compressed = gzip.compress(data)
    return base64.b64encode(compressed).decode("utf-8")


def create_chunks(movie_name):
    """Split TEMP_VIDEO into compressed JSON chunk files."""
    files = []
    index = 0
    safe_name = clean_name(movie_name)

    with open(TEMP_VIDEO, "rb") as f:
        while True:
            chunk = f.read(INITIAL_CHUNK_SIZE)
            if not chunk:
                break

            encoded = encode(chunk)

            payload = {
                "order": index,
                "encoding": "gzip+base64",
                "data": encoded
            }

            json_str = json.dumps(payload, separators=(",", ":"))
            size = len(json_str.encode("utf-8"))

            while size > MAX_JSON_SIZE:
                chunk = chunk[:int(len(chunk) * 0.8)]
                encoded = encode(chunk)
                payload["data"] = encoded
                json_str = json.dumps(payload, separators=(",", ":"))
                size = len(json_str.encode("utf-8"))

            filename = f"{safe_name}-chunk_{index:04d}.json"
            filepath = os.path.join(JSON_DIR, filename)

            with open(filepath, "w", encoding="utf-8") as jf:
                jf.write(json_str)

            files.append(filepath)
            print(f"✅ {filename} ({size / 1024:.1f} KB)")
            index += 1

    return files


def get_upload_bot(index):
    """Select bot using round-robin."""
    return UPLOAD_BOTS[index % len(UPLOAD_BOTS)]


def upload(file_path, chunk_index):
    """Upload one chunk file to Telegram."""
    bot_token = get_upload_bot(chunk_index)
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

    for attempt in range(3):
        try:
            with open(file_path, "rb") as f:
                res = requests.post(
                    url,
                    data={"chat_id": CHAT_ID},
                    files={"document": f},
                    timeout=120
                )

            data = res.json()

            if data.get("ok"):
                bot_number = (chunk_index % len(UPLOAD_BOTS)) + 1
                print(f"🚀 Uploaded chunk {chunk_index} using bot #{bot_number}")
                return data["result"]["document"]["file_id"]

            print(f"❌ Upload error for chunk {chunk_index}: {data}")

            if data.get("error_code") == 429:
                retry_after = data.get("parameters", {}).get("retry_after", 5)
                print(f"⏳ Rate limited. Waiting {retry_after} seconds...")
                time.sleep(retry_after)

        except Exception as e:
            print(f"⚠️ Upload retry {attempt + 1} for chunk {chunk_index}: {e}")
            time.sleep(2)

    return None


def upload_all_chunks(json_files):
    """
    Upload all chunks in parallel.
    Total concurrent workers = MAX_WORKERS_PER_BOT * number of bots.
    """
    chunks = []
    total_workers = MAX_WORKERS_PER_BOT * len(UPLOAD_BOTS)

    print(f"🚀 Starting parallel uploads with {total_workers} workers...")

    with ThreadPoolExecutor(max_workers=total_workers) as executor:
        futures = {
            executor.submit(upload, file_path, i): i
            for i, file_path in enumerate(json_files)
        }

        for future in as_completed(futures):
            i = futures[future]

            try:
                file_id = future.result()

                if file_id:
                    chunks.append({
                        "order": i,
                        "file_id": file_id,
                        "bot_index": i % len(UPLOAD_BOTS)
                    })

            except Exception as e:
                print(f"❌ Failed chunk {i}: {e}")

    chunks.sort(key=lambda x: x["order"])
    print(f"✅ Uploaded {len(chunks)} chunks successfully")
    return chunks


def process_movie(movie):
    """Process a single movie."""
    name = movie["name"]
    year = movie["year"]
    source_url = movie["url"]

    print(f"\n🎬 Processing: {name} ({year})")

    safe = clean_name(name)
    manifest_name = f"{safe}_{year}.json"
    manifest_path = os.path.join(MOVIES_DIR, manifest_name)

    if os.path.exists(TEMP_VIDEO):
        os.remove(TEMP_VIDEO)

    if not download_video(source_url):
        print("⛔ Skipping movie")
        return None

    json_files = create_chunks(name)
    chunks = upload_all_chunks(json_files)

    if not chunks:
        print("❌ No chunks uploaded successfully")
        return None

    manifest = {
        "movie": name,
        "year": year,
        "chunkDuration": 5,
        "totalChunks": len(chunks),
        "chunks": chunks
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"📝 Saved → movies/{manifest_name}")
    return manifest_name


def update_catalog(entries):
    """Update master movies.json catalog."""
    if os.path.exists(MOVIES_FILE):
        with open(MOVIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"movies": []}

    existing = {
        (item.get("name"), item.get("year")): item
        for item in data["movies"]
    }

    for entry in entries:
        if entry:
            existing[(entry["name"], entry["year"])] = entry

    data["movies"] = list(existing.values())
    data["movies"].sort(key=lambda x: (x["name"].lower(), x["year"]))

    with open(MOVIES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("📚 movies.json updated")


if __name__ == "__main__":
    print("🚀 Starting pipeline...")

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        movies_data = json.load(f)["movies"]

    catalog_entries = []

    for movie in movies_data:
        manifest_name = process_movie(movie)

        if not manifest_name:
            continue

        manifest_url = (
            "https://raw.githubusercontent.com/"
            "saitarun1806/"
            "video-storing/main/"
            f"movies/{manifest_name}"
        )


        catalog_entries.append({
            "name": movie["name"],
            "year": movie["year"],
            "manifest": manifest_url
        })

    update_catalog(catalog_entries)
    print("\n🎉 DONE!")
