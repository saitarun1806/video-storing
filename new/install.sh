#!/usr/bin/env bash

set -e

echo "=========================================="
echo " Java DASH DRM Uploader - Setup"
echo "=========================================="

# ------------------------------------------
# Check OS
# ------------------------------------------

if [ ! -f /etc/os-release ]; then
    echo "[ERROR] Unsupported operating system."
    exit 1
fi

. /etc/os-release

echo "[INFO] OS: $PRETTY_NAME"

# ------------------------------------------
# Check sudo
# ------------------------------------------

if ! command -v sudo >/dev/null 2>&1; then
    echo "[ERROR] sudo is not installed."
    exit 1
fi

# ------------------------------------------
# Update packages
# ------------------------------------------

echo
echo "[1/7] Updating package lists..."

sudo apt-get update

# ------------------------------------------
# Install basic requirements
# ------------------------------------------

echo
echo "[2/7] Installing system packages..."

sudo apt-get install -y \
    openjdk-21-jdk \
    maven \
    ffmpeg \
    curl \
    wget \
    unzip \
    git \
    ca-certificates

# ------------------------------------------
# Verify Java
# ------------------------------------------

echo
echo "[3/7] Checking Java..."

if ! command -v java >/dev/null 2>&1; then
    echo "[ERROR] Java was not installed correctly."
    exit 1
fi

if ! command -v javac >/dev/null 2>&1; then
    echo "[ERROR] javac was not installed correctly."
    exit 1
fi

java -version
javac -version

# ------------------------------------------
# Verify Maven
# ------------------------------------------

echo
echo "[4/7] Checking Maven..."

if ! command -v mvn >/dev/null 2>&1; then
    echo "[ERROR] Maven was not installed correctly."
    exit 1
fi

mvn -version

# ------------------------------------------
# Verify FFmpeg
# ------------------------------------------

echo
echo "[5/7] Checking FFmpeg..."

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "[ERROR] FFmpeg was not installed correctly."
    exit 1
fi

if ! command -v ffprobe >/dev/null 2>&1; then
    echo "[ERROR] FFprobe was not installed correctly."
    exit 1
fi

echo "[OK] FFmpeg:"
ffmpeg -version | head -n 1

echo "[OK] FFprobe:"
ffprobe -version | head -n 1

# ------------------------------------------
# Install Bento4
# ------------------------------------------

echo
echo "[6/7] Installing Bento4..."

BENTO_DIR="/opt/bento4"
BENTO_BIN="$BENTO_DIR/bin"

# Official Bento4 Linux x86_64 binary
BENTO_X86_64_URL="https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip"

# Check if Bento4 is already installed
if command -v mp4encrypt >/dev/null 2>&1 && \
   command -v mp4dump >/dev/null 2>&1; then

    echo "[INFO] Bento4 already installed."
    echo "[INFO] mp4encrypt: $(command -v mp4encrypt)"
    echo "[INFO] mp4dump: $(command -v mp4dump)"

else

    ARCH="$(uname -m)"

    echo "[INFO] Architecture: $ARCH"

    # --------------------------------------
    # Architecture selection
    # --------------------------------------

    case "$ARCH" in

        x86_64)
            BENTO_URL="$BENTO_X86_64_URL"
            ;;

        *)
            echo "[ERROR] Unsupported architecture: $ARCH"
            echo
            echo "Currently supported Bento4 architecture:"
            echo "  x86_64"
            echo
            exit 1
            ;;

    esac

    echo "[INFO] Bento4 URL:"
    echo "$BENTO_URL"

    # --------------------------------------
    # Temporary directory
    # --------------------------------------

    TMP_DIR="$(mktemp -d)"

    cleanup() {
        rm -rf "$TMP_DIR"
    }

    trap cleanup EXIT

    echo
    echo "[INFO] Temporary directory:"
    echo "$TMP_DIR"

    # --------------------------------------
    # Download Bento4
    # --------------------------------------

    echo
    echo "[INFO] Downloading Bento4..."

    curl -fL \
        --retry 3 \
        --retry-delay 2 \
        "$BENTO_URL" \
        -o "$TMP_DIR/bento4.zip"

    if [ ! -f "$TMP_DIR/bento4.zip" ]; then
        echo "[ERROR] Bento4 download failed."
        exit 1
    fi

    echo "[OK] Bento4 downloaded."

    # --------------------------------------
    # Extract Bento4
    # --------------------------------------

    echo
    echo "[INFO] Extracting Bento4..."

    mkdir -p "$TMP_DIR/extracted"

    unzip -q \
        "$TMP_DIR/bento4.zip" \
        -d "$TMP_DIR/extracted"

    echo "[OK] Bento4 extracted."

    # --------------------------------------
    # Find mp4encrypt
    # --------------------------------------

    echo
    echo "[INFO] Searching for mp4encrypt..."

    MP4ENCRYPT_PATH=$(
        find "$TMP_DIR/extracted" \
            -type f \
            -name "mp4encrypt" \
            -print -quit
    )

    if [ -z "$MP4ENCRYPT_PATH" ]; then
        echo "[ERROR] mp4encrypt was not found in Bento4 archive."
        echo
        echo "Files inside archive:"
        find "$TMP_DIR/extracted" -type f | head -50
        exit 1
    fi

    echo "[OK] mp4encrypt found:"
    echo "$MP4ENCRYPT_PATH"

    # --------------------------------------
    # Find mp4dump
    # --------------------------------------

    echo
    echo "[INFO] Searching for mp4dump..."

    MP4DUMP_PATH=$(
        find "$TMP_DIR/extracted" \
            -type f \
            -name "mp4dump" \
            -print -quit
    )

    if [ -z "$MP4DUMP_PATH" ]; then
        echo "[ERROR] mp4dump was not found in Bento4 archive."
        echo
        echo "Files inside archive:"
        find "$TMP_DIR/extracted" -type f | head -50
        exit 1
    fi

    echo "[OK] mp4dump found:"
    echo "$MP4DUMP_PATH"

    # --------------------------------------
    # Install Bento4
    # --------------------------------------

    echo
    echo "[INFO] Installing Bento4 to:"
    echo "$BENTO_DIR"

    sudo mkdir -p "$BENTO_BIN"

    sudo cp \
        "$MP4ENCRYPT_PATH" \
        "$BENTO_BIN/mp4encrypt"

    sudo cp \
        "$MP4DUMP_PATH" \
        "$BENTO_BIN/mp4dump"

    # --------------------------------------
    # Make executable
    # --------------------------------------

    sudo chmod +x \
        "$BENTO_BIN/mp4encrypt"

    sudo chmod +x \
        "$BENTO_BIN/mp4dump"

    # --------------------------------------
    # Create global commands
    # --------------------------------------

    echo
    echo "[INFO] Creating global commands..."

    sudo ln -sf \
        "$BENTO_BIN/mp4encrypt" \
        /usr/local/bin/mp4encrypt

    sudo ln -sf \
        "$BENTO_BIN/mp4dump" \
        /usr/local/bin/mp4dump

    echo "[OK] Bento4 installed."

fi

# ------------------------------------------
# Verify Bento4
# ------------------------------------------

echo
echo "[7/7] Verifying Bento4..."

if ! command -v mp4encrypt >/dev/null 2>&1; then
    echo "[ERROR] mp4encrypt was not found in PATH."
    exit 1
fi

if ! command -v mp4dump >/dev/null 2>&1; then
    echo "[ERROR] mp4dump was not found in PATH."
    exit 1
fi

echo "[OK] mp4encrypt: $(command -v mp4encrypt)"
echo "[OK] mp4dump: $(command -v mp4dump)"

# ------------------------------------------
# Project directories
# ------------------------------------------

echo
echo "[INFO] Creating project directories..."

mkdir -p drm_jobs

echo "[OK] drm_jobs directory ready."

# ------------------------------------------
# Create .env
# ------------------------------------------

if [ ! -f .env ]; then

    if [ -f .env.example ]; then

        echo
        echo "[INFO] Creating .env from .env.example..."

        cp .env.example .env

        echo "[OK] .env created."
        echo
        echo "[WARNING] Edit .env and add your configuration/secrets."

    else

        echo
        echo "[WARNING] .env.example does not exist."
        echo "[WARNING] Create .env manually."

    fi

else

    echo
    echo "[INFO] .env already exists."
    echo "[INFO] Keeping existing configuration."

fi

# ------------------------------------------
# Final information
# ------------------------------------------

echo
echo "=========================================="
echo " Installation completed successfully!"
echo "=========================================="

echo
echo "Java:"
java -version 2>&1 | head -n 1

echo
echo "Javac:"
javac -version

echo
echo "Maven:"
mvn -version | head -n 1

echo
echo "FFmpeg:"
ffmpeg -version | head -n 1

echo
echo "FFprobe:"
ffprobe -version | head -n 1

echo
echo "Bento4:"
echo "mp4encrypt -> $(command -v mp4encrypt)"
echo "mp4dump    -> $(command -v mp4dump)"

echo
echo "Project directory:"
pwd

echo
echo "=========================================="
echo " Next steps"
echo "=========================================="

echo
echo "1. Edit .env"
echo "   nano .env"

echo
echo "2. Build Java project"
echo "   mvn clean package"

echo
echo "3. Run"
echo "   java -jar target/dash-drm-uploader-1.0.0.jar"

echo
echo "=========================================="
echo " Setup complete!"
echo "=========================================="