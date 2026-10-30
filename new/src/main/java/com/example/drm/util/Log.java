package com.example.drm.util;
public final class Log {
 private Log(){}
 public static void banner(String s){System.out.println("\n"+"=".repeat(72)+"\n"+s+"\n"+"=".repeat(72));}
 public static void info(String s){System.out.println("[INFO] "+s);}
 public static void ok(String s){System.out.println("[OK]   "+s);}
 public static void warn(String s){System.out.println("[WARN] "+s);}
 public static void err(String s){System.err.println("[ERR]  "+s);}
 public static void job(int n,String s){System.out.println("[JOB "+n+"] "+s);}
}
