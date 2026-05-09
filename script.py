
# ======================================================
# PART 1
# CONFIG + HELPERS + DOWNLOAD + MEDIA EXTRACTION
# ======================================================

import os
import re
import json
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
TEMP_SOURCE = os.path.join(PROJECT_DIR, "temp_source.bin")
WORK_DIR = os.path.join(PROJECT_DIR, "work")
JSON_DIR = "json_chunks"
MOVIES_DIR = "movies"
MOVIES_FILE = "movies.json"

# Telegram upload bots (round-robin)
UPLOAD_BOTS = [
    "8522819598:AAFd20SQZ5G2CgadEtfATTGi191eacbMeUg",
    "8756092341:AAF84Kg1K3Ji7X16dQy5DETtoo-7BktbFyc",
    "8020744167:AAFw0RbWz_NGGfJNLvlO_O-gAU5xl9VLkgs",
]

# Dedicated bot token used in your Cloudflare Worker for getFile
GETFILE_BOT = "BOT_TOKEN_4"

CHAT_ID = "@stream1806"

# Chunking
CHUNK_SIZE = 2 * 1024 * 1024      # 2 MB binary chunks
MAX_JSON_SIZE = 20 * 1024 * 1024  # Telegram safety limit

# Upload parallelism
MAX_UPLOAD_WORKERS = 4
UPLOAD_RETRIES = 3
CHUNK_UPLOAD_DELAY = 0.1

# Download settings
DOWNLOAD_TIMEOUT = 60

# GitHub raw URL base
GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/"
    "saitarun1806/video-storing/main"
)

# Validate configuration
if not UPLOAD_BOTS:
    raise ValueError("UPLOAD_BOTS cannot be empty")

# Create folders
os.makedirs(WORK_DIR, exist_ok=True)
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


def safe_remove(path: str):
    if os.path.exists(path):
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)


def reset_work_dirs():
    safe_remove(TEMP_SOURCE)
    safe_remove(WORK_DIR)
    safe_remove(JSON_DIR)

    os.makedirs(WORK_DIR, exist_ok=True)
    os.makedirs(JSON_DIR, exist_ok=True)


# ======================================================
# DOWNLOAD USING CURL
# ======================================================
def download_video(url: str) -> bool:
    print(f"⬇️ Downloading: {url}")

    for attempt in range(1, 4):
        try:
            subprocess.run(
                [
                    "curl",
                    "-L",
                    "--fail",
                    url,
                    "-o",
                    TEMP_SOURCE,
                ],
                check=True,
            )

            print("✅ Downloaded source file")
            return True

        except subprocess.CalledProcessError as e:
            print(f"⚠️ Download attempt {attempt} failed: {e}")
            time.sleep(3)

    print("❌ Download failed")
    return False


# ======================================================
# EXTRACT VIDEO ONLY
# Uses stream copy for maximum speed
# ======================================================
def extract_video_only() -> str:
    video_path = os.path.join(WORK_DIR, "video.mp4")

    print("🎬 Extracting video-only stream...")

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        TEMP_SOURCE,
        "-map",
        "0:v:0",
        "-c:v",
        "copy",
        "-an",
        "-movflags",
        "+faststart",
        video_path,
    ]

    subprocess.run(cmd, check=True)

    print("✅ video.mp4 created")
    return video_path


# ======================================================
# GET AUDIO TRACK INFORMATION
# ======================================================
def get_audio_tracks() -> list:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index,codec_name,channels:stream_tags=language,title",
        "-of",
        "json",
        TEMP_SOURCE,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)
    tracks = []

    for i, stream in enumerate(data.get("streams", [])):
        tags = stream.get("tags", {})

        tracks.append({
            "audio_index": i,
            "stream_index": stream.get("index"),
            "language": tags.get("language", f"audio{i}"),
            "title": tags.get("title", ""),
            "codec": stream.get("codec_name"),
            "channels": stream.get("channels"),
        })

    return tracks


# ======================================================
# EXTRACT EACH AUDIO TRACK SEPARATELY
# ======================================================
def extract_audio_tracks() -> list:
    tracks = get_audio_tracks()
    extracted = []

    for track in tracks:
        idx = track["audio_index"]
        output = os.path.join(WORK_DIR, f"audio_{idx}.m4a")

        print(
            f"🎵 Extracting audio {idx} "
            f"({track['language'] or 'unknown'})..."
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            TEMP_SOURCE,
            "-map",
            f"0:a:{idx}",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            output,
        ]

        subprocess.run(cmd, check=True)

        extracted.append({
            "path": output,
            "audio_index": idx,
            "language": track["language"],
            "title": track["title"],
            "codec": "aac",
            "channels": track["channels"],
        })

        print(f"✅ {os.path.basename(output)} created")

    return extracted

# ======================================================
# PART 2
# CHUNKING + TELEGRAM UPLOAD + MANIFESTS + MAIN
# ======================================================

# ======================================================
# GET GENERAL MEDIA INFO
# ======================================================
def get_media_info(path: str) -> dict:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries",
        "format=duration,size",
        "-of", "json",
        path,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)
    fmt = data.get("format", {})

    return {
        "duration": float(fmt.get("duration", 0) or 0),
        "size": int(fmt.get("size", 0) or 0),
    }


# ======================================================
# ENCODE CHUNK AS gzip + base64
# ======================================================
def encode_chunk(data: bytes) -> str:
    return base64.b64encode(
        gzip.compress(data)
    ).decode("utf-8")


# ======================================================
# CREATE JSON CHUNKS FOR ANY FILE
# ======================================================
def create_chunks(file_path: str, prefix: str):
    files = []

    with open(file_path, "rb") as f:
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

            json_str = json.dumps(
                payload,
                separators=(",", ":")
            )

            size_bytes = len(
                json_str.encode("utf-8")
            )

            if size_bytes > MAX_JSON_SIZE:
                raise RuntimeError(
                    f"Chunk JSON too large "
                    f"({size_bytes} bytes)"
                )

            filename = f"{prefix}-chunk_{index:05d}.json"
            filepath = os.path.join(
                JSON_DIR,
                filename
            )

            with open(
                filepath,
                "w",
                encoding="utf-8"
            ) as jf:
                jf.write(json_str)

            files.append({
                "path": filepath,
                "order": index,
                "offset": offset,
                "chunkSize": len(chunk),
            })

            print(
                f"✅ {filename} "
                f"({len(chunk)/1024/1024:.2f} MB)"
            )

            offset += len(chunk)
            index += 1

    return files


# ======================================================
# MULTI-BOT ROUND ROBIN
# ======================================================
def get_upload_bot(index: int) -> str:
    return UPLOAD_BOTS[
        index % len(UPLOAD_BOTS)
    ]


# ======================================================
# UPLOAD SINGLE FILE
# ======================================================
def upload_single(file_info: dict) -> dict:
    file_path = file_info["path"]
    order = file_info["order"]

    bot_token = get_upload_bot(order)

    url = (
        f"https://api.telegram.org/"
        f"bot{bot_token}/sendDocument"
    )

    for attempt in range(
        1,
        UPLOAD_RETRIES + 1
    ):
        try:
            with open(file_path, "rb") as f:
                res = requests.post(
                    url,
                    data={
                        "chat_id": CHAT_ID
                    },
                    files={
                        "document": f
                    },
                    timeout=120,
                )

            data = res.json()

            if data.get("ok"):
                print(
                    f"🚀 Uploaded chunk {order} "
                    f"using bot "
                    f"#{(order % len(UPLOAD_BOTS)) + 1}"
                )

                return {
                    "order": order,
                    "offset": file_info["offset"],
                    "chunkSize": file_info["chunkSize"],
                    "file_id": data["result"]["document"]["file_id"],
                    "bot_index": (
                        order % len(UPLOAD_BOTS)
                    ),
                }

            print(
                f"❌ Telegram error "
                f"for chunk {order}: {data}"
            )

        except Exception as e:
            print(
                f"⚠️ Upload attempt "
                f"{attempt} failed "
                f"for chunk {order}: {e}"
            )
            time.sleep(2)

    raise RuntimeError(
        f"Failed to upload chunk {order}"
    )


# ======================================================
# PARALLEL UPLOADS
# ======================================================
def upload_chunks_parallel(chunk_files):
    results = []

    with ThreadPoolExecutor(
        max_workers=MAX_UPLOAD_WORKERS
    ) as executor:

        futures = [
            executor.submit(
                upload_single,
                info
            )
            for info in chunk_files
        ]

        for future in as_completed(
            futures
        ):
            results.append(
                future.result()
            )
            time.sleep(
                CHUNK_UPLOAD_DELAY
            )

    results.sort(
        key=lambda x: x["order"]
    )

    return results


# ======================================================
# BUILD COMPONENT MANIFEST
# ======================================================
def build_component_manifest(
    component_type: str,
    info: dict,
    chunks: list,
    extra: dict = None
):
    total_chunks = len(chunks)
    duration = info["duration"]

    seconds_per_chunk = (
        duration / total_chunks
        if total_chunks else 0
    )

    manifest = {
        "type": component_type,
        "mimeType": (
            "video/mp4"
            if component_type == "video"
            else "audio/mp4"
        ),
        "encoding": "gzip+base64",
        "chunkSize": CHUNK_SIZE,
        "totalSize": info["size"],
        "duration": duration,
        "totalChunks": total_chunks,
        "estimatedChunkDuration": (
            seconds_per_chunk
        ),
        "seek": {
            "type": "estimated",
            "secondsPerChunk": (
                seconds_per_chunk
            ),
            "formula": (
                "chunkIndex = "
                "floor(seconds / "
                "secondsPerChunk)"
            ),
        },
        "chunks": chunks,
    }

    if extra:
        manifest.update(extra)

    return manifest


# ======================================================
# SAVE JSON
# ======================================================
def save_json(path: str, data: dict):
    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )


# ======================================================
# PROCESS ONE MOVIE
# ======================================================
def process_movie(movie: dict):
    name = movie["name"]
    year = movie["year"]
    url = movie["url"]

    print(
        f"\\n🎬 Processing: "
        f"{name} ({year})"
    )

    safe = clean_name(name)
    reset_work_dirs()

    # 1. Download source
    if not download_video(url):
        print("⛔ Skipping movie")
        return None

    # 2. Extract video-only
    video_path = extract_video_only()

    # 3. Extract all audio tracks
    audio_files = extract_audio_tracks()

    # --------------------------
    # VIDEO MANIFEST
    # --------------------------
    print("📦 Chunking video...")
    video_chunk_files = create_chunks(
        video_path,
        f"{safe}-video"
    )

    print("📤 Uploading video...")
    video_uploaded = upload_chunks_parallel(
        video_chunk_files
    )

    video_info = get_media_info(
        video_path
    )

    video_manifest = (
        build_component_manifest(
            "video",
            video_info,
            video_uploaded,
        )
    )

    video_manifest_name = (
        f"{safe}_{year}_video.json"
    )

    save_json(
        os.path.join(
            MOVIES_DIR,
            video_manifest_name
        ),
        video_manifest,
    )

    # --------------------------
    # AUDIO MANIFESTS
    # --------------------------
    master_audio_tracks = []

    for audio in audio_files:
        idx = audio["audio_index"]

        print(
            f"📦 Chunking audio "
            f"{idx}..."
        )

        audio_chunk_files = (
            create_chunks(
                audio["path"],
                f"{safe}-audio_{idx}"
            )
        )

        print(
            f"📤 Uploading audio "
            f"{idx}..."
        )

        audio_uploaded = (
            upload_chunks_parallel(
                audio_chunk_files
            )
        )

        audio_info = get_media_info(
            audio["path"]
        )

        audio_manifest = (
            build_component_manifest(
                "audio",
                audio_info,
                audio_uploaded,
                extra={
                    "language": (
                        audio["language"]
                    ),
                    "title": (
                        audio["title"]
                    ),
                    "channels": (
                        audio["channels"]
                    ),
                },
            )
        )

        audio_manifest_name = (
            f"{safe}_{year}"
            f"_audio_{idx}.json"
        )

        save_json(
            os.path.join(
                MOVIES_DIR,
                audio_manifest_name
            ),
            audio_manifest,
        )

        master_audio_tracks.append({
            "audio_index": idx,
            "language": (
                audio["language"]
            ),
            "title": (
                audio["title"]
            ),
            "channels": (
                audio["channels"]
            ),
            "manifest": (
                f"{GITHUB_RAW_BASE}/"
                f"movies/"
                f"{audio_manifest_name}"
            ),
        })

    # --------------------------
    # MASTER MOVIE MANIFEST
    # --------------------------
    master_manifest = {
        "movie": name,
        "year": year,
        "videoManifest": (
            f"{GITHUB_RAW_BASE}/"
            f"movies/"
            f"{video_manifest_name}"
        ),
        "audioTracks": (
            master_audio_tracks
        ),
    }

    master_manifest_name = (
        f"{safe}_{year}.json"
    )

    save_json(
        os.path.join(
            MOVIES_DIR,
            master_manifest_name
        ),
        master_manifest,
    )

    print(
        f"📝 Saved → "
        f"{master_manifest_name}"
    )

    # Cleanup temp files
    reset_work_dirs()

    return master_manifest_name


# ======================================================
# UPDATE movies.json
# ======================================================
def update_catalog(entries):
    catalog = {"movies": []}

    if os.path.exists(
        MOVIES_FILE
    ):
        try:
            with open(
                MOVIES_FILE,
                "r",
                encoding="utf-8"
            ) as f:
                catalog = json.load(f)
        except Exception:
            catalog = {
                "movies": []
            }

    existing = {
        (
            item.get("name"),
            item.get("year")
        ): item
        for item in catalog.get(
            "movies",
            []
        )
    }

    for entry in entries:
        if entry:
            existing[
                (
                    entry["name"],
                    entry["year"]
                )
            ] = entry

    catalog["movies"] = list(
        existing.values()
    )

    catalog["movies"].sort(
        key=lambda x: (
            x["name"].lower(),
            x["year"]
        )
    )

    save_json(
        MOVIES_FILE,
        catalog
    )

    print(
        "📚 movies.json updated"
    )


# ======================================================
# MAIN
# ======================================================
def main():
    print(
        "🚀 Starting pipeline..."
    )

    if not os.path.exists(
        INPUT_FILE
    ):
        raise FileNotFoundError(
            f"{INPUT_FILE} not found"
        )

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        movies_data = json.load(
            f
        )["movies"]

    catalog_entries = []

    for movie in movies_data:
        manifest_name = (
            process_movie(movie)
        )

        if not manifest_name:
            continue

        manifest_url = (
            f"{GITHUB_RAW_BASE}/"
            f"movies/"
            f"{manifest_name}"
        )

        catalog_entries.append({
            "name": movie["name"],
            "year": movie["year"],
            "manifest": manifest_url,
        })

    update_catalog(
        catalog_entries
    )

    print("\\n🎉 DONE!")


# ======================================================
# ENTRY POINT
# ======================================================
if __name__ == "__main__":
    main()

