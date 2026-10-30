
package com.example.drm.util;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class CommandRunner {

    private CommandRunner() {
    }

    public static Result run(List<String> command, Path cwd)
            throws Exception {

        System.out.println("$ " + String.join(" ", command));

        ProcessBuilder processBuilder =
                new ProcessBuilder(command);

        if (cwd != null) {
            processBuilder.directory(cwd.toFile());
        }

        processBuilder.redirectErrorStream(true);

        Process process = processBuilder.start();

        String output = new String(
                process.getInputStream().readAllBytes()
        );

        int exitCode = process.waitFor();

        if (!output.isBlank()) {
            System.out.print(output);
        }

        if (exitCode != 0) {
            throw new IOException(
                    "Command failed ("
                            + exitCode
                            + "): "
                            + command.get(0)
            );
        }

        return new Result(exitCode, output);
    }

    public record Result(
            int exitCode,
            String output
    ) {
    }

    public static boolean exists(String command) {

        Path path = Path.of(command);

        if (path.isAbsolute()) {
            return Files.isRegularFile(path);
        }

        try {

            Process process =
                    new ProcessBuilder(
                            command,
                            "-version"
                    )
                            .redirectErrorStream(true)
                            .start();

            process.destroy();

            return true;

        } catch (Exception e) {

            return false;
        }
    }
}
