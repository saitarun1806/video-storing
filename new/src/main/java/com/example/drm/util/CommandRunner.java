package com.example.drm.util;
import java.io.*;import java.nio.file.*;import java.util.*;
public final class CommandRunner {
 private CommandRunner(){}
 public static Result run(List<String> command, Path cwd) throws Exception {
  System.out.println("$ "+String.join(" ",command));
  ProcessBuilder pb=new ProcessBuilder(command); if(cwd!=null)pb.directory(cwd.toFile()); pb.redirectErrorStream(true);
  Process p=pb.start(); String out=new String(p.getInputStream().readAllBytes()); int code=p.waitFor();
  if(!out.isBlank())System.out.print(out); if(code!=0)throw new IOException("Command failed ("+code+"): "+command.get(0)); return new Result(code,out);
 }
 public record Result(int exitCode,String output){}
 public static boolean exists(String c){
  if(Path.of(c).isAbsolute()) return Files.isRegularFile(Path.of(c));
  try { Process p=new ProcessBuilder(c,"-version").redirectErrorStream(true).start(); p.destroy(); return true; } catch(Exception e){ return false; }
 }
}
