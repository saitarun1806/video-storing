
# ======================================================
# PART 1
# CONFIG + HELPERS + DOWNLOAD + CHUNK CREATION
# ======================================================

import os
import json
import base64
import gzip
import requests
import time
import re

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
# ======================
UPLOAD_BOTS = [
    "8522819598:AAFd20SQZ5G2CgadEtfATTGi191eacbMeUg",
    "8756092341:AAF84Kg1K3Ji7X16dQy5DETtoo-7BktbFyc",
    "8020744167:AAFw0RbWz_NGGfJNLvlO_O-gAU5xl9VLkgs",
]

CHAT_ID = "@stream1806"   # Your Telegram channel username or channel ID

# ======================
# CHUNK SETTINGS
# ======================
MAX_JSON_SIZE = 20 * 1024 * 1024      # Telegram-safe JSON size
INITIAL_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB binary chunks

# ======================
# CREATE FOLDERS
# ======================
os.makedirs(PROJECT_DIR, exist_ok=True)
os.makedirs(JSON_DIR, exist_ok=True)
os.makedirs(MOVIES_DIR, exist_ok=True)

# ======================
# HELPERS
# ======================
def clean_name(name):
    """
    Convert movie name to a safe filename.
    Example:
        'The Mummy (2026)' -> 'the_mummy_2026'
    """
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("_")


# ======================
# DOWNLOAD (ROBUST)
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
# ENCODE (gzip + base64)
# ======================
def encode(data):
    compressed = gzip.compress(data)
    return base64.b64encode(compressed).decode("utf-8")


# ======================
# CREATE JSON CHUNKS
# ======================
def create_chunks(movie_name):
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

            # Ensure final JSON stays under MAX_JSON_SIZE
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

            print(
                f"✅ {filename} "
                f"({size / 1024:.1f} KB)"
            )

            index += 1

    return files

# ======================================================
# PART 2
# MULTI-BOT UPLOAD + MANIFEST + CATALOG + MAIN
# ======================================================

# ======================
# SELECT BOT (ROUND ROBIN)
# ======================
def get_upload_bot(index):
    """
    Chunk 0 -> Bot 1
    Chunk 1 -> Bot 2
    Chunk 2 -> Bot 3
    Chunk 3 -> Bot 1
    """
    return UPLOAD_BOTS[index % len(UPLOAD_BOTS)]


# ======================
# TELEGRAM UPLOAD (MULTI-BOT)
# ======================
def upload(file_path, chunk_index):
    bot_token = get_upload_bot(chunk_index)
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

    for attempt in range(3):
        try:
            with open(file_path, "rb") as f:
                res = requests.post(
                    url,
                    data={"chat_id": CHAT_ID},
                    files={"document": f},
                    timeout=60
                )

            data = res.json()

            if data.get("ok"):
                bot_number = (
                    chunk_index % len(UPLOAD_BOTS)
                ) + 1

                print(
                    f"🚀 Uploaded chunk "
                    f"{chunk_index} "
                    f"using bot #{bot_number}"
                )

                return data["result"]["document"]["file_id"]

            print(
                f"❌ Upload error for "
                f"chunk {chunk_index}: "
                f"{data}"
            )

        except Exception as e:
            print(
                f"⚠️ Upload retry "
                f"{attempt + 1} for "
                f"chunk {chunk_index}: {e}"
            )
            time.sleep(2)

    return None


# ======================
# PROCESS MOVIE
# ======================
def process_movie(movie):
    name = movie["name"]
    year = movie["year"]
    url = movie["url"]

    print(
        f"\n🎬 Processing: "
        f"{name} ({year})"
    )

    safe = clean_name(name)
    manifest_name = f"{safe}_{year}.json"
    manifest_path = os.path.join(
        MOVIES_DIR,
        manifest_name
    )

    # Remove previous temp video
    if os.path.exists(TEMP_VIDEO):
        os.remove(TEMP_VIDEO)

    # Download source video
    if not download_video(url):
        print("⛔ Skipping movie")
        return None

    # Create JSON chunk files
    json_files = create_chunks(name)

    # Upload all chunks
    chunks = []

    for i, file_path in enumerate(json_files):
        file_id = upload(file_path, i)

        if file_id:
            chunks.append({
                "order": i,
                "file_id": file_id,
                "bot_index": (
                    i % len(UPLOAD_BOTS)
                )
            })

        # Small delay to avoid hitting limits
        time.sleep(0.4)

    # Create manifest
    manifest = {
        "movie": name,
        "year": year,
        "chunkDuration": 5,
        "totalChunks": len(chunks),
        "chunks": chunks
    }

    # Save manifest
    with open(
        manifest_path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            manifest,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(
        f"📝 Saved → "
        f"movies/{manifest_name}"
    )

    return manifest_name


# ======================
# UPDATE movies.json
# ======================
def update_catalog(entries):
    if os.path.exists(MOVIES_FILE):
        with open(
            MOVIES_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)
    else:
        data = {"movies": []}

    # Prevent duplicates
    existing = {
        (
            item.get("name"),
            item.get("year")
        ): item
        for item in data["movies"]
    }

    for entry in entries:
        if entry:
            existing[
                (
                    entry["name"],
                    entry["year"]
                )
            ] = entry

    data["movies"] = list(
        existing.values()
    )

    # Sort alphabetically
    data["movies"].sort(
        key=lambda x: (
            x["name"].lower(),
            x["year"]
        )
    )

    # Save movies.json
    with open(
        MOVIES_FILE,
        "w",
        encoding="utf-8"
    ) as f:
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
    print("🚀 Starting pipeline...")

    # Load input_movies.json
    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        movies_data = json.load(f)["movies"]

    catalog_entries = []

    # Process each movie
    for movie in movies_data:
        manifest_name = process_movie(movie)

        if not manifest_name:
            continue

        # GitHub raw URL for manifest
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

    # Update movies.json
    update_catalog(catalog_entries)

    print("\n🎉 DONE!")

