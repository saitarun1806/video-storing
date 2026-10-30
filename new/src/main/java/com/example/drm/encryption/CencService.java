package com.example.drm.encryption;

import com.example.drm.config.Config;import com.example.drm.util.CommandRunner;import com.example.drm.util.Log;
import java.nio.file.*;import java.util.*;import java.util.regex.*;

public class CencService {
 private final Config c; public CencService(Config c){this.c=c;}
 public void encryptDash(Path dir,String kid,String key) throws Exception{
  List<Path> inits=Files.list(dir).filter(p->p.getFileName().toString().matches("init-.+\\.m4s")).sorted().toList(); if(inits.isEmpty())throw new IOException("No init segments");
  Map<String,Path> clear=new HashMap<>();
  for(Path init:inits){String rep=representation(init);Path cp=dir.resolve("init-"+rep+".clear.m4s");Files.copy(init,cp,StandardCopyOption.REPLACE_EXISTING);clear.put(rep,cp);Path enc=dir.resolve("init-"+rep+".encrypted.m4s");encryptInit(cp,enc,kid,key);verifyKid(enc,kid);Files.move(enc,init,StandardCopyOption.REPLACE_EXISTING);}
  List<Path> media=Files.list(dir).filter(p->p.getFileName().toString().matches("chunk-.+?-\\d+\\.m4s")).sorted().toList();
  for(Path f:media){Matcher m=Pattern.compile("chunk-(.+?)-\\d+\\.m4s").matcher(f.getFileName().toString());if(!m.matches())continue;Path ci=clear.get(m.group(1));if(ci==null)throw new IOException("No matching init for "+f);Path enc=dir.resolve(f.getFileName()+".encrypted");encryptMedia(f,enc,ci,kid,key);Files.move(enc,f,StandardCopyOption.REPLACE_EXISTING);}
 }
 private void encryptInit(Path in,Path out,String kid,String key)throws Exception{CommandRunner.run(List.of(c.mp4encrypt(),"--method","MPEG-CENC","--key","1:"+key+":random","--property","1:KID:"+kid,"--global-option","mpeg-cenc.eme-pssh:true",in.toString(),out.toString()),out.getParent());}
 private void encryptMedia(Path in,Path out,Path init,String kid,String key)throws Exception{CommandRunner.run(List.of(c.mp4encrypt(),"--method","MPEG-CENC","--key","1:"+key+":random","--property","1:KID:"+kid,"--global-option","mpeg-cenc.eme-pssh:true","--fragments-info",init.toString(),in.toString(),out.toString()),out.getParent());}
 private void verifyKid(Path file,String expected)throws Exception{var r=CommandRunner.run(List.of(c.mp4dump(),"--verbosity","1",file.toString()),file.getParent());String s=r.output().replaceAll("[^0-9a-fA-F]","").toLowerCase(Locale.ROOT);if(!s.contains(expected.toLowerCase(Locale.ROOT)))Log.warn("mp4dump output did not contain expected KID for "+file.getFileName()+"; inspect Bento4 output if needed");}
 private String representation(Path p){Matcher m=Pattern.compile("init-(.+)\\.m4s").matcher(p.getFileName().toString());if(!m.matches())throw new IllegalArgumentException("Cannot determine representation from "+p);return m.group(1);}
 public static String videoId(){ java.security.SecureRandom r=new java.security.SecureRandom(); return (char)('1'+r.nextInt(9))+String.format("%017d",r.nextLong(0,100000000000000000L)); }
 public static String hex16(){byte[] b=new byte[16];new java.security.SecureRandom().nextBytes(b);StringBuilder s=new StringBuilder();for(byte x:b)s.append(String.format("%02x",x));return s.toString();}
}
