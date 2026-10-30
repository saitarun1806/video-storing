package com.example.drm.discord;
import com.example.drm.config.Config;import com.fasterxml.jackson.databind.*;import java.net.*;import java.net.http.*;import java.time.*;import java.util.*;
public class DiscordBotProvider {
 public static List<DiscordUploader.Bot> load(Config c)throws Exception{
  HttpClient h=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(30)).build();HttpRequest r=HttpRequest.newBuilder(URI.create(c.discordBotIndexUrl()+"/admin/bots")).timeout(Duration.ofSeconds(30)).header("Authorization","Bearer "+c.adminSecret()).GET().build();HttpResponse<String> res=h.send(r,HttpResponse.BodyHandlers.ofString());if(res.statusCode()/100!=2)throw new IllegalStateException("Bot worker HTTP "+res.statusCode()+": "+res.body());JsonNode root=new ObjectMapper().readTree(res.body());if(!root.path("success").asBoolean(false))throw new IllegalStateException("Bot worker rejected request");List<DiscordUploader.Bot> out=new ArrayList<>();for(JsonNode b:root.path("bots")){if(b.has("index")&&!b.path("token").asText().isBlank())out.add(new DiscordUploader.Bot(b.path("index").asInt(),b.path("token").asText().trim()));}out.sort(Comparator.comparingInt(DiscordUploader.Bot::index));if(out.isEmpty())throw new IllegalStateException("No Discord bots returned");return out;
 }
}
