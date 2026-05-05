import os
import json
import base64
import gzip
import subprocess
import requests
import time

# ======================
# CONFIG
# ======================
INPUT_FILE = "input_movies.json"

PROJECT_DIR = "project"
TEMP_VIDEO = os.path.join(PROJECT_DIR, "temp.mp4")

JSON_DIR = os.path.join(PROJECT_DIR, "json_chunks")
MOVIES_DIR = os.path.join(PROJECT_DIR, "movies")   # 🔥 manifests here
MOVIES_FILE = os.path.join(PROJECT_DIR, "movies.json")  # 🔥 catalog outside

BOT_TOKEN = "8651470873:AAEMq3GGKk9FBG60O6Vd_eH5V-1x0S6Pqc4"
CHAT_ID = "@stream1806"  # or channel ID

MAX_JSON_SIZE = 1 * 1024 * 1024
INITIAL_CHUNK_SIZE = 700 * 1024

# ======================
# CREATE FOLDERS
# ======================
os.makedirs(PROJECT_DIR, exist_ok=True)
os.makedirs(JSON_DIR, exist_ok=True)
os.makedirs(MOVIES_DIR, exist_ok=True)

# ======================
# DOWNLOAD USING CURL
# ======================
def download_video(url):
    print(f"⬇️ Downloading: {url}")

    subprocess.run([
        "curl", "-L", url, "-o", TEMP_VIDEO
    ], check=True)

    print("✅ Downloaded")

# ======================
# ENCODE
# ======================
def encode(data):
    return base64.b64encode(gzip.compress(data)).decode()

# ======================
# CREATE JSON CHUNKS
# ======================
def create_chunks():
    files = []

    with open(TEMP_VIDEO, "rb") as f:
        index = 0

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

            while size > MAX_JSON_SIZE:
                chunk = chunk[:int(len(chunk) * 0.8)]
                encoded = encode(chunk)
                data["data"] = encoded
                json_str = json.dumps(data, separators=(",", ":"))
                size = len(json_str.encode())

            filename = f"chunk_{index:04d}.json"
            filepath = os.path.join(JSON_DIR, filename)

            with open(filepath, "w") as f:
                f.write(json_str)

            files.append(filepath)
            print(f"✅ {filename}")

            index += 1

    return files

# ======================
# TELEGRAM UPLOAD
# ======================
def upload(file_path):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"

    with open(file_path, "rb") as f:
        res = requests.post(url, data={"chat_id": CHAT_ID}, files={"document": f})

    data = res.json()

    if data.get("ok"):
        return data["result"]["document"]["file_id"]

    print("❌ Upload error:", data)
    return None

# ======================
# PROCESS MOVIE
# ======================
def process_movie(movie):
    name = movie["name"]
    year = movie["year"]
    url = movie["url"]

    print(f"\n🎬 Processing: {name} ({year})")

    safe = name.lower().replace(" ", "_")
    manifest_name = f"{safe}_{year}.json"
    manifest_path = os.path.join(MOVIES_DIR, manifest_name)  # 🔥 inside movies/

    # 1. Download
    download_video(url)

    # 2. Chunk
    json_files = create_chunks()

    # 3. Upload
    chunks = []
    for i, file in enumerate(json_files):
        file_id = upload(file)

        if file_id:
            chunks.append({
                "order": i,
                "file_id": file_id
            })

        time.sleep(0.5)

    # 4. Create manifest
    manifest = {
        "movie": name,
        "year": year,
        "chunkDuration": 5,
        "chunks": chunks
    }

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"📝 Manifest saved → movies/{manifest_name}")

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

        # 👇 update this to your GitHub raw path
        manifest_url = f"https://raw.githubusercontent.com/saitarun1806/video-storing/main/movies/{manifest_name}"

        catalog_entries.append({
            "name": movie["name"],
            "year": movie["year"],
            "manifest": manifest_url
        })

    update_catalog(catalog_entries)

    print("\n🎉 DONE!")
