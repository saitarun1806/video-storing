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

JSON_DIR = os.path.join(PROJECT_DIR, "json_chunks")
MOVIES_DIR = "movies"
MOVIES_FILE = "movies.json"

# ======================
# TELEGRAM CONFIG (MULTI-BOT)
# Replace these with NEW bot tokens
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
CHAT_ID = "@stream1806" # or channel ID
# ======================
# CHUNK SETTINGS
# ======================
MAX_JSON_SIZE = 20 * 1024 * 1024      # 20 MB max JSON size
INITIAL_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB binary chunks

# ======================
# PARALLEL UPLOAD SETTINGS
# ======================
# Recommended: 6-8 workers per bot to avoid Telegram 429 errors
MAX_WORKERS_PER_BOT = 6

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
# DOWNLOAD VIDEO
# ======================
def download_video(url):
    """
    Download source video to TEMP_VIDEO with retries.
    """
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
# ENCODE DATA
# ======================
def encode(data):
    """
    Compress binary data with gzip and encode to base64.
    """
    compressed = gzip.compress(data)
    return base64.b64encode(compressed).decode("utf-8")


# ======================
# CREATE JSON CHUNKS
# ======================
def create_chunks(movie_name):
    """
    Split TEMP_VIDEO into independently playable MP4 parts
    of approximately 4 MB each, then convert each MP4 part
    into gzip + base64 JSON.

    This allows the browser to:
    - Play after downloading the first chunk
    - Download remaining chunks in the background
    """

    files = []
    safe_name = clean_name(movie_name)

    # Temporary folder for MP4 segments
    segment_dir = tempfile.mkdtemp(prefix="mp4_parts_")

    try:
        print("🎬 Splitting video into ~4 MB MP4 parts...")

        # Get total duration using ffprobe
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                TEMP_VIDEO
            ],
            capture_output=True,
            text=True,
            check=True
        )

        total_duration = float(result.stdout.strip())
        total_size = os.path.getsize(TEMP_VIDEO)

        target_size = 4 * 1024 * 1024  # 4 MB target
        num_parts = max(1, int(total_size / target_size))
        segment_time = max(1, total_duration / num_parts)

        print(f"📦 File size: {total_size / (1024**3):.2f} GB")
        print(f"⏱ Duration: {total_duration:.2f} sec")
        print(f"🔢 Estimated parts: {num_parts}")
        print(f"⏳ Segment time: {segment_time:.2f} sec")

        # Output pattern
        segment_pattern = os.path.join(
            segment_dir,
            "part_%04d.mp4"
        )

        # Split video WITHOUT re-encoding (very fast)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", TEMP_VIDEO,
                "-c", "copy",
                "-map", "0",
                "-f", "segment",
                "-segment_time", str(segment_time),
                "-reset_timestamps", "1",
                "-movflags", "+faststart",
                segment_pattern
            ],
            check=True
        )

        print("✅ MP4 splitting complete")

        # Find generated MP4 parts
        part_files = sorted(
            f for f in os.listdir(segment_dir)
            if f.endswith(".mp4")
        )

        # Convert each MP4 part to JSON
        for index, part_name in enumerate(part_files):
            part_path = os.path.join(segment_dir, part_name)

            with open(part_path, "rb") as f:
                mp4_data = f.read()

            encoded = encode(mp4_data)

            payload = {
                "order": index,
                "encoding": "gzip+base64",
                "segmentType": "mp4",
                "data": encoded
            }

            json_str = json.dumps(
                payload,
                separators=(",", ":")
            )

            filename = f"{safe_name}-chunk_{index:04d}.json"
            filepath = os.path.join(JSON_DIR, filename)

            with open(filepath, "w", encoding="utf-8") as jf:
                jf.write(json_str)

            files.append(filepath)

            part_size_mb = len(mp4_data) / (1024 * 1024)

            print(
                f"✅ {filename} "
                f"({part_size_mb:.2f} MB MP4)"
            )

        print(f"🎉 Created {len(files)} MP4-based JSON chunks")
        return files

    finally:
        # Clean temporary segment directory
        shutil.rmtree(segment_dir, ignore_errors=True)
# ======================================================
# PART 2
# MULTI-BOT UPLOAD + GUARANTEED RETRIES + MANIFEST + CATALOG + MAIN
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
# UPLOAD SINGLE CHUNK
# ======================
def upload(file_path, chunk_index):
    """
    Upload one JSON chunk to Telegram.
    Handles retries and Telegram 429 rate limits.
    Returns Telegram file_id on success, otherwise None.
    """
    bot_token = get_upload_bot(chunk_index)
    api_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

    for attempt in range(3):
        try:
            with open(file_path, "rb") as f:
                response = requests.post(
                    api_url,
                    data={"chat_id": CHAT_ID},
                    files={"document": f},
                    timeout=120
                )

            data = response.json()

            # Success
            if data.get("ok"):
                bot_number = (chunk_index % len(UPLOAD_BOTS)) + 1

                print(
                    f"🚀 Uploaded chunk "
                    f"{chunk_index} "
                    f"using bot #{bot_number}"
                )

                return data["result"]["document"]["file_id"]

            # Telegram rate limit
            print(
                f"❌ Upload error for chunk "
                f"{chunk_index}: {data}"
            )

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
                f"chunk {chunk_index}: {e}"
            )

            time.sleep(2)

    return None


# ======================
# UPLOAD ALL CHUNKS (GUARANTEED)
# ======================
# ======================
# UPLOAD ALL CHUNKS (PENDING LIST METHOD)
# ======================
def upload_all_chunks(json_files):
    """
    Upload all chunks and keep retrying until EVERY chunk is uploaded.

    Logic:
    1. Create a list containing all chunk numbers.
       Example: [0, 1, 2, 3, 4, ...]
    2. When a chunk uploads successfully, remove its number from the list.
    3. If a chunk fails, keep its number in the list.
    4. After one upload round, retry ONLY the remaining chunk numbers.
    5. Continue until the list becomes empty.

    This guarantees:
    - No chunk is missed
    - Failed chunks are retried indefinitely
    - Process ends only when all chunks are uploaded
    """

    total_files = len(json_files)
    total_workers = MAX_WORKERS_PER_BOT * len(UPLOAD_BOTS)

    print(f"🚀 Starting parallel uploads with {total_workers} workers...")
    print(f"📦 Total chunks to upload: {total_files}")

    # Dictionary to store successful uploads
    uploaded = {}

    # LIST OF CHUNK NUMBERS STILL TO UPLOAD
    # Example: [0, 1, 2, 3, 4, ...]
    pending_chunks = list(range(total_files))

    round_number = 1

    # Continue until the list becomes empty
    while pending_chunks:
        print(f"\n🔄 Upload Round {round_number}")
        print(f"⏳ Remaining chunks: {len(pending_chunks)}")
        print(f"📋 Pending list: {pending_chunks[:20]}{' ...' if len(pending_chunks) > 20 else ''}")

        # Use only as many workers as needed
        workers = min(total_workers, len(pending_chunks))

        # Temporary list for chunks that fail this round
        failed_chunks = []

        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit only pending chunks
            futures = {
                executor.submit(upload, json_files[index], index): index
                for index in pending_chunks
            }

            for future in as_completed(futures):
                index = futures[future]

                try:
                    file_id = future.result()

                    if file_id:
                        # Save successful upload info
                        uploaded[index] = {
                            "order": index,
                            "file_id": file_id,
                            "bot_index": index % len(UPLOAD_BOTS)
                        }

                        # Success -> do NOT add back to pending list
                        print(f"✅ Removed chunk {index} from pending list")
                    else:
                        # Failed -> keep for next round
                        failed_chunks.append(index)

                except Exception as e:
                    print(f"❌ Failed chunk {index}: {e}")
                    failed_chunks.append(index)

        # Replace pending list with only failed chunks
        pending_chunks = sorted(failed_chunks)

        print(
            f"✅ Uploaded: {len(uploaded)}/{total_files} | "
            f"Remaining in pending list: {len(pending_chunks)}"
        )

        # Wait before retrying remaining chunks
        if pending_chunks:
            print("⏳ Waiting 5 seconds before retrying remaining chunks...")
            time.sleep(5)

        round_number += 1

    # Build ordered chunk list
    chunks = [uploaded[i] for i in sorted(uploaded.keys())]

    # Final verification
    if len(chunks) != total_files:
        raise Exception(
            f"Upload incomplete! Expected {total_files}, got {len(chunks)}"
        )

    print(f"\n🎉 All {total_files} chunks uploaded successfully!")
    print("📋 Pending list is empty.")
    return chunks


# ======================
# PROCESS ONE MOVIE
# ======================
def process_movie(movie):
    name = movie["name"]
    year = movie["year"]
    source_url = movie["url"]

    print(f"\n🎬 Processing: {name} ({year})")

    safe = clean_name(name)
    manifest_name = f"{safe}_{year}.json"
    manifest_path = os.path.join(MOVIES_DIR, manifest_name)

    # Remove previous temp video
    if os.path.exists(TEMP_VIDEO):
        os.remove(TEMP_VIDEO)

    # Download source video
    if not download_video(source_url):
        print("⛔ Skipping movie")
        return None

    # Create JSON chunk files
    json_files = create_chunks(name)

    # Guaranteed upload of all chunks
    chunks = upload_all_chunks(json_files)

    if not chunks:
        print("❌ No chunks uploaded successfully")
        return None

    # Create manifest
    manifest = {
        "movie": name,
        "year": year,
        "chunkDuration": 5,
        "totalChunks": len(chunks),
        "chunks": chunks
    }

    # Save manifest
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(
            manifest,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(f"📝 Saved → movies/{manifest_name}")
    return manifest_name


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
    print("🚀 Starting pipeline...")

    # Load input_movies.json
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        movies_data = json.load(f)["movies"]

    catalog_entries = []

    # Process each movie
    for movie in movies_data:
        manifest_name = process_movie(movie)

        if not manifest_name:
            continue

        # Update this to your actual GitHub repository path
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

    # Update master catalog
    update_catalog(catalog_entries)

    print("\n🎉 DONE!")
