
package com.example.drm.encryption;

import com.example.drm.config.Config;
import com.example.drm.util.CommandRunner;
import com.example.drm.util.Log;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.SecureRandom;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class CencService {

    private final Config config;

    public CencService(Config config) {
        this.config = config;
    }

    public void encryptDash(
            Path directory,
            String kid,
            String key
    ) throws Exception {

        /*
         * Find all DASH initialization segments.
         */
        List<Path> initSegments;

        try (var stream = Files.list(directory)) {

            initSegments =
                    stream
                            .filter(
                                    path ->
                                            path.getFileName()
                                                    .toString()
                                                    .matches(
                                                            "init-.+\\.m4s"
                                                    )
                            )
                            .sorted()
                            .toList();
        }

        if (initSegments.isEmpty()) {

            throw new IOException(
                    "No init segments"
            );
        }

        /*
         * Keep a clear copy of each initialization
         * segment so Bento4 can use it as fragments-info
         * for the media segments.
         */
        Map<String, Path> clearInits =
                new HashMap<>();

        /*
         * Encrypt initialization segments.
         */
        for (Path init : initSegments) {

            String representation =
                    representation(init);

            Path clearInit =
                    directory.resolve(
                            "init-"
                                    + representation
                                    + ".clear.m4s"
                    );

            Files.copy(
                    init,
                    clearInit,
                    StandardCopyOption.REPLACE_EXISTING
            );

            clearInits.put(
                    representation,
                    clearInit
            );

            Path encryptedInit =
                    directory.resolve(
                            "init-"
                                    + representation
                                    + ".encrypted.m4s"
                    );

            encryptInit(
                    clearInit,
                    encryptedInit,
                    kid,
                    key
            );

            /*
             * Verify the generated initialization
             * segment contains the expected KID.
             */
            verifyKid(
                    encryptedInit,
                    kid
            );

            /*
             * Replace the original init segment
             * with the encrypted version.
             */
            Files.move(
                    encryptedInit,
                    init,
                    StandardCopyOption.REPLACE_EXISTING
            );
        }

        /*
         * Find all media segments.
         */
        List<Path> mediaSegments;

        try (var stream = Files.list(directory)) {

            mediaSegments =
                    stream
                            .filter(
                                    path ->
                                            path.getFileName()
                                                    .toString()
                                                    .matches(
                                                            "chunk-.+?-\\d+\\.m4s"
                                                    )
                            )
                            .sorted()
                            .toList();
        }

        /*
         * Encrypt each media segment.
         */
        Pattern mediaPattern =
                Pattern.compile(
                        "chunk-(.+?)-\\d+\\.m4s"
                );

        for (Path media : mediaSegments) {

            Matcher matcher =
                    mediaPattern.matcher(
                            media.getFileName().toString()
                    );

            if (!matcher.matches()) {
                continue;
            }

            String representation =
                    matcher.group(1);

            Path clearInit =
                    clearInits.get(
                            representation
                    );

            if (clearInit == null) {

                throw new IOException(
                        "No matching init for "
                                + media
                );
            }

            Path encryptedMedia =
                    directory.resolve(
                            media.getFileName()
                                    + ".encrypted"
                    );

            encryptMedia(
                    media,
                    encryptedMedia,
                    clearInit,
                    kid,
                    key
            );

            /*
             * Replace original media segment
             * with encrypted version.
             */
            Files.move(
                    encryptedMedia,
                    media,
                    StandardCopyOption.REPLACE_EXISTING
            );
        }
    }

    private void encryptInit(
            Path input,
            Path output,
            String kid,
            String key
    ) throws Exception {

        CommandRunner.run(
                List.of(
                        config.mp4encrypt(),

                        "--method",
                        "MPEG-CENC",

                        "--key",
                        "1:"
                                + key
                                + ":random",

                        "--property",
                        "1:KID:"
                                + kid,

                        "--global-option",
                        "mpeg-cenc.eme-pssh:true",

                        input.toString(),
                        output.toString()
                ),
                output.getParent()
        );
    }

    private void encryptMedia(
            Path input,
            Path output,
            Path init,
            String kid,
            String key
    ) throws Exception {

        CommandRunner.run(
                List.of(
                        config.mp4encrypt(),

                        "--method",
                        "MPEG-CENC",

                        "--key",
                        "1:"
                                + key
                                + ":random",

                        "--property",
                        "1:KID:"
                                + kid,

                        "--global-option",
                        "mpeg-cenc.eme-pssh:true",

                        "--fragments-info",
                        init.toString(),

                        input.toString(),
                        output.toString()
                ),
                output.getParent()
        );
    }

    private void verifyKid(
            Path file,
            String expectedKid
    ) throws Exception {

        CommandRunner.Result result =
                CommandRunner.run(
                        List.of(
                                config.mp4dump(),
                                "--verbosity",
                                "1",
                                file.toString()
                        ),
                        file.getParent()
                );

        String output =
                result.output()
                        .replaceAll(
                                "[^0-9a-fA-F]",
                                ""
                        )
                        .toLowerCase(
                                Locale.ROOT
                        );

        if (!output.contains(
                expectedKid.toLowerCase(
                        Locale.ROOT
                )
        )) {

            Log.warn(
                    "mp4dump output did not contain "
                            + "expected KID for "
                            + file.getFileName()
                            + "; inspect Bento4 output "
                            + "if needed"
            );
        }
    }

    private String representation(
            Path path
    ) {

        Matcher matcher =
                Pattern.compile(
                        "init-(.+)\\.m4s"
                ).matcher(
                        path.getFileName()
                                .toString()
                );

        if (!matcher.matches()) {

            throw new IllegalArgumentException(
                    "Cannot determine representation from "
                            + path
            );
        }

        return matcher.group(1);
    }

    public static String videoId() {

        SecureRandom random =
                new SecureRandom();

        return (char) (
                '1' + random.nextInt(9)
        )
                + String.format(
                        "%017d",
                        random.nextLong(
                                0,
                                100000000000000000L
                        )
                );
    }

    public static String hex16() {

        byte[] bytes =
                new byte[16];

        new SecureRandom()
                .nextBytes(bytes);

        StringBuilder result =
                new StringBuilder();

        for (byte value : bytes) {

            result.append(
                    String.format(
                            "%02x",
                            value
                    )
            );
        }

        return result.toString();
    }
}
