package ro.cobrabm.fexdroid;

import android.content.Context;
import android.content.SharedPreferences;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Locale;
import java.util.Map;

/** Matches the relevant keys from The Order PC port's write_runtime_config() for Android. */
final class Order1886LauncherConfig {
    private Order1886LauncherConfig(){}

    static File write(Context ctx, File user) throws IOException {
        if(!user.isDirectory()&&!user.mkdirs())throw new IOException("Não é possível criar perfil do jogo");
        SharedPreferences p=ctx.getSharedPreferences("order1886",Context.MODE_PRIVATE);
        int fps=p.getInt("fps",30);
        int width=p.getInt("width",1920);
        String aspect=p.getString("aspect","original");
        boolean vsync=p.getBoolean("vsync",false);
        if(fps!=30&&fps!=60)throw new IOException("FPS inválido");
        if(width!=1920&&width!=1600&&width!=1280)throw new IOException("Resolução inválida");
        if(!"original".equals(aspect)&&!"16:9".equals(aspect))throw new IOException("Proporção inválida");
        // Exact size() and scene_size() rules from order1886_resolution.py.
        int height="16:9".equals(aspect)?Math.round((width*9f/16f)/8f)*8:
                                           Math.round(width/2.4f);
        String scene=width==1920?"native":String.format(Locale.US,"%dx%d",width,height);
        StringBuilder c=new StringBuilder();
        c.append("# The Order: 1886 Android Bionic runtime settings.\n");
        c.append("display_mode=fullscreen\n");
        c.append("vsync=").append(vsync?1:0).append('\n');
        c.append("show_fps=0\n");
        c.append("fps_limit=").append(fps).append('\n');
        c.append("render_resolution=").append(scene).append('\n');
        c.append("presentation_filter=").append(width==1920?"fsr1":"linear").append('\n');
        c.append("output_res=automatic\n");
        c.append("rcas=0\nrcas_strength=0\n");
        c.append("anisotropy=0\nframes_queued=1\nasync_shaders=1\n");
        c.append("overlay_fps=0\noverlay_frametime=0\noverlay_gpu=0\noverlay_cpu=0\noverlay_ram=0\noverlay_vram=0\n");
        c.append("mouse_look=0\nmouse_sensitivity=100\nmouse_invert_y=0\n");
        File target=new File(user,"runtime.ini");
        File pending=new File(user,"runtime.ini.tmp");
        Files.write(pending.toPath(),c.toString().getBytes(StandardCharsets.UTF_8));
        if(target.exists()&&!target.delete())throw new IOException("Não foi possível substituir runtime.ini");
        if(!pending.renameTo(target))throw new IOException("Não foi possível ativar runtime.ini");
        return target;
    }

    static void environment(Context ctx,File user,Map<String,String> env){
        SharedPreferences p=ctx.getSharedPreferences("order1886",Context.MODE_PRIVATE);
        env.put("ORDER1886_CONFIG",new File(user,"runtime.ini").getAbsolutePath());
        env.put("ORDER1886_USER_DIR",user.getAbsolutePath());
        env.put("ORDER1886_FPS_LIMIT",Integer.toString(p.getInt("fps",30)));
        env.put("ORDER1886_VBLANK_HZ","60");
        env.put("ORDER1886_LANGUAGE","1");
        env.put("ORDER1886_HTILE","0");
        env.put("ORDER1886_PIPELINE_BINARIES","0");
        env.put("ORDER1886_PARALLEL_WARMUP","0");
        env.put("ORDER1886_DEFERRED_READBACK","0");
        env.put("ORDER1886_PREP_WORKERS","0");
        env.put("ORDER1886_STREAM_MEMORY","cached");
        env.put("ORDER1886_SETTINGS_MENU","0");
    }
}
