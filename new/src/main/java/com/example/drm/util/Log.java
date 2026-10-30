
package com.example.drm.util;

public final class Log {

    private Log() {
    }

    public static void banner(String message) {

        System.out.println(
                "\n"
                        + "=".repeat(72)
                        + "\n"
                        + message
                        + "\n"
                        + "=".repeat(72)
        );
    }

    public static void info(String message) {
        System.out.println("[INFO] " + message);
    }

    public static void ok(String message) {
        System.out.println("[OK]   " + message);
    }

    public static void warn(String message) {
        System.out.println("[WARN] " + message);
    }

    public static void err(String message) {
        System.err.println("[ERR]  " + message);
    }

    public static void job(int number, String message) {
        System.out.println(
                "[JOB " + number + "] " + message
        );
    }
}
