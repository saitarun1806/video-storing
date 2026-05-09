import os
import re
import json
import math
import base64
import gzip
import time
import shutil
import requests
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

# ======================================================
# CONFIG
# ======================================================
INPUT_FILE = "input_movies.json"

# Output paths
PROJECT_DIR = "."
TEMP_SOURCE = os.path.join(PROJECT_DIR, "temp_source.bin")  # raw download
TEMP_VIDEO = os.path.join(PROJECT_DIR, "temp.mp4")          # browser-ready MP4
JSON_DIR = "json_chunks"
MOVIES_DIR = "movies"
MOVIES_FILE = "movies.json"

# Telegram
UPLOAD_BOTS = [
    "8522819598:AAFd20SQZ5G2CgadEtfATTGi191eacbMeUg",
    "8756092341:AAF84Kg1K3Ji7X16dQy5DETtoo-7BktbFyc",
    "8020744167:AAFw0RbWz_NGGfJNLvlO_O-gAU5xl9VLkgs",
]
CHAT_ID = "@stream1806"

# Chunking
CHUNK_SIZE = 2 * 1024 * 1024           # 2 MB binary chunks
MAX_JSON_SIZE = 20 * 1024 * 1024       # Telegram JSON file size safety

# Upload parallelism
MAX_UPLOAD_WORKERS = 4                 # 4 uploads in parallel
UPLOAD_RETRIES = 3

# GitHub raw base URL
GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/"
    "saitarun1806/video-storing/main"
)

# Request settings
DOWNLOAD_TIMEOUT = 60
CHUNK_UPLOAD_DELAY = 0.1

# ======================================================
# SETUP
# ======================================================
os.makedirs(JSON_DIR, exist_ok=True)
os.makedirs(MOVIES_DIR, exist_ok=True)


# ======================================================
# HELPERS
# ======================================================
def clean_name(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("_")


# ======================================================
# DOWNLOAD VIDEO
# ======================================================
def download_video(url: str) -> bool:
    print(f"⬇️ Downloading: {url}")

    for attempt in range(1, 4):
        try:
            with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as r:
                r.raise_for_status()

                with open(TEMP_SOURCE, "wb") as f:
                    for chunk in r.iter_content(1024 * 1024):
                        if chunk:
                            f.write(chunk)

            print("✅ Downloaded source file")
            return True

        except Exception as e:
            print(f"⚠️ Download attempt {attempt} failed: {e}")
            time.sleep(3)

    print("❌ Download failed")
    return False


# ======================================================
# RE-ENCODE TO BROWSER-COMPATIBLE MP4
# PRESERVES ALL AUDIO + SUBTITLE STREAMS USING -map 0
# ======================================================
def reencode_video() -> bool:
    print("🎞️ Re-encoding to browser-compatible MP4 (preserving all streams)...")

    if os.path.exists(TEMP_VIDEO):
        os.remove(TEMP_VIDEO)

    cmd = [
        "ffmpeg",
        "-y",
        "-i", TEMP_SOURCE,
        "-map", "0",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "160k",
        "-c:s", "mov_text",
        "-movflags", "+faststart",
        TEMP_VIDEO,
    ]

    try:
        subprocess.run(cmd, check=True)
        print("✅ Re-encoded to temp.mp4")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg failed: {e}")
        return False


# ======================================================
# MEDIA INFO (duration, streams)
# ======================================================
def get_media_info(path: str) -> dict:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries",
        "format=duration,size:stream=index,codec_type,codec_name,channels:stream_tags=language,title",
        "-of", "json",
        path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)

    duration = float(info.get("format", {}).get("duration", 0) or 0)
    size = int(info.get("format", {}).get("size", 0) or 0)

    audio_tracks = []
    subtitle_tracks = []

    for stream in info.get("streams", []):
        tags = stream.get("tags", {})
        entry = {
            "index": stream.get("index"),
            "codec": stream.get("codec_name"),
            "language": tags.get("language", "und"),
            "title": tags.get("title", ""),
        }

        if stream.get("codec_type") == "audio":
            entry["channels"] = stream.get("channels")
            audio_tracks.append(entry)
        elif stream.get("codec_type") == "subtitle":
            subtitle_tracks.append(entry)

    return {
        "duration": duration,
        "size": size,
        "audioTracks": audio_tracks,
        "subtitleTracks": subtitle_tracks,
    }


# ======================================================
# ENCODE CHUNK AS gzip + base64
# ======================================================
def encode_chunk(data: bytes) -> str:
    return base64.b64encode(gzip.compress(data)).decode("utf-8")


# ======================================================
# CREATE 2 MB JSON CHUNKS
# ======================================================
def create_chunks(movie_name: str):
    safe_name = clean_name(movie_name)
    files = []

    with open(TEMP_VIDEO, "rb") as f:
        index = 0
        offset = 0

        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break

            encoded = encode_chunk(chunk)

            payload = {
                "order": index,
                "offset": offset,
                "chunkSize": len(chunk),
                "encoding": "gzip+base64",
                "data": encoded,
            }

            json_str = json.dumps(payload, separators=(",", ":"))
            size_bytes = len(json_str.encode("utf-8"))

            if size_bytes > MAX_JSON_SIZE:
                raise RuntimeError(
                    f"Chunk JSON too large ({size_bytes} bytes). Reduce CHUNK_SIZE."
                )

            filename = f"{safe_name}-chunk_{index:05d}.json"
            filepath = os.path.join(JSON_DIR, filename)

            with open(filepath, "w", encoding="utf-8") as jf:
                jf.write(json_str)

            files.append({
                "path": filepath,
                "order": index,
                "offset": offset,
                "chunkSize": len(chunk),
            })

            print(f"✅ {filename} ({len(chunk)/1024/1024:.2f} MB binary)")

            offset += len(chunk)
            index += 1

    return files


# ======================================================
# MULTI-BOT ROUND ROBIN
# ======================================================
def get_upload_bot(index: int) -> str:
    return UPLOAD_BOTS[index % len(UPLOAD_BOTS)]


# ======================================================
# UPLOAD SINGLE FILE
# ======================================================
def upload_single(file_info: dict) -> dict:
    file_path = file_info["path"]
    order = file_info["order"]

    bot_token = get_upload_bot(order)
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

    for attempt in range(1, UPLOAD_RETRIES + 1):
        try:
            with open(file_path, "rb") as f:
                res = requests.post(
                    url,
                    data={"chat_id": CHAT_ID},
                    files={"document": f},
                    timeout=120,
                )

            data = res.json()

            if data.get("ok"):
                print(
                    f"🚀 Uploaded chunk {order} using bot "
                    f"#{(order % len(UPLOAD_BOTS)) + 1}"
                )

                return {
                    "order": order,
                    "offset": file_info["offset"],
                    "chunkSize": file_info["chunkSize"],
                    "file_id": data["result"]["document"]["file_id"],
                    "bot_index": order % len(UPLOAD_BOTS),
                }

            print(f"❌ Telegram error for chunk {order}: {data}")

        except Exception as e:
            print(f"⚠️ Upload attempt {attempt} failed for chunk {order}: {e}")
            time.sleep(2)

    raise RuntimeError(f"Failed to upload chunk {order}")


# ======================================================
# PARALLEL UPLOADS
# ======================================================
def upload_chunks_parallel(chunk_files):
    results = []

    with ThreadPoolExecutor(max_workers=MAX_UPLOAD_WORKERS) as executor:
        futures = [executor.submit(upload_single, info) for info in chunk_files]

        for future in as_completed(futures):
            results.append(future.result())
            time.sleep(CHUNK_UPLOAD_DELAY)

    results.sort(key=lambda x: x["order"])
    return results


# ======================================================
# PROCESS ONE MOVIE
# ======================================================
def process_movie(movie: dict):
    name = movie["name"]
    year = movie["year"]
    url = movie["url"]

    print(f"\n🎬 Processing: {name} ({year})")

    safe = clean_name(name)
    manifest_name = f"{safe}_{year}.json"
    manifest_path = os.path.join(MOVIES_DIR, manifest_name)

    # Cleanup previous temp files
    for temp in [TEMP_SOURCE, TEMP_VIDEO]:
        if os.path.exists(temp):
            os.remove(temp)

    # Download
    if not download_video(url):
        print("⛔ Skipping movie")
        return None

    # Re-encode
    if not reencode_video():
        print("⛔ Re-encode failed")
        return None

    # Media info
    info = get_media_info(TEMP_VIDEO)

    # Chunk creation
       # Chunk creation
    chunk_files = create_chunks(name)

    # Upload in parallel with multiple bots
    uploaded_chunks = upload_chunks_parallel(chunk_files)

    # Estimated seek metadata
    total_chunks = len(uploaded_chunks)
    duration = info["duration"]
    estimated_chunk_duration = duration / total_chunks if total_chunks else 0

    # Manifest
    manifest = {
        "movie": name,
        "year": year,
        "mimeType": "video/mp4",
        "encoding": "gzip+base64",
        "chunkSize": CHUNK_SIZE,
        "totalSize": info["size"],
        "duration": duration,
        "totalChunks": total_chunks,
        "estimatedChunkDuration": estimated_chunk_duration,
        "audioTracks": info["audioTracks"],
        "subtitleTracks": info["subtitleTracks"],
        "seek": {
            "type": "estimated",
            "secondsPerChunk": estimated_chunk_duration,
            "formula": "chunkIndex = floor(seconds / secondsPerChunk)"
        },
        "chunks": uploaded_chunks,
    }

    # Save manifest
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"📝 Saved → {manifest_path}")

    # Optional cleanup of temporary JSON chunk files
    shutil.rmtree(JSON_DIR)
    os.makedirs(JSON_DIR, exist_ok=True)

    return manifest_name


# ======================================================
# UPDATE movies.json
# ======================================================
def update_catalog(entries):
    catalog = {"movies": []}

    # Load existing movies.json if available
    if os.path.exists(MOVIES_FILE):
        try:
            with open(MOVIES_FILE, "r", encoding="utf-8") as f:
                catalog = json.load(f)
        except Exception:
            catalog = {"movies": []}

    # Create lookup to avoid duplicates
    existing = {
        (item.get("name"), item.get("year")): item
        for item in catalog.get("movies", [])
    }

    # Update or insert entries
    for entry in entries:
        if entry:
            existing[(entry["name"], entry["year"])] = entry

    # Convert back to list and sort
    catalog["movies"] = list(existing.values())
    catalog["movies"].sort(
        key=lambda x: (x["name"].lower(), x["year"])
    )

    # Save movies.json
    with open(MOVIES_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    print("📚 movies.json updated")


# ======================================================
# MAIN
# ======================================================
def main():
    print("🚀 Starting pipeline...")

    # Load input file
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        movies_data = json.load(f)["movies"]

    catalog_entries = []

    # Process each movie
    for movie in movies_data:
        manifest_name = process_movie(movie)

        # Skip failed movies
        if not manifest_name:
            continue

        # Create GitHub raw URL for manifest
        manifest_url = f"{GITHUB_RAW_BASE}/movies/{manifest_name}"

        # Add to catalog
        catalog_entries.append({
            "name": movie["name"],
            "year": movie["year"],
            "manifest": manifest_url,
        })

    # Update movies.json
    update_catalog(catalog_entries)

    print("\n🎉 DONE!")


# ======================================================
# ENTRY POINT
# ======================================================
if __name__ == "__main__":
    main()
   
