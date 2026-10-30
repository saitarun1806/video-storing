#!/usr/bin/env bash

set -e

echo "=========================================="
echo " Java DASH DRM Uploader - Setup"
echo "=========================================="

# ------------------------------------------
# Check OS
# ------------------------------------------

if [ ! -f /etc/os-release ]; then
    echo "Unsupported operating system."
    exit 1
fi

. /etc/os-release

echo "[INFO] OS: $PRETTY_NAME"

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

java -version
javac -version

# ------------------------------------------
# Verify Maven
# ------------------------------------------

echo
echo "[4/7] Checking Maven..."

mvn -version

# ------------------------------------------
# Verify FFmpeg
# ------------------------------------------

echo
echo "[5/7] Checking FFmpeg..."

ffmpeg -version | head -n 1
ffprobe -version | head -n 1

# ------------------------------------------
# Install Bento4
# ------------------------------------------

echo
echo "[6/7] Installing Bento4..."

BENTO_DIR="/opt/bento4"
BENTO_BIN="$BENTO_DIR/bin"

if command -v mp4encrypt >/dev/null 2>&1 && \
   command -v mp4dump >/dev/null 2>&1; then

    echo "[INFO] Bento4 already installed."

else

    sudo mkdir -p "$BENTO_DIR"

    ARCH="$(uname -m)"

    case "$ARCH" in
        x86_64)
            BENTO_ARCH="x86_64"
            ;;
        aarch64|arm64)
            BENTO_ARCH="aarch64"
            ;;
        *)
            echo "[ERROR] Unsupported architecture: $ARCH"
            exit 1
            ;;
    esac

    echo "[INFO] Architecture: $ARCH"

    echo "[INFO] Finding latest Bento4 release..."

    BENTO_URL=$(
        curl -fsSL \
        https://api.github.com/repos/axiomatic-systems/Bento4/releases/latest |
        grep -o '"browser_download_url": "[^"]*"' |
        cut -d '"' -f 4 |
        grep -Ei "linux.*${BENTO_ARCH}|${BENTO_ARCH}.*linux" |
        grep -E '\.(zip|tar\.gz)$' |
        head -n 1
    )

    if [ -z "$BENTO_URL" ]; then
        echo "[ERROR] Could not automatically find Bento4 release."
        echo
        echo "Install Bento4 manually and make sure these commands exist:"
        echo "  mp4encrypt"
        echo "  mp4dump"
        exit 1
    fi

    echo "[INFO] Downloading:"
    echo "$BENTO_URL"

    TMP_DIR="$(mktemp -d)"

    curl -L "$BENTO_URL" \
        -o "$TMP_DIR/bento4_archive"

    FILE_TYPE="$(file "$TMP_DIR/bento4_archive")"

    echo "[INFO] Downloaded Bento4."

    if echo "$BENTO_URL" | grep -q "\.zip"; then

        unzip -q "$TMP_DIR/bento4_archive" \
            -d "$TMP_DIR/extracted"

    elif echo "$BENTO_URL" | grep -q "\.tar.gz"; then

        mkdir -p "$TMP_DIR/extracted"

        tar -xzf "$TMP_DIR/bento4_archive" \
            -C "$TMP_DIR/extracted"

    else
        echo "[ERROR] Unknown Bento4 archive format."
        exit 1
    fi

    # Find mp4encrypt
    MP4ENCRYPT_PATH=$(
        find "$TMP_DIR/extracted" \
        -type f \
        -name mp4encrypt \
        -print -quit
    )

    # Find mp4dump
    MP4DUMP_PATH=$(
        find "$TMP_DIR/extracted" \
        -type f \
        -name mp4dump \
        -print -quit
    )

    if [ -z "$MP4ENCRYPT_PATH" ]; then
        echo "[ERROR] mp4encrypt not found in Bento4 archive."
        exit 1
    fi

    if [ -z "$MP4DUMP_PATH" ]; then
        echo "[ERROR] mp4dump not found in Bento4 archive."
        exit 1
    fi

    sudo mkdir -p "$BENTO_BIN"

    sudo cp "$MP4ENCRYPT_PATH" "$BENTO_BIN/mp4encrypt"
    sudo cp "$MP4DUMP_PATH" "$BENTO_BIN/mp4dump"

    sudo chmod +x "$BENTO_BIN/mp4encrypt"
    sudo chmod +x "$BENTO_BIN/mp4dump"

    rm -rf "$TMP_DIR"

    # Create global symlinks
    sudo ln -sf "$BENTO_BIN/mp4encrypt" /usr/local/bin/mp4encrypt
    sudo ln -sf "$BENTO_BIN/mp4dump" /usr/local/bin/mp4dump

fi

# ------------------------------------------
# Verify Bento4
# ------------------------------------------

echo
echo "[7/7] Verifying Bento4..."

if ! command -v mp4encrypt >/dev/null 2>&1; then
    echo "[ERROR] mp4encrypt was not found."
    exit 1
fi

if ! command -v mp4dump >/dev/null 2>&1; then
    echo "[ERROR] mp4dump was not found."
    exit 1
fi

echo "[OK] mp4encrypt found:"
which mp4encrypt

echo "[OK] mp4dump found:"
which mp4dump

# ------------------------------------------
# Project directories
# ------------------------------------------

mkdir -p drm_jobs

# ------------------------------------------
# Create .env
# ------------------------------------------

if [ ! -f .env ]; then

    if [ -f .env.example ]; then

        echo
        echo "[INFO] Creating .env from .env.example..."

        cp .env.example .env

        echo "[WARNING] .env was created."
        echo "[WARNING] Edit .env and add your secrets."

    else

        echo
        echo "[WARNING] .env.example does not exist."
        echo "[WARNING] Create .env manually."

    fi

else

    echo
    echo "[INFO] .env already exists. Keeping existing configuration."

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
which mp4encrypt
which mp4dump

echo
echo "Project directory:"
pwd

echo
echo "Next steps:"
echo
echo "  1. Edit .env"
echo "     nano .env"
echo
echo "  2. Build Java project"
echo "     mvn clean package"
echo
echo "  3. Run"
echo "     java -jar target/dash-drm-uploader-1.0.0.jar"
echo
