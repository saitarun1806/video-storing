package com.example.drm.media;

import com.example.drm.config.Config;
import com.example.drm.util.CommandRunner;
import com.example.drm.util.Log;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;import java.nio.file.*;import java.util.*;import java.util.regex.Pattern;

public class MediaService {
 private final Config c; private final ObjectMapper mapper=new ObjectMapper();
 public MediaService(Config c){this.c=c;}
 public Path prepareSource(String input,Path job) throws Exception{
  input=input.trim(); if(input.isBlank())throw new IllegalArgumentException("Empty input");
  if(!isUrl(input)){Path p=Path.of(input).toAbsolutePath();if(!Files.isRegularFile(p))throw new FileNotFoundException(p.toString());return p;}
  String name=Path.of(URI.create(input).getPath()==null?"source.mkv":URI.create(input).getPath()).getFileName().toString();
  if(name.isBlank())name="source.mkv"; name=name.replaceAll("[^A-Za-z0-9._-]","_");
  Path dest=job.resolve("source").resolve(name);Files.createDirectories(dest.getParent());
  CommandRunner.run(List.of(c.ffmpeg(),"-y","-hide_banner","-loglevel","warning","-i",input,"-map","0","-c","copy",dest.toString()),job);
  if(!Files.isRegularFile(dest)||Files.size(dest)==0)throw new IOException("Source was not created"); return dest;
 }
 public boolean isUrl(String s){try{String x=URI.create(s).getScheme();return "http".equalsIgnoreCase(x)||"https".equalsIgnoreCase(x);}catch(Exception e){return false;}}
 public Tracks detectTracks(Path source) throws Exception{
  var r=CommandRunner.run(List.of(c.ffprobe(),"-v","error","-print_format","json","-show_streams","-show_format",source.toString()),source.getParent());
  JsonNode root=mapper.readTree(r.output()); List<AudioTrack> audios=new ArrayList<>(); JsonNode video=null; int ai=0;
  for(JsonNode s:root.path("streams")){String type=s.path("codec_type").asText(); if("video".equals(type)&&video==null)video=s; if("audio".equals(type)){
    JsonNode tags=s.path("tags");String lang=tags.path("language").asText(tags.path("LANGUAGE").asText(tags.path("lang").asText(""))).trim().toLowerCase(Locale.ROOT);
    if(lang.isBlank())lang="und"+(ai+1);lang=lang.replaceAll("[^a-z0-9-]","");if(lang.isBlank())lang="und"+(ai+1);
    String title=tags.path("title").asText(tags.path("handler_name").asText(tags.path("handler").asText(""))).trim();if(title.isBlank())title=lang.startsWith("und")?"Audio "+(ai+1):lang.toUpperCase(Locale.ROOT);
    audios.add(new AudioTrack(ai,lang,title,s.path("codec_name").asText(),s.path("channels").asInt(),s.path("sample_rate").asText()));ai++;
  }}
  if(video==null)throw new IllegalStateException("No video stream found");
  Log.info("Video: "+video.path("width").asInt()+"x"+video.path("height").asInt()); for(AudioTrack a:audios)Log.info("Audio "+(a.sourceIndex()+1)+": "+a.title()+" ("+a.language()+") codec="+a.codec());
  return new Tracks(video,audios);
 }
 public Path createDash(Path source,Path dir,Tracks tracks) throws Exception{
  Files.createDirectories(dir);Path mpd=dir.resolve("manifest.mpd");List<String> cmd=new ArrayList<>(List.of(c.ffmpeg(),"-y","-hide_banner","-loglevel","warning","-i",source.toString(),"-map","0:v:0","-c:v","libx264","-preset","veryfast","-profile:v","high","-level:v","4.1","-pix_fmt","yuv420p","-crf","22","-force_key_frames","expr:gte(t,n_forced*"+c.segmentDuration()+")"));
  for(int i=0;i<tracks.audios().size();i++){AudioTrack a=tracks.audios().get(i);cmd.addAll(List.of("-map","0:a:"+a.sourceIndex(),"-c:a","aac","-profile:a","aac_low","-b:a","128k","-ar","48000","-ac","2","-metadata:s:a:"+i,"language="+a.language(),"-metadata:s:a:"+i,"title="+a.title()));}
  List<String> sets=new ArrayList<>();sets.add("id=0,streams=v");for(int i=0;i<tracks.audios().size();i++)sets.add("id="+(i+1)+",streams="+(i+1));
  cmd.addAll(List.of("-f","dash","-seg_duration",""+c.segmentDuration(),"-use_template","1","-use_timeline","1","-adaptation_sets",String.join(" ",sets),"-init_seg_name","init-$RepresentationID$.m4s","-media_seg_name","chunk-$RepresentationID$-$Number%05d$.m4s",mpd.toString()));
  CommandRunner.run(cmd,dir);if(!Files.isRegularFile(mpd))throw new IOException("DASH MPD was not generated");if(!Files.find(dir,1,(p,a)->p.getFileName().toString().startsWith("init-")&&p.toString().endsWith(".m4s")).findAny().isPresent())throw new IOException("No DASH init segments");return mpd;
 }
 public record Tracks(JsonNode video,List<AudioTrack> audios){}
 public record AudioTrack(int sourceIndex,String language,String title,String codec,int channels,String sampleRate){}
}
