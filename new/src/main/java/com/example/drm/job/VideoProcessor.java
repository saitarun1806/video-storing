
package com.example.drm.job;

import com.example.drm.config.Config;
import com.example.drm.discord.DiscordUploader;
import com.example.drm.drm.DrmClient;
import com.example.drm.encryption.CencService;
import com.example.drm.media.MediaService;
import com.example.drm.mpd.MpdRewriter;
import com.example.drm.util.Log;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.Map;

public class VideoProcessor {

    public record Result(
            boolean success,
            String videoId,
            String mpdUrl,
            String licenseUrl,
            String kid,
            String error
    ) {
    }

    private final Config config;
    private final MediaService media;
    private final CencService cenc;
    private final DiscordUploader discord;
    private final DrmClient drm;
    private final MpdRewriter mpd =
            new MpdRewriter();

    public VideoProcessor(
            Config config,
            MediaService media,
            CencService cenc,
            DiscordUploader discord,
            DrmClient drm
    ) {
        this.config = config;
        this.media = media;
        this.cenc = cenc;
        this.discord = discord;
        this.drm = drm;
    }

    public Result process(
            String input,
            int job,
            int total
    ) throws Exception {

        String videoId =
                CencService.videoId();

        String kid =
                CencService.hex16();

        String key =
                CencService.hex16();

        Path directory =
                config.workRoot()
                        .resolve(videoId);

        try {

            Log.banner(
                    "[JOB "
                            + job
                            + "/"
                            + total
                            + "] STARTING"
            );

            Log.job(
                    job,
                    "Input: " + input
            );

            Log.job(
                    job,
                    "Video ID: " + videoId
            );

            Log.job(
                    job,
                    "KID: " + kid
            );

            Files.createDirectories(
                    directory
            );

            /*
             * Prepare source media.
             */
            Path source =
                    media.prepareSource(
                            input,
                            directory
                    );

            /*
             * Detect video and audio tracks.
             */
            MediaService.Tracks tracks =
                    media.detectTracks(source);

            /*
             * Create DASH.
             */
            Path dashDirectory =
                    directory.resolve("dash");

            Path manifest =
                    media.createDash(
                            source,
                            dashDirectory,
                            tracks
                    );

            /*
             * MPEG-CENC encryption.
             */
            cenc.encryptDash(
                    dashDirectory,
                    kid,
                    key
            );

            /*
             * Upload DASH segments.
             */
            Map<String, DiscordUploader.UploadResult> uploaded =
                    discord.uploadSegments(
                            dashDirectory
                    );

            /*
             * Rewrite MPD with CDN URLs
             * and ClearKey/CENC information.
             */
            mpd.rewrite(
                    manifest,
                    uploaded,
                    kid
            );

            /*
             * Upload final MPD.
             */
            DiscordUploader.UploadResult finalMpd =
                    discord.uploadSingle(
                            manifest
                    );

            String mpdUrl =
                    finalMpd.resolverUrl();

            /*
             * Register DRM information.
             */
            drm.register(
                    videoId,
                    kid,
                    key,
                    mpdUrl
            );

            Log.banner(
                    "[JOB "
                            + job
                            + "/"
                            + total
                            + "] COMPLETED"
            );

            System.out.println(
                    "Video ID : " + videoId
            );

            System.out.println(
                    "MPD URL  : " + mpdUrl
            );

            System.out.println(
                    "License  : "
                            + config.drmLicenseUrl()
            );

            System.out.println(
                    "KID      : " + kid
            );

            return new Result(
                    true,
                    videoId,
                    mpdUrl,
                    config.drmLicenseUrl(),
                    kid,
                    null
            );

        } catch (Exception e) {

            Log.err(
                    "JOB "
                            + job
                            + " failed: "
                            + e.getMessage()
            );

            return new Result(
                    false,
                    videoId,
                    null,
                    config.drmLicenseUrl(),
                    kid,
                    e.getMessage()
            );

        } finally {

            /*
             * Remove temporary job directory.
             */
            try {

                if (Files.exists(directory)) {
                    deleteTree(directory);
                }

            } catch (Exception e) {

                Log.warn(
                        "Cleanup failed: "
                                + e.getMessage()
                );
            }
        }
    }

    private void deleteTree(Path path)
            throws Exception {

        try (var stream = Files.walk(path)) {

            stream
                    .sorted(
                            Comparator.reverseOrder()
                    )
                    .forEach(
                            item -> {

                                try {

                                    Files.deleteIfExists(
                                            item
                                    );

                                } catch (Exception e) {

                                    throw new RuntimeException(
                                            e
                                    );
                                }
                            }
                    );
        }
    }
}
