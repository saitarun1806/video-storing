
package com.example.drm.discord;

import com.example.drm.config.Config;
import com.example.drm.util.Log;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class DiscordBotProvider {

    private DiscordBotProvider() {
    }

    /**
     * Existing Main.java expects:
     *
     * DiscordBotProvider.load(config)
     */
    public static List<DiscordUploader.Bot> load(
            Config config
    ) throws Exception {

        String url =
                config.discordBotIndexUrl()
                        + "/admin/bots";

        Log.info("Loading Discord bots...");
        Log.info("Bot API: " + url);

        HttpClient http =
                HttpClient.newBuilder()
                        .connectTimeout(
                                Duration.ofSeconds(30)
                        )
                        .build();

        ObjectMapper mapper =
                new ObjectMapper();

        HttpRequest request =
                HttpRequest.newBuilder()
                        .uri(
                                URI.create(url)
                        )
                        .timeout(
                                Duration.ofSeconds(60)
                        )
                        .header(
                                "Authorization",
                                "Bearer "
                                        + config.adminSecret()
                        )
                        .header(
                                "Accept",
                                "application/json"
                        )
                        .GET()
                        .build();

        HttpResponse<String> response =
                http.send(
                        request,
                        HttpResponse.BodyHandlers
                                .ofString()
                );

        if (response.statusCode() < 200
                || response.statusCode() >= 300) {

            throw new IllegalStateException(
                    "Bot API returned HTTP "
                            + response.statusCode()
                            + ": "
                            + response.body()
            );
        }

        JsonNode root =
                mapper.readTree(
                        response.body()
                );

        if (!root.path("success")
                .asBoolean(false)) {

            throw new IllegalStateException(
                    "Bot API returned success=false: "
                            + response.body()
            );
        }

        JsonNode botsNode =
                root.path("bots");

        if (!botsNode.isArray()) {

            throw new IllegalStateException(
                    "Bot API response does not contain "
                            + "a bots array"
            );
        }

        List<DiscordUploader.Bot> bots =
                new ArrayList<>();

        Set<Integer> indexes =
                new HashSet<>();

        for (JsonNode node : botsNode) {

            int index =
                    node.path("index")
                            .asInt(-1);

            String token =
                    node.path("token")
                            .asText("")
                            .trim();

            if (index < 0) {
                continue;
            }

            if (token.isBlank()) {
                continue;
            }

            if (!indexes.add(index)) {

                throw new IllegalStateException(
                        "Duplicate Discord bot index: "
                                + index
                );
            }

            bots.add(
                    new DiscordUploader.Bot(
                            index,
                            token
                    )
            );
        }

        if (bots.isEmpty()) {

            throw new IllegalStateException(
                    "No Discord bots were loaded"
            );
        }

        /*
         * Always use the actual worker index.
         */
        bots.sort(
                Comparator.comparingInt(
                        DiscordUploader.Bot::index
                )
        );

        StringBuilder indices =
                new StringBuilder();

        for (DiscordUploader.Bot bot : bots) {

            if (!indices.isEmpty()) {
                indices.append(", ");
            }

            indices.append(
                    bot.index()
            );
        }

        Log.info(
                "Discord bots loaded: "
                        + bots.size()
        );

        Log.info(
                "Loaded bot indices: ["
                        + indices
                        + "]"
        );

        return List.copyOf(bots);
    }
}
