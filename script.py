# ======================================================
# TELEGRAM DASH (.m4s) STREAMING SYSTEM
# YOUTUBE STYLE STREAMING
# MULTI AUDIO SUPPORT
# NO RE-ENCODING
# ORIGINAL QUALITY
# ======================================================

import os
import json
import requests
import time
import re
import shutil
import subprocess

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
    "temp.mkv"
)

DASH_DIR = os.path.join(
    PROJECT_DIR,
    "dash_output"
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
]

CHAT_ID = "@stream1806"

# ======================================================
# WORKER URL
# ======================================================

WORKER_URL = (
    "https://frosty-snow-1291.database1806.workers.dev"
)

# ======================================================
# DASH SETTINGS
# ======================================================

SEGMENT_DURATION = 4

# ======================================================
# PARALLEL SETTINGS
# ======================================================

MAX_WORKERS_PER_BOT = 4

# ======================================================
# CREATE FOLDERS
# ======================================================

os.makedirs(PROJECT_DIR, exist_ok=True)
os.makedirs(DASH_DIR, exist_ok=True)
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
# CREATE DASH SEGMENTS
# ======================================================

def create_dash(movie_name):

    print("\n🎬 Creating DASH stream...")

    # Remove old DASH files
    if os.path.exists(DASH_DIR):
        shutil.rmtree(DASH_DIR)

    os.makedirs(DASH_DIR, exist_ok=True)

    mpd_path = os.path.join(
        DASH_DIR,
        "stream.mpd"
    )

    #
    # IMPORTANT:
    # -map 0:v = include video
    # -map 0:a? = include audio
    # subtitles ignored
    #

    result = subprocess.run(

        [
            "ffmpeg",

            "-y",

            "-i",
            TEMP_VIDEO,

            #
            # VIDEO + AUDIO ONLY
            #

            "-map", "0:v",
            "-map", "0:a?",

            #
            # NO RE-ENCODING
            #

            "-c", "copy",

            #
            # Bitrate metadata
            #

            "-b:v", "3000k",
            "-b:a", "128k",

            #
            # DASH
            #

            "-f",
            "dash",

            "-seg_duration",
            str(SEGMENT_DURATION),

            "-use_template",
            "1",

            "-use_timeline",
            "1",

            #
            # Fragment names
            #

            "-init_seg_name",
            "init-$RepresentationID$.m4s",

            "-media_seg_name",
            "chunk-$RepresentationID$-$Number%05d$.m4s",

            mpd_path
        ],

        capture_output=True,
        text=True

    )

    if result.returncode != 0:

        print(result.stderr)

        raise RuntimeError(
            "FFmpeg DASH creation failed"
        )

    print("✅ DASH stream created")

    files = sorted(

        os.path.join(DASH_DIR, f)

        for f in os.listdir(DASH_DIR)

        if f.endswith(".m4s")
        or f.endswith(".mpd")

    )

    print(
        f"📦 Created "
        f"{len(files)} DASH files"
    )

    return files


# ======================================================
# SELECT BOT
# ======================================================

def get_upload_bot(index):

    return UPLOAD_BOTS[
        index % len(UPLOAD_BOTS)
    ]


# ======================================================
# UPLOAD SINGLE FILE
# ======================================================

def upload_file(file_path, index):

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
                    f"{os.path.basename(file_path)}"
                )

                return {

                    "name":
                    os.path.basename(file_path),

                    "file_id":
                    file_id
                }

            print(
                f"❌ Upload error:\n{data}"
            )

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
# UPLOAD ALL DASH FILES
# ======================================================

def upload_all_files(files):

    total_workers = (
        MAX_WORKERS_PER_BOT *
        len(UPLOAD_BOTS)
    )

    uploaded = {}

    with ThreadPoolExecutor(
        max_workers=total_workers
    ) as executor:

        futures = {

            executor.submit(
                upload_file,
                files[i],
                i
            ): i

            for i in range(len(files))
        }

        for future in as_completed(futures):

            result = future.result()

            if result:
                uploaded[result["name"]] = result

    return uploaded


# ======================================================
# CREATE FINAL MPD
# ======================================================

def build_final_mpd(
    movie_name,
    uploaded_files
):

    safe_name = clean_name(movie_name)

    original_mpd_path = os.path.join(
        DASH_DIR,
        "stream.mpd"
    )

    final_mpd_path = os.path.join(
        MOVIES_DIR,
        f"{safe_name}.mpd"
    )

    with open(
        original_mpd_path,
        "r",
        encoding="utf-8"
    ) as f:

        mpd = f.read()

    #
    # Replace DASH filenames
    # with Worker URLs
    #

    for filename, data in uploaded_files.items():

        if not (
            filename.endswith(".m4s")
            or filename.endswith(".mpd")
        ):
            continue

        worker_url = (
            f"{WORKER_URL}/file_by_id/"
            f"{requests.utils.quote(data['file_id'], safe='')}"
        )

        mpd = mpd.replace(
            filename,
            worker_url
        )

    with open(
        final_mpd_path,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(mpd)

    print(
        f"📝 Saved MPD:\n"
        f"{final_mpd_path}"
    )

    return safe_name


# ======================================================
# PROCESS MOVIE
# ======================================================

def process_movie(movie):

    print(
        f"\n🎬 PROCESSING:\n"
        f"{movie['name']}"
    )

    if os.path.exists(TEMP_VIDEO):
        os.remove(TEMP_VIDEO)

    #
    # Download source
    #

    if not download_video(movie["url"]):
        return None

    #
    # Create DASH
    #

    files = create_dash(
        movie["name"]
    )

    #
    # Upload DASH files
    #

    uploaded = upload_all_files(files)

    #
    # Create final MPD
    #

    safe_name = build_final_mpd(
        movie["name"],
        uploaded
    )

    return safe_name


# ======================================================
# UPDATE CATALOG
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

    data["movies"] = entries

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
        "\n🚀 TELEGRAM DASH "
        "STREAMING SYSTEM\n"
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
            "video-storing/main/movies/"
            f"{safe_name}.mpd"
        )

        catalog_entries.append({

            "name": movie["name"],

            "year": movie["year"],

            "playlist": playlist_url
        })

    update_catalog(catalog_entries)

    print("\n🎉 DONE!")
