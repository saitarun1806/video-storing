
package com.example.drm.discord;

import com.example.drm.config.Config;
import com.example.drm.util.Log;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class DiscordUploader implements AutoCloseable {

    private final Config config;
    private final List<Bot> bots;
    private final HttpClient http;
    private final ObjectMapper mapper;

    /*
     * One single-thread worker per Discord bot.
     *
     * 48 bots = 48 independent upload queues.
     */
    private final List<ExecutorService> botWorkers;

    /*
     * Used by uploadSingle().
     *
     * 0 -> bot 0
     * 1 -> bot 1
     * ...
     * 47 -> bot 47
     * 48 -> bot 0
     */
    private final AtomicInteger nextBot =
            new AtomicInteger(0);

    /*
     * Last upload-start time for every bot.
     */
    private final long[] lastUploadTime;

    private final Object rateLock =
            new Object();

    public DiscordUploader(
            Config config,
            List<Bot> bots
    ) {

        this.config = config;

        List<Bot> sorted =
                new ArrayList<>(bots);

        sorted.sort(
                Comparator.comparingInt(
                        Bot::index
                )
        );

        this.bots =
                List.copyOf(sorted);

        if (this.bots.isEmpty()) {
            throw new IllegalArgumentException(
                    "No Discord bots supplied"
            );
        }

        this.http =
                HttpClient.newBuilder()
                        .connectTimeout(
                                Duration.ofSeconds(30)
                        )
                        .build();

        this.mapper =
                new ObjectMapper();

        this.lastUploadTime =
                new long[this.bots.size()];

        this.botWorkers =
                new ArrayList<>();

        /*
         * Create exactly one worker for every bot.
         */
        for (Bot bot : this.bots) {

            ExecutorService worker =
                    Executors.newSingleThreadExecutor(
                            runnable -> {

                                Thread thread =
                                        new Thread(
                                                runnable
                                        );

                                thread.setName(
                                        "discord-bot-"
                                                + bot.index()
                                );

                                thread.setDaemon(
                                        true
                                );

                                return thread;
                            }
                    );

            botWorkers.add(worker);
        }

        Log.info(
                "Discord uploader initialized"
        );

        Log.info(
                "Active bots="
                        + this.bots.size()
        );

        Log.info(
                "Rate=1 upload/sec per bot"
        );
    }

    /**
     * Existing VideoProcessor API.
     *
     * Returns:
     *
     * Map<filename, UploadResult>
     */
    public Map<String, UploadResult> uploadSegments(
            Path directory
    ) throws Exception {

        if (!Files.isDirectory(directory)) {

            throw new IOException(
                    "Not a directory: "
                            + directory
            );
        }

        List<Path> files;

        try (var stream =
                     Files.list(directory)) {

            files =
                    stream
                            .filter(
                                    Files::isRegularFile
                            )
                            .filter(
                                    p ->
                                            p.getFileName()
                                                    .toString()
                                                    .toLowerCase()
                                                    .endsWith(".m4s")
                            )
                            .sorted()
                            .toList();
        }

        return uploadSegments(
                files
        );
    }

    /**
     * Upload a list of files.
     *
     * Returns Map<filename, UploadResult>
     */
    public Map<String, UploadResult> uploadSegments(
            List<Path> files
    ) throws Exception {

        Map<String, UploadResult> results =
                new LinkedHashMap<>();

        if (files == null || files.isEmpty()) {
            return results;
        }

        Log.info(
                "UPLOADING ENCRYPTED SEGMENTS"
        );

        Log.info(
                "Segments="
                        + files.size()
        );

        Log.info(
                "Active bots="
                        + bots.size()
        );

        Log.info(
                "Rate=1 upload/sec per bot"
        );

        /*
         * Each bot receives files in round-robin order.
         *
         * Example with 48 bots:
         *
         * file 0  -> bot 0
         * file 1  -> bot 1
         * ...
         * file 47 -> bot 47
         * file 48 -> bot 0
         */
        List<List<Path>> assignments =
                new ArrayList<>();

        for (int i = 0;
             i < bots.size();
             i++) {

            assignments.add(
                    new ArrayList<>()
            );
        }

        for (int i = 0;
             i < files.size();
             i++) {

            int botPosition =
                    i % bots.size();

            Path file =
                    files.get(i);

            assignments
                    .get(botPosition)
                    .add(file);

            Log.info(
                    "ASSIGN "
                            + file.getFileName()
                            + " -> bot="
                            + bots.get(
                                    botPosition
                            ).index()
            );
        }

        /*
         * One Future per active bot.
         */
        List<Future<List<UploadResult>>> futures =
                new ArrayList<>();

        for (int i = 0;
             i < bots.size();
             i++) {

            List<Path> assigned =
                    assignments.get(i);

            if (assigned.isEmpty()) {
                continue;
            }

            final int botPosition = i;

            Future<List<UploadResult>> future =
                    botWorkers
                            .get(botPosition)
                            .submit(
                                    () ->
                                            uploadBotQueue(
                                                    botPosition,
                                                    assigned
                                            )
                            );

            futures.add(future);
        }

        /*
         * Collect all bot results.
         */
        for (Future<List<UploadResult>> future :
                futures) {

            List<UploadResult> botResults =
                    future.get();

            for (UploadResult result :
                    botResults) {

                results.put(
                        result.filename(),
                        result
                );
            }
        }

        return results;
    }

    /**
     * Existing VideoProcessor API.
     */
    public UploadResult uploadSingle(
            Path file
    ) throws Exception {

        int position =
                Math.floorMod(
                        nextBot.getAndIncrement(),
                        bots.size()
                );

        Bot bot =
                bots.get(position);

        Log.info(
                "ASSIGN "
                        + file.getFileName()
                        + " -> bot="
                        + bot.index()
        );

        return uploadWithRetry(
                file,
                bot,
                position
        );
    }

    /**
     * Process one bot's queue.
     */
    private List<UploadResult> uploadBotQueue(
            int botPosition,
            List<Path> files
    ) throws Exception {

        Bot bot =
                bots.get(
                        botPosition
                );

        List<UploadResult> results =
                new ArrayList<>();

        for (Path file : files) {

            UploadResult result =
                    uploadWithRetry(
                            file,
                            bot,
                            botPosition
                    );

            results.add(result);
        }

        return results;
    }

    /**
     * Upload using the assigned bot.
     *
     * A 429 does not move the file to bot 0.
     * The same assigned bot waits and retries.
     */
    private UploadResult uploadWithRetry(
            Path file,
            Bot bot,
            int botPosition
    ) throws Exception {

        while (true) {

            waitForBotRateLimit(
                    botPosition
            );

            try {

                UploadResult result =
                        sendFile(
                                file,
                                bot
                        );

                Log.info(
                        "[OK]   "
                                + file.getFileName()
                                + " -> bot="
                                + result.botIndex()
                                + " message="
                                + result.messageId()
                                + " attachment="
                                + result.attachmentId()
                );

                return result;

            } catch (RateLimitedException e) {

                Log.warn(
                        "429 for "
                                + file.getFileName()
                                + " on bot="
                                + bot.index()
                                + ", retry_after="
                                + e.retryAfter
                                + "s"
                );

                long waitMs =
                        Math.max(
                                1000L,
                                (long)
                                        Math.ceil(
                                                e.retryAfter
                                                        * 1000.0
                                        )
                        );

                Thread.sleep(
                        waitMs
                );

            } catch (Exception e) {

                Log.warn(
                        "Upload failed for "
                                + file.getFileName()
                                + " on bot="
                                + bot.index()
                                + ": "
                                + e.getMessage()
                );

                throw e;
            }
        }
    }

    /**
     * Maximum one upload start per second
     * for each individual bot.
     */
    private void waitForBotRateLimit(
            int botPosition
    ) throws InterruptedException {

        synchronized (rateLock) {

            long now =
                    System.currentTimeMillis();

            long last =
                    lastUploadTime[
                            botPosition
                    ];

            long wait =
                    1000L
                            - (now - last);

            if (last != 0L && wait > 0) {

                rateLock.wait(wait);
            }

            lastUploadTime[
                    botPosition
            ] =
                    System.currentTimeMillis();

            rateLock.notifyAll();
        }
    }

    /**
     * Actual Discord upload.
     */
    private UploadResult sendFile(
            Path file,
            Bot bot
    ) throws Exception {

        if (!Files.exists(file)) {

            throw new IOException(
                    "File does not exist: "
                            + file
            );
        }

        if (!Files.isRegularFile(file)) {

            throw new IOException(
                    "Not a regular file: "
                            + file
            );
        }

        String filename =
                file.getFileName()
                        .toString();

        byte[] data =
                Files.readAllBytes(file);

        String boundary =
                "----JavaDiscordUploader"
                        + System.nanoTime();

        byte[] body =
                buildMultipartBody(
                        boundary,
                        filename,
                        data
                );

        String url =
                "https://discord.com/api/v10/channels/"
                        + config.discordChannelId()
                        + "/messages";

        HttpRequest request =
                HttpRequest.newBuilder()
                        .uri(
                                URI.create(url)
                        )
                        .timeout(
                                Duration.ofSeconds(
                                        config.uploadTimeoutSeconds()
                                )
                        )
                        .header(
                                "Authorization",
                                "Bot "
                                        + bot.token()
                        )
                        .header(
                                "User-Agent",
                                "DASH-DRM-Uploader/2.0"
                        )
                        .header(
                                "Content-Type",
                                "multipart/form-data; boundary="
                                        + boundary
                        )
                        .POST(
                                HttpRequest.BodyPublishers
                                        .ofByteArray(
                                                body
                                        )
                        )
                        .build();

        HttpResponse<String> response =
                http.send(
                        request,
                        HttpResponse.BodyHandlers
                                .ofString()
                );

        int status =
                response.statusCode();

        /*
         * Discord rate limit.
         */
        if (status == 429) {

            throw new RateLimitedException(
                    parseRetryAfter(
                            response.body()
                    )
            );
        }

        /*
         * Other Discord error.
         */
        if (status < 200
                || status >= 300) {

            throw new IOException(
                    "Discord upload failed. HTTP "
                            + status
                            + ": "
                            + response.body()
            );
        }

        JsonNode json =
                mapper.readTree(
                        response.body()
                );

        String messageId =
                json.path("id")
                        .asText("");

        if (messageId.isBlank()) {

            throw new IOException(
                    "Discord response missing message id"
            );
        }

        JsonNode attachments =
                json.path(
                        "attachments"
                );

        if (!attachments.isArray()
                || attachments.isEmpty()) {

            throw new IOException(
                    "Discord response contains no attachment"
            );
        }

        JsonNode attachment =
                attachments.get(0);

        String attachmentId =
                attachment
                        .path("id")
                        .asText("");

        if (attachmentId.isBlank()) {

            throw new IOException(
                    "Discord response missing attachment id"
            );
        }

        /*
         * IMPORTANT:
         *
         * Use the actual assigned bot index.
         */
        String resolverUrl =
                config.cdnWorkerUrl()
                        + "/"
                        + bot.index()
                        + "/"
                        + messageId
                        + "/"
                        + attachmentId;

        return new UploadResult(
                filename,
                bot.index(),
                messageId,
                attachmentId,
                resolverUrl
        );
    }

    private byte[] buildMultipartBody(
            String boundary,
            String filename,
            byte[] data
    ) throws IOException {

        ByteArrayOutputStream output =
                new ByteArrayOutputStream();

        String header =
                "--"
                        + boundary
                        + "\r\n"
                        + "Content-Disposition: form-data; "
                        + "name=\"files[0]\"; filename=\""
                        + escapeFilename(filename)
                        + "\"\r\n"
                        + "Content-Type: application/octet-stream\r\n"
                        + "\r\n";

        output.write(
                header.getBytes(
                        StandardCharsets.UTF_8
                )
        );

        output.write(data);

        output.write(
                (
                        "\r\n--"
                                + boundary
                                + "--\r\n"
                ).getBytes(
                        StandardCharsets.UTF_8
                )
        );

        return output.toByteArray();
    }

    private String escapeFilename(
            String filename
    ) {

        return filename
                .replace("\\", "_")
                .replace("\"", "_")
                .replace("\r", "_")
                .replace("\n", "_");
    }

    private double parseRetryAfter(
            String body
    ) {

        try {

            JsonNode json =
                    mapper.readTree(
                            body
                    );

            return json
                    .path("retry_after")
                    .asDouble(1.0);

        } catch (Exception ignored) {

            return 1.0;
        }
    }

    public record Bot(
            int index,
            String token
    ) {
    }

    public record UploadResult(
            String filename,
            int botIndex,
            String messageId,
            String attachmentId,
            String resolverUrl
    ) {
    }

    private static final class RateLimitedException
            extends Exception {

        private final double retryAfter;

        private RateLimitedException(
                double retryAfter
        ) {

            this.retryAfter =
                    retryAfter;
        }
    }

    @Override
    public void close() {

        for (ExecutorService worker :
                botWorkers) {

            worker.shutdown();
        }

        for (ExecutorService worker :
                botWorkers) {

            try {

                if (!worker.awaitTermination(
                        10,
                        TimeUnit.SECONDS
                )) {

                    worker.shutdownNow();
                }

            } catch (InterruptedException e) {

                worker.shutdownNow();

                Thread.currentThread()
                        .interrupt();
            }
        }
    }
}
