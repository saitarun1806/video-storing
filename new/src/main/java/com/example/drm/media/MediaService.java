
package com.example.drm.media;

import com.example.drm.config.Config;
import com.example.drm.util.CommandRunner;
import com.example.drm.util.Log;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.FileNotFoundException;
import java.io.IOException;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class MediaService {

    private final Config config;
    private final ObjectMapper mapper = new ObjectMapper();

    public MediaService(Config config) {
        this.config = config;
    }

    public Path prepareSource(
            String input,
            Path job
    ) throws Exception {

        input = input.trim();

        if (input.isBlank()) {
            throw new IllegalArgumentException(
                    "Empty input"
            );
        }

        /*
         * Local file.
         */
        if (!isUrl(input)) {

            Path path =
                    Path.of(input)
                            .toAbsolutePath();

            if (!Files.isRegularFile(path)) {
                throw new FileNotFoundException(
                        path.toString()
                );
            }

            return path;
        }

        /*
         * HTTP/HTTPS source.
         */
        URI uri = URI.create(input);

        String path =
                uri.getPath();

        String name;

        if (path == null || path.isBlank()) {
            name = "source.mkv";
        } else {
            Path uriPath = Path.of(path);
            Path fileName = uriPath.getFileName();

            name = fileName == null
                    ? "source.mkv"
                    : fileName.toString();
        }

        if (name.isBlank()) {
            name = "source.mkv";
        }

        name = name.replaceAll(
                "[^A-Za-z0-9._-]",
                "_"
        );

        Path destination =
                job.resolve("source")
                        .resolve(name);

        Files.createDirectories(
                destination.getParent()
        );

        CommandRunner.run(
                List.of(
                        config.ffmpeg(),
                        "-y",
                        "-hide_banner",
                        "-loglevel",
                        "warning",
                        "-i",
                        input,
                        "-map",
                        "0",
                        "-c",
                        "copy",
                        destination.toString()
                ),
                job
        );

        if (!Files.isRegularFile(destination)
                || Files.size(destination) == 0) {

            throw new IOException(
                    "Source was not created"
            );
        }

        return destination;
    }

    public boolean isUrl(String value) {

        try {

            String scheme =
                    URI.create(value)
                            .getScheme();

            return "http".equalsIgnoreCase(scheme)
                    || "https".equalsIgnoreCase(scheme);

        } catch (Exception e) {

            return false;
        }
    }

    public Tracks detectTracks(
            Path source
    ) throws Exception {

        CommandRunner.Result result =
                CommandRunner.run(
                        List.of(
                                config.ffprobe(),
                                "-v",
                                "error",
                                "-print_format",
                                "json",
                                "-show_streams",
                                "-show_format",
                                source.toString()
                        ),
                        source.getParent()
                );

        JsonNode root =
                mapper.readTree(result.output());

        List<AudioTrack> audios =
                new ArrayList<>();

        JsonNode video = null;

        int audioIndex = 0;

        for (JsonNode stream :
                root.path("streams")) {

            String type =
                    stream.path("codec_type")
                            .asText();

            /*
             * First video stream.
             */
            if ("video".equals(type)
                    && video == null) {

                video = stream;
            }

            /*
             * Audio streams.
             */
            if ("audio".equals(type)) {

                JsonNode tags =
                        stream.path("tags");

                String language =
                        tags.path("language")
                                .asText(
                                        tags.path("LANGUAGE")
                                                .asText(
                                                        tags.path("lang")
                                                                .asText("")
                                                )
                                )
                                .trim()
                                .toLowerCase(
                                        Locale.ROOT
                                );

                if (language.isBlank()) {
                    language =
                            "und"
                                    + (audioIndex + 1);
                }

                language =
                        language.replaceAll(
                                "[^a-z0-9-]",
                                ""
                        );

                if (language.isBlank()) {
                    language =
                            "und"
                                    + (audioIndex + 1);
                }

                String title =
                        tags.path("title")
                                .asText(
                                        tags.path("handler_name")
                                                .asText(
                                                        tags.path("handler")
                                                                .asText("")
                                                )
                                )
                                .trim();

                if (title.isBlank()) {

                    title =
                            language.startsWith("und")
                                    ? "Audio "
                                            + (audioIndex + 1)
                                    : language.toUpperCase(
                                            Locale.ROOT
                                    );
                }

                audios.add(
                        new AudioTrack(
                                audioIndex,
                                language,
                                title,
                                stream.path("codec_name")
                                        .asText(),
                                stream.path("channels")
                                        .asInt(),
                                stream.path("sample_rate")
                                        .asText()
                        )
                );

                audioIndex++;
            }
        }

        if (video == null) {
            throw new IllegalStateException(
                    "No video stream found"
            );
        }

        Log.info(
                "Video: "
                        + video.path("width").asInt()
                        + "x"
                        + video.path("height").asInt()
        );

        for (AudioTrack audio : audios) {

            Log.info(
                    "Audio "
                            + (audio.sourceIndex() + 1)
                            + ": "
                            + audio.title()
                            + " ("
                            + audio.language()
                            + ") codec="
                            + audio.codec()
            );
        }

        return new Tracks(
                video,
                audios
        );
    }

    public Path createDash(
            Path source,
            Path directory,
            Tracks tracks
    ) throws Exception {

        Files.createDirectories(directory);

        Path mpd =
                directory.resolve(
                        "manifest.mpd"
                );

        List<String> command =
                new ArrayList<>(
                        List.of(
                                config.ffmpeg(),
                                "-y",
                                "-hide_banner",
                                "-loglevel",
                                "warning",
                                "-i",
                                source.toString(),

                                "-map",
                                "0:v:0",

                                "-c:v",
                                "libx264",

                                "-preset",
                                "veryfast",

                                "-profile:v",
                                "high",

                                "-level:v",
                                "4.1",

                                "-pix_fmt",
                                "yuv420p",

                                "-crf",
                                "22",

                                "-force_key_frames",
                                "expr:gte(t,n_forced*"
                                        + config.segmentDuration()
                                        + ")"
                        )
                );

        /*
         * Add every audio track.
         */
        for (int i = 0;
             i < tracks.audios().size();
             i++) {

            AudioTrack audio =
                    tracks.audios().get(i);

            command.addAll(
                    List.of(
                            "-map",
                            "0:a:"
                                    + audio.sourceIndex(),

                            "-c:a",
                            "aac",

                            "-profile:a",
                            "aac_low",

                            "-b:a",
                            "128k",

                            "-ar",
                            "48000",

                            "-ac",
                            "2",

                            "-metadata:s:a:"
                                    + i,
                            "language="
                                    + audio.language(),

                            "-metadata:s:a:"
                                    + i,
                            "title="
                                    + audio.title()
                    )
            );
        }

        /*
         * DASH adaptation sets.
         */
        List<String> adaptationSets =
                new ArrayList<>();

        adaptationSets.add(
                "id=0,streams=v"
        );

        for (int i = 0;
             i < tracks.audios().size();
             i++) {

            adaptationSets.add(
                    "id="
                            + (i + 1)
                            + ",streams="
                            + (i + 1)
            );
        }

        command.addAll(
                List.of(
                        "-f",
                        "dash",

                        "-seg_duration",
                        String.valueOf(
                                config.segmentDuration()
                        ),

                        "-use_template",
                        "1",

                        "-use_timeline",
                        "1",

                        "-adaptation_sets",
                        String.join(
                                " ",
                                adaptationSets
                        ),

                        "-init_seg_name",
                        "init-$RepresentationID$.m4s",

                        "-media_seg_name",
                        "chunk-$RepresentationID$-$Number%05d$.m4s",

                        mpd.toString()
                )
        );

        CommandRunner.run(
                command,
                directory
        );

        if (!Files.isRegularFile(mpd)) {

            throw new IOException(
                    "DASH MPD was not generated"
            );
        }

        boolean initExists;

        try (var stream =
                     Files.find(
                             directory,
                             1,
                             (path, attributes) ->
                                     path.getFileName()
                                             .toString()
                                             .startsWith("init-")
                                             && path.toString()
                                             .endsWith(".m4s")
                     )) {

            initExists =
                    stream.findAny().isPresent();
        }

        if (!initExists) {

            throw new IOException(
                    "No DASH init segments"
            );
        }

        return mpd;
    }

    public record Tracks(
            JsonNode video,
            List<AudioTrack> audios
    ) {
    }

    public record AudioTrack(
            int sourceIndex,
            String language,
            String title,
            String codec,
            int channels,
            String sampleRate
    ) {
    }
}
