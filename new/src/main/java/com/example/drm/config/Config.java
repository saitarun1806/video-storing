package com.example.drm.config;

import java.nio.file.Path;
import java.util.Locale;

public record Config(
        String adminSecret,
        String drmRegisterSecret,
        String discordBotIndexUrl,
        String discordChannelId,
        String drmRegisterUrl,
        String drmLicenseUrl,
        String cdnWorkerUrl,
        String ffmpeg,
        String ffprobe,
        String mp4encrypt,
        String mp4dump,
        Path workRoot,
        int segmentDuration,
        int uploadConcurrency,
        int uploadTimeoutSeconds,
        double botFailureCooldownSeconds
) {
    public static Config load() {
        return new Config(
                env("ADMIN_SECRET", ""), env("DRM_REGISTER_SECRET", ""),
                env("DISCORD_BOT_INDEX_URL", "").replaceAll("/$", ""),
                env("DISCORD_CHANNEL_ID", ""), env("DRM_REGISTER_URL", "").replaceAll("/$", ""),
                env("DRM_LICENSE_URL", "").replaceAll("/$", ""), env("CDN_WORKER_URL", "").replaceAll("/$", ""),
                env("FFMPEG", "ffmpeg"), env("FFPROBE", "ffprobe"), env("BENTO4_MP4ENCRYPT", "mp4encrypt"),
                env("BENTO4_MP4DUMP", "mp4dump"), Path.of(env("WORK_ROOT", "./drm_jobs")).toAbsolutePath(),
                integer("SEGMENT_DURATION", 4), integer("DISCORD_UPLOAD_CONCURRENCY", 4),
                integer("DISCORD_UPLOAD_TIMEOUT_SECONDS", 600), number("DISCORD_BOT_FAILURE_COOLDOWN_SECONDS", 2)
        );
    }
    private static String env(String k, String d) { String v=System.getenv(k); return v==null||v.isBlank()?d:v.trim(); }
    private static int integer(String k,int d){try{return Integer.parseInt(env(k,""+d));}catch(Exception e){return d;}}
    private static double number(String k,double d){try{return Double.parseDouble(env(k,""+d));}catch(Exception e){return d;}}
    public void validate(){
        if(adminSecret.isBlank()) throw new IllegalStateException("ADMIN_SECRET is not configured");
        if(drmRegisterSecret.isBlank()) throw new IllegalStateException("DRM_REGISTER_SECRET is not configured");
        if(discordBotIndexUrl.isBlank()||discordChannelId.isBlank()||drmRegisterUrl.isBlank()||drmLicenseUrl.isBlank()||cdnWorkerUrl.isBlank())
            throw new IllegalStateException("Discord/DRM/CDN configuration is incomplete");
        if(segmentDuration<=0||uploadConcurrency<=0) throw new IllegalStateException("Invalid numeric configuration");
    }
}
