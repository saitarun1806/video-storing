
package com.example.drm;

import com.example.drm.config.Config;
import com.example.drm.discord.DiscordBotProvider;
import com.example.drm.discord.DiscordUploader;
import com.example.drm.drm.DrmClient;
import com.example.drm.encryption.CencService;
import com.example.drm.job.VideoProcessor;
import com.example.drm.media.MediaService;
import com.example.drm.util.CommandRunner;
import com.example.drm.util.Log;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.List;

public class Main {

    public static void main(String[] args) {

        try {
            Config config = Config.load();
            config.validate();

            config.workRoot().toFile().mkdirs();

            // Check required external programs
            String[][] commands = {
                    {config.ffmpeg(), "FFmpeg"},
                    {config.ffprobe(), "FFprobe"},
                    {config.mp4encrypt(), "Bento4 mp4encrypt"},
                    {config.mp4dump(), "Bento4 mp4dump"}
            };

            for (String[] command : commands) {
                if (!CommandRunner.exists(command[0])) {
                    throw new IllegalStateException(
                            command[1] + " not found: " + command[0]
                    );
                }
            }

            Log.banner(
                    "DASH + MULTI-AUDIO + MPEG-CENC + DISCORD + DRM UPLOADER (JAVA)"
            );

            // Load Discord bots
            List<DiscordUploader.Bot> bots =
                    DiscordBotProvider.load(config);

            System.out.println(
                    "Discord bots loaded: " + bots.size()
            );

            // Initialize services
            MediaService media = new MediaService(config);
            CencService cenc = new CencService(config);
            DrmClient drm = new DrmClient(config);

            try (DiscordUploader uploader =
                         new DiscordUploader(config, bots)) {

                VideoProcessor processor =
                        new VideoProcessor(
                                config,
                                media,
                                cenc,
                                uploader,
                                drm
                        );

                while (true) {

                    List<String> inputs = readBatch();

                    if (inputs.isEmpty()) {

                        String answer = ask(
                                "No videos entered. Try again? [Y/n]: "
                        );

                        if (answer.equalsIgnoreCase("n")
                                || answer.equalsIgnoreCase("no")) {
                            break;
                        }

                        continue;
                    }

                    List<VideoProcessor.Result> successful =
                            new ArrayList<>();

                    List<VideoProcessor.Result> failed =
                            new ArrayList<>();

                    Log.banner(
                            "STARTING QUEUE: "
                                    + inputs.size()
                                    + " VIDEO(S)"
                    );

                    for (int i = 0; i < inputs.size(); i++) {

                        VideoProcessor.Result result =
                                processor.process(
                                        inputs.get(i),
                                        i + 1,
                                        inputs.size()
                                );

                        if (result.success()) {
                            successful.add(result);
                        } else {
                            failed.add(result);
                        }
                    }

                    Log.banner("QUEUE FINISHED");

                    System.out.println(
                            "Total: " + inputs.size()
                                    + "  Success: " + successful.size()
                                    + "  Failed: " + failed.size()
                    );

                    // Successful videos
                    for (VideoProcessor.Result result : successful) {

                        System.out.println(
                                "SUCCESS video="
                                        + result.videoId()
                                        + " mpd="
                                        + result.mpdUrl()
                        );
                    }

                    // Failed videos
                    for (VideoProcessor.Result result : failed) {

                        System.out.println(
                                "FAILED video="
                                        + result.videoId()
                                        + " error="
                                        + result.error()
                        );
                    }

                    String answer = ask(
                            "Add another batch? [Y/n]: "
                    );

                    if (answer.equalsIgnoreCase("n")
                            || answer.equalsIgnoreCase("no")) {
                        break;
                    }
                }
            }

            Log.banner("UPLOADER STOPPED");

        } catch (Exception e) {

            Log.banner("FATAL ERROR");

            if (e.getMessage() != null) {
                System.err.println(e.getMessage());
            }

            e.printStackTrace();

            System.exit(1);
        }
    }

    /**
     * Read a batch of video inputs.
     *
     * The user can enter:
     * - Local file paths
     * - HTTP URLs
     * - HTTPS URLs
     *
     * An empty line starts processing.
     */
    private static List<String> readBatch() throws IOException {

        Log.banner("ADD VIDEOS");

        System.out.println(
                "Enter local file paths or HTTP/HTTPS URLs. "
                        + "Empty line starts processing."
        );

        List<String> inputs = new ArrayList<>();

        BufferedReader reader =
                new BufferedReader(
                        new InputStreamReader(System.in)
                );

        while (true) {

            System.out.print(
                    "Video " + (inputs.size() + 1) + ": "
            );

            String input = reader.readLine();

            if (input == null || input.trim().isEmpty()) {
                break;
            }

            inputs.add(input.trim());
        }

        return inputs;
    }

    /**
     * Ask the user for a response.
     */
    private static String ask(String message)
            throws IOException {

        System.out.print(message);

        BufferedReader reader =
                new BufferedReader(
                        new InputStreamReader(System.in)
                );

        String answer = reader.readLine();

        if (answer == null) {
            return "";
        }

        return answer.trim();
    }
}
