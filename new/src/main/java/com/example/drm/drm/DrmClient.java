
package com.example.drm.drm;

import com.example.drm.config.Config;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class DrmClient {

    private final Config config;

    private final HttpClient httpClient =
            HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(30))
                    .build();

    private final ObjectMapper objectMapper =
            new ObjectMapper();

    public DrmClient(Config config) {
        this.config = config;
    }

    public JsonNode register(
            String videoId,
            String kid,
            String key,
            String mpd
    ) throws Exception {

        ObjectNode payload =
                objectMapper.createObjectNode();

        payload.put(
                "video_id",
                videoId
        );

        payload.put(
                "kid",
                kid.toLowerCase()
        );

        payload.put(
                "key",
                key.toLowerCase()
        );

        payload.put(
                "mpd_url",
                mpd
        );

        payload.put(
                "license_url",
                config.drmLicenseUrl()
        );

        payload.put(
                "enabled",
                true
        );

        HttpRequest request =
                HttpRequest.newBuilder(
                                URI.create(
                                        config.drmRegisterUrl()
                                )
                        )
                        .timeout(
                                Duration.ofSeconds(60)
                        )
                        .header(
                                "Authorization",
                                "Bearer "
                                        + config.drmRegisterSecret()
                        )
                        .header(
                                "Content-Type",
                                "application/json"
                        )
                        .POST(
                                HttpRequest.BodyPublishers.ofString(
                                        objectMapper.writeValueAsString(
                                                payload
                                        )
                                )
                        )
                        .build();

        HttpResponse<String> response =
                httpClient.send(
                        request,
                        HttpResponse.BodyHandlers.ofString()
                );

        if (response.statusCode() / 100 != 2) {

            throw new IllegalStateException(
                    "DRM registration HTTP "
                            + response.statusCode()
                            + ": "
                            + response.body()
            );
        }

        JsonNode result =
                objectMapper.readTree(
                        response.body()
                );

        if (!result.path("success").asBoolean(false)) {

            throw new IllegalStateException(
                    "DRM worker rejected registration: "
                            + result
            );
        }

        return result;
    }
}
