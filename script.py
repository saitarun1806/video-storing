import os
import json
import base64
import gzip
import requests
import time

# ======================
# CONFIG
# ======================
INPUT_FILE = "input_movies.json"

PROJECT_DIR = "project"
TEMP_VIDEO = os.path.join(PROJECT_DIR, "temp.mp4")

JSON_DIR = os.path.join(PROJECT_DIR, "json_chunks")
MOVIES_DIR = os.path.join(PROJECT_DIR, "movies")
MOVIES_FILE = os.path.join(PROJECT_DIR, "movies.json")

BOT_TOKEN = "8651470873:AAEMq3GGKk9FBG60O6Vd_eH5V-1x0S6Pqc4"
CHAT_ID = "@stream1806"  # or channel ID

MAX_JSON_SIZE = 20 * 1024 * 1024   # increased for larger chunks
INITIAL_CHUNK_SIZE = 4 * 1024 * 1024  # 🔥 4 MB chunks

# ======================
# CREATE FOLDERS
# ======================
os.makedirs(PROJECT_DIR, exist_ok=True)
os.makedirs(JSON_DIR, exist_ok=True)
os.makedirs(MOVIES_DIR, exist_ok=True)

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
            print(f"⚠️ Retry {attempt+1}: {e}")
            time.sleep(2)

    print("❌ Download failed")
    return False

# ======================
# ENCODE
# ======================
def encode(data):
    return base64.b64encode(gzip.compress(data)).decode()

# ======================
# CREATE JSON CHUNKS
# ======================
def create_chunks(movie_name):
    files = []
    index = 0

    # clean movie name
    safe_name = movie_name.lower().replace(" ", "_").replace("(", "").replace(")", "")

    with open(TEMP_VIDEO, "rb") as f:
        while True:
            chunk = f.read(INITIAL_CHUNK_SIZE)
            if not chunk:
                break

            encoded = encode(chunk)

            data = {
                "order": index,
                "encoding": "gzip+base64",
                "data": encoded
            }

            json_str = json.dumps(data, separators=(",", ":"))
            size = len(json_str.encode())

            # ensure under limit
            while size > MAX_JSON_SIZE:
                chunk = chunk[:int(len(chunk) * 0.8)]
                encoded = encode(chunk)
                data["data"] = encoded
                json_str = json.dumps(data, separators=(",", ":"))
                size = len(json_str.encode())

            filename = f"{safe_name}-chunk_{index:04d}.json"
            filepath = os.path.join(JSON_DIR, filename)

            with open(filepath, "w") as jf:
                jf.write(json_str)

            files.append(filepath)
            print(f"✅ {filename} ({size/1024:.1f} KB)")

            index += 1

    return files

# ======================
# TELEGRAM UPLOAD
# ======================
def upload(file_path):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"

    for attempt in range(3):
        try:
            with open(file_path, "rb") as f:
                res = requests.post(
                    url,
                    data={"chat_id": CHAT_ID},
                    files={"document": f},
                    timeout=20
                )

            data = res.json()

            if data.get("ok"):
                return data["result"]["document"]["file_id"]

            print("❌ Upload error:", data)

        except Exception as e:
            print(f"⚠️ Upload retry {attempt+1}: {e}")
            time.sleep(2)

    return None

# ======================
# PROCESS MOVIE
# ======================
def process_movie(movie):
    name = movie["name"]
    year = movie["year"]
    url = movie["url"]

    print(f"\n🎬 Processing: {name} ({year})")

    safe = name.lower().replace(" ", "_").replace("(", "").replace(")", "")
    manifest_name = f"{safe}_{year}.json"
    manifest_path = os.path.join(MOVIES_DIR, manifest_name)

    # clean temp file
    if os.path.exists(TEMP_VIDEO):
        os.remove(TEMP_VIDEO)

    # download
    if not download_video(url):
        print("⛔ Skipping movie")
        return None

    # chunk creation
    json_files = create_chunks(name)

    # upload
    chunks = []
    for i, file in enumerate(json_files):
        file_id = upload(file)

        if file_id:
            chunks.append({
                "order": i,
                "file_id": file_id
            })

        time.sleep(0.4)

    # manifest
    manifest = {
        "movie": name,
        "year": year,
        "chunkDuration": 5,
        "chunks": chunks
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"📝 Saved → movies/{manifest_name}")

    return manifest_name

# ======================
# UPDATE CATALOG
# ======================
def update_catalog(entries):
    if os.path.exists(MOVIES_FILE):
        with open(MOVIES_FILE, "r") as f:
            data = json.load(f)
    else:
        data = {"movies": []}

    for entry in entries:
        if entry:
            data["movies"].append(entry)

    with open(MOVIES_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print("📚 movies.json updated")

# ======================
# MAIN
# ======================
if __name__ == "__main__":
    print("🚀 Starting pipeline...")

    with open(INPUT_FILE) as f:
        movies_data = json.load(f)["movies"]

    catalog_entries = []

    for movie in movies_data:
        manifest_name = process_movie(movie)

        if not manifest_name:
            continue

        manifest_url = f"https://raw.githubusercontent.com/saitarun1806/video-storing/main/movies/{manifest_name}"

        catalog_entries.append({
            "name": movie["name"],
            "year": movie["year"],
            "manifest": manifest_url
        })

    update_catalog(catalog_entries)

    print("\n🎉 DONE!")
