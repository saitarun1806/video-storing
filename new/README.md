# DASH + MPEG-CENC + ClearKey + Discord uploader (Java)

This is a Java conversion of the supplied Python pipeline. It keeps the media pipeline:

input -> ffmpeg/ffprobe -> multi-audio DASH -> MPEG-CENC/Bento4 -> Discord storage -> MPD rewrite -> DRM registration.

The uploader uses bounded asynchronous HTTP uploads and honors Discord HTTP 429 `retry_after`. It does not intentionally use concurrent bot accounts to evade Discord rate limits. Multiple bot tokens can be loaded for failover/redundancy.

## Requirements
- Java 21+
- Maven
- FFmpeg + FFprobe
- Bento4 `mp4encrypt` and `mp4dump`
- A bot-index worker returning `{ "success": true, "bots": [{"index":0,"token":"..."}] }`
- Your own/authorized media and DRM service

## Run
1. Copy `.env.example` to `.env` or export variables in the shell.
2. `mvn clean package`
3. `java -jar target/dash-drm-uploader-1.0.0.jar`

The program accepts local paths or HTTP/HTTPS media URLs. Press Enter on an empty input to start processing the batch.

Do not commit bot tokens, admin secrets, DRM registration secrets, or encryption keys.
