package ro.cobrabm.fexdroid;
import android.content.Context;
import android.content.SharedPreferences;
/** SotC identity and one-way migration from the original GoW3-derived boot test. */
public final class SotcPaths {
  public static boolean isSotc(Context c){return "com.sotc.android.daedalus".equals(c.getPackageName());}
  public static String baseName(Context c){return isSotc(c)?"sotcport":"gow3port";}
  public static String prefsName(Context c){return isSotc(c)?"sotc":"gow3";}
  public static String iniName(Context c){return isSotc(c)?"sotc.ini":"gow3.ini";}
  public static void migratePreferences(Context c){
    if(!isSotc(c))return;
    SharedPreferences legacy=c.getSharedPreferences("gow3",Context.MODE_PRIVATE);
    SharedPreferences target=c.getSharedPreferences("sotc",Context.MODE_PRIVATE);
    SharedPreferences.Editor e=target.edit();
    for(String key:new String[]{"game_dir","update_dir","gpu_driver","controller_overlay","swap_square_triangle"}){
      if(target.contains(key)||!legacy.contains(key))continue;
      Object v=legacy.getAll().get(key);
      if(v instanceof String)e.putString(key,(String)v);
      else if(v instanceof Boolean)e.putBoolean(key,(Boolean)v);
    }
    e.apply();
  }
  private SotcPaths(){}
}
