# ======================================================
# TELEGRAM DIRECT CHUNK MOVIE STORAGE SYSTEM
# NO FFMPEG
# NO HLS
# NO RE-ENCODING
# ORIGINAL QUALITY PRESERVED
# ======================================================

import os
import json
import requests
import time
import re
import shutil

from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed
)

# ======================================================
# CONFIG
# ======================================================

INPUT_FILE = "input_movies.json"

PROJECT_DIR = "."

TEMP_VIDEO = os.path.join(
    PROJECT_DIR,
    "temp.mp4"
)

CHUNKS_DIR = os.path.join(
    PROJECT_DIR,
    "chunks"
)

MOVIES_DIR = os.path.join(
    PROJECT_DIR,
    "movies"
)

MOVIES_FILE = "movies.json"

# ======================================================
# TELEGRAM CONFIG
# ======================================================

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

# ======================================================
# WORKER URL
# ======================================================

WORKER_URL = "https://frosty-snow-1291.database1806.workers.dev"

# ======================================================
# CHUNK SETTINGS
# ======================================================

# 45MB chunks
CHUNK_SIZE = 10 * 1024 * 1024

# ======================================================
# PARALLEL SETTINGS
# ======================================================

MAX_WORKERS_PER_BOT = 4

# ======================================================
# CREATE FOLDERS
# ======================================================

os.makedirs(PROJECT_DIR, exist_ok=True)
os.makedirs(CHUNKS_DIR, exist_ok=True)
os.makedirs(MOVIES_DIR, exist_ok=True)

# ======================================================
# HELPERS
# ======================================================

def clean_name(name):

    name = name.strip().lower()

    name = re.sub(
        r"[^a-z0-9]+",
        "_",
        name
    )

    name = re.sub(
        r"_+",
        "_",
        name
    )

    return name.strip("_")


# ======================================================
# DOWNLOAD VIDEO
# ======================================================

def download_video(url):

    print(f"\n⬇️ Downloading:\n{url}")

    for attempt in range(3):

        try:

            with requests.get(
                url,
                stream=True,
                timeout=30
            ) as r:

                if r.status_code != 200:
                    raise Exception(
                        f"Status {r.status_code}"
                    )

                total = 0

                with open(TEMP_VIDEO, "wb") as f:

                    for chunk in r.iter_content(
                        1024 * 1024
                    ):

                        if chunk:

                            f.write(chunk)

                            total += len(chunk)

                            print(
                                f"\r📥 "
                                f"{total / (1024*1024):.2f} MB",
                                end=""
                            )

            print("\n✅ Download complete")

            return True

        except Exception as e:

            print(
                f"\n⚠️ Retry "
                f"{attempt+1}: {e}"
            )

            time.sleep(2)

    print("❌ Download failed")

    return False


# ======================================================
# CREATE DIRECT CHUNKS
# ======================================================

def create_chunks(movie_name):

    print("\n📦 Creating chunks...")

    # Remove old chunks
    if os.path.exists(CHUNKS_DIR):
        shutil.rmtree(CHUNKS_DIR)

    os.makedirs(CHUNKS_DIR, exist_ok=True)

    chunk_files = []

    total_size = os.path.getsize(TEMP_VIDEO)

    print(
        f"🎞 Video Size: "
        f"{total_size / (1024*1024):.2f} MB"
    )

    with open(TEMP_VIDEO, "rb") as f:

        index = 0

        while True:

            data = f.read(CHUNK_SIZE)

            if not data:
                break

            chunk_path = os.path.join(
                CHUNKS_DIR,
                f"chunk_{index:05d}.bin"
            )

            with open(chunk_path, "wb") as out:
                out.write(data)

            chunk_size_mb = (
                len(data) / (1024*1024)
            )

            print(
                f"📦 Chunk {index} | "
                f"{chunk_size_mb:.2f} MB"
            )

            chunk_files.append(chunk_path)

            index += 1

    print(
        f"\n✅ Created "
        f"{len(chunk_files)} chunks"
    )

    return chunk_files


# ======================================================
# SELECT BOT
# ======================================================

def get_upload_bot(index):

    return UPLOAD_BOTS[
        index % len(UPLOAD_BOTS)
    ]


# ======================================================
# UPLOAD SINGLE CHUNK
# ======================================================

def upload_chunk(file_path, index):

    bot_token = get_upload_bot(index)

    api_url = (
        f"https://api.telegram.org/"
        f"bot{bot_token}/sendDocument"
    )

    for attempt in range(3):

        try:

            with open(file_path, "rb") as f:

                response = requests.post(
                    api_url,
                    data={
                        "chat_id": CHAT_ID
                    },
                    files={
                        "document": f
                    },
                    timeout=300
                )

            data = response.json()

            if data.get("ok"):

                file_id = (
                    data["result"]
                    ["document"]
                    ["file_id"]
                )

                print(
                    f"🚀 Uploaded "
                    f"chunk {index}"
                )

                return {
                    "index": index,
                    "file_id": file_id
                }

            print(
                f"❌ Upload error:\n{data}"
            )

            # Telegram rate limit
            if data.get("error_code") == 429:

                retry_after = (
                    data.get(
                        "parameters",
                        {}
                    ).get(
                        "retry_after",
                        5
                    )
                )

                print(
                    f"⏳ Waiting "
                    f"{retry_after}s"
                )

                time.sleep(retry_after)

        except Exception as e:

            print(
                f"⚠️ Upload retry "
                f"{attempt+1}: {e}"
            )

            time.sleep(2)

    return None


# ======================================================
# UPLOAD ALL CHUNKS
# ======================================================

def upload_all_chunks(chunk_files):

    total_files = len(chunk_files)

    total_workers = (
        MAX_WORKERS_PER_BOT *
        len(UPLOAD_BOTS)
    )

    print(
        f"\n🚀 Uploading "
        f"{total_files} chunks"
    )

    uploaded = {}

    pending = list(range(total_files))

    round_number = 1

    while pending:

        print(
            f"\n🔄 Upload Round "
            f"{round_number}"
        )

        failed = []

        workers = min(
            total_workers,
            len(pending)
        )

        with ThreadPoolExecutor(
            max_workers=workers
        ) as executor:

            futures = {

                executor.submit(
                    upload_chunk,
                    chunk_files[index],
                    index
                ): index

                for index in pending
            }

            for future in as_completed(futures):

                index = futures[future]

                try:

                    result = future.result()

                    if result:
                        uploaded[index] = result
                    else:
                        failed.append(index)

                except Exception as e:

                    print(
                        f"❌ Failed "
                        f"chunk {index}: {e}"
                    )

                    failed.append(index)

        pending = failed

        print(
            f"✅ Uploaded: "
            f"{len(uploaded)}/"
            f"{total_files}"
        )

        if pending:

            print(
                "⏳ Waiting "
                "5 seconds..."
            )

            time.sleep(5)

        round_number += 1

    print("\n🎉 All chunks uploaded!")

    return [
        uploaded[i]
        for i in sorted(uploaded.keys())
    ]


# ======================================================
# CREATE MOVIE METADATA
# ======================================================

def create_movie_metadata(
    movie,
    uploaded_chunks
):

    safe_name = clean_name(
        movie["name"]
    )

    metadata_path = os.path.join(
        MOVIES_DIR,
        f"{safe_name}.json"
    )

    metadata = {

        "name": movie["name"],

        "year": movie["year"],

        "original_url": movie["url"],

        "chunk_size": CHUNK_SIZE,

        "total_chunks": len(uploaded_chunks),

        "chunks": []
    }

    for chunk in uploaded_chunks:

        metadata["chunks"].append({

            "index": chunk["index"],

            "file_id": chunk["file_id"],

            "url":
            f"{WORKER_URL}/file_by_id/"
            f"{requests.utils.quote(chunk['file_id'], safe='')}"

        })

    with open(
        metadata_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            metadata,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(
        f"📝 Saved metadata:\n"
        f"{metadata_path}"
    )

    return safe_name


# ======================================================
# PROCESS MOVIE
# ======================================================

def process_movie(movie):

    print(
        f"\n🎬 PROCESSING:\n"
        f"{movie['name']} "
        f"({movie['year']})"
    )

    # Remove previous temp video
    if os.path.exists(TEMP_VIDEO):
        os.remove(TEMP_VIDEO)

    # Download movie
    if not download_video(movie["url"]):

        print("⛔ Download failed")

        return None

    # Create chunks
    chunk_files = create_chunks(
        movie["name"]
    )

    # Upload chunks
    uploaded_chunks = upload_all_chunks(
        chunk_files
    )

    # Create metadata
    safe_name = create_movie_metadata(
        movie,
        uploaded_chunks
    )

    return safe_name


# ======================================================
# UPDATE movies.json
# ======================================================

def update_catalog(entries):

    if os.path.exists(MOVIES_FILE):

        with open(
            MOVIES_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

    else:

        data = {
            "movies": []
        }

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

    data["movies"].sort(

        key=lambda x: (
            x["name"].lower(),
            x["year"]
        )
    )

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


# ======================================================
# MAIN
# ======================================================

if __name__ == "__main__":

    print(
        "\n🚀 DIRECT CHUNK "
        "MOVIE STORAGE SYSTEM\n"
    )

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        movies_data = json.load(f)["movies"]

    catalog_entries = []

    for movie in movies_data:

        safe_name = process_movie(movie)

        if not safe_name:
            continue

        playlist_url = (
            "https://raw.githubusercontent.com/"
            "saitarun1806/"
            "video-storing/main/"
            f"movies/{safe_name}.json"
        )

        catalog_entries.append({

            "name": movie["name"],

            "year": movie["year"],

            "playlist": playlist_url
        })

    update_catalog(catalog_entries)

    print("\n🎉 DONE!")
