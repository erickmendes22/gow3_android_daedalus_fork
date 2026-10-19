package ro.cobrabm.fexdroid;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.FileReader;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.Properties;

/**
 * Adapted directly from ducvd89/Bloodborne-Android's FrameGenDialog.
 * Uses the SAME Bloodframe state contract: multiplier, flow, performance, fp16.
 * Applies live via the Vulkan presenter's native Gow3LsfgState::Watcher.
 */
final class FrameGenDialog {
    private static final String[] VALUES={"0","2","3","4"};
    private static final String[] NAMES={"Off","2× frames","3× frames","4× frames"};
    private final Activity activity;
    private final File base;
    private final SharedPreferences prefs;
    private final Runnable applied;
    FrameGenDialog(Activity activity,File base,Runnable applied) {
        this.activity=activity; this.base=base; this.applied=applied;
        prefs=activity.getSharedPreferences("gow3",Activity.MODE_PRIVATE);
    }
    private int dp(float n) {
        return Math.round(n*activity.getResources().getDisplayMetrics().density);
    }
    private TextView note(LinearLayout parent,String text,float alpha) {
        TextView view=new TextView(activity); view.setTextSize(13); view.setAlpha(alpha);
        view.setText(text); view.setPadding(0,dp(5),0,dp(5)); parent.addView(view);
        return view;
    }
    private static int selected(RadioGroup buttons) {
        for(int i=0;i<buttons.getChildCount();i++)
            if(((RadioButton)buttons.getChildAt(i)).isChecked()) return i;
        return 0;
    }
    private Properties read(File file) {
        Properties props=new Properties();
        if(!file.isFile()) return props;
        try(FileInputStream input=new FileInputStream(file)) { props.load(input); }
        catch(Exception ignored) {}
        return props;
    }
    private String engineStatus() {
        Properties stats=read(new File(base,"framegen.stats"));
        int mult=0;
        try { mult=Integer.parseInt(stats.getProperty("multiplier","0")); }
        catch(Exception ignored) {}
        if(mult>=2 && mult<=4) {
            return "Engine active: "+mult+"× · "+stats.getProperty("source_fps","0")+
                   " real FPS / "+stats.getProperty("presented_fps","0")+" displayed FPS";
        }
        File log=new File(base,"logs/android-game.log");
        if(log.isFile()) {
            // Logs can be large. Read only the tail, not the whole file on the
            // Android UI thread when opening this in-game dialog.
            try(java.io.RandomAccessFile input=new java.io.RandomAccessFile(log,"r")) {
                long length=input.length();
                int count=(int)Math.min(length,96*1024L);
                byte[] tail=new byte[count];
                input.seek(length-count);
                input.readFully(tail);
                String text=new String(tail,StandardCharsets.UTF_8);
                int at=text.lastIndexOf("LSFG: off (");
                if(at>=0) {
                    int end=text.indexOf('\n',at);
                    return text.substring(at,end>=0?end:text.length()).trim();
                }
            } catch(Exception ignored) {}
        }
        return "Not active yet: enable it and start the game with your own Lossless.dll.";
    }
    void show() {
        Properties state=read(new File(base,"framegen.state"));
        int requested=prefs.getInt("framegen_multiplier",0);
        try { requested=Integer.parseInt(state.getProperty("multiplier",String.valueOf(requested))); }
        catch(Exception ignored) {}
        String storedFlow=state.getProperty("flow",
                             prefs.getString("framegen_flow","0.75"));
        float flowStart=0.75f;
        try { flowStart=Float.parseFloat(storedFlow); } catch(Exception ignored) {}
        boolean fast="1".equals(state.getProperty("performance",
                                prefs.getBoolean("framegen_performance",true)?"1":"0"));
        boolean fp16="1".equals(state.getProperty("fp16",
                                prefs.getBoolean("framegen_fp16",true)?"1":"0"));

        LinearLayout box=new LinearLayout(activity); box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(22),dp(8),dp(22),dp(10));
        note(box,"Native Bloodframe · directly adapted from Bloodborne Android. "
           +"Generated frames are inserted between real game frames, using shaders in your own Lossless.dll.",0.85f);
        TextView hdr=note(box,"Frame generation",1f);
        hdr.setTypeface(Typeface.DEFAULT,Typeface.BOLD); hdr.setTextSize(16);
        RadioGroup mult=new RadioGroup(activity);
        int which=0;
        for(int i=0;i<VALUES.length;i++) if(VALUES[i].equals(String.valueOf(requested))) which=i;
        for(int i=0;i<NAMES.length;i++) {
            RadioButton b=new RadioButton(activity); b.setId(View.generateViewId());
            b.setText(NAMES[i]); b.setTextSize(15); mult.addView(b);
            if(i==which) mult.check(b.getId());
        }
        box.addView(mult);
        TextView flowLabel=note(box,"",0.9f);
        SeekBar flow=new SeekBar(activity); flow.setMax(15);
        flow.setProgress(Math.round((Math.max(0.25f,Math.min(1f,flowStart))-0.25f)/0.05f));
        flow.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar s,int progress,boolean user) {
                flowLabel.setText(String.format(Locale.ROOT,
                  "Motion flow: %.2f (lower = faster)",0.25f+progress*0.05f));
            }
            @Override public void onStartTrackingTouch(SeekBar s) {}
            @Override public void onStopTrackingTouch(SeekBar s) {}
        });
        flowLabel.setText(String.format(Locale.ROOT,"Motion flow: %.2f (lower = faster)",
                            0.25f+flow.getProgress()*0.05f));
        box.addView(flow);
        Switch performance=new Switch(activity);
        performance.setText("Performance model (recommended)");performance.setChecked(fast);
        performance.setPadding(0,dp(5),0,dp(5));box.addView(performance);
        Switch half=new Switch(activity);
        half.setText("FP16 shaders · Adreno 830 (recommended)");half.setChecked(fp16);
        half.setPadding(0,dp(5),0,dp(5));box.addView(half);
        note(box,"The Bloodborne fix uses the original FP16 / FP32 SPIR-V shaders from Lossless.dll. "
            +"Old DXBC translations may cause ghosting on Adreno 8xx.",0.7f);
        File dll=new File(base,"Lossless.dll");
        note(box,dll.isFile() && dll.length()>0 ? "Lossless.dll found" :
            "Lossless.dll missing: import it in Settings → General. The engine cannot start without it.",1f);
        note(box,engineStatus(),0.9f);
        final Runnable enabled=() -> {
            boolean on=selected(mult)>0; flow.setEnabled(on);
            performance.setEnabled(on);half.setEnabled(on);
        };
        mult.setOnCheckedChangeListener((g,id)->enabled.run());enabled.run();
        ScrollView scroll=new ScrollView(activity);scroll.addView(box);
        new AlertDialog.Builder(activity).setTitle("Bloodframe · Native frame generation")
          .setView(scroll).setNegativeButton("Cancel",null)
          .setPositiveButton("Apply live",(dialog,ignored)->{
            int value=Integer.parseInt(VALUES[selected(mult)]);
            String flowString=String.format(Locale.ROOT,"%.2f",0.25f+flow.getProgress()*0.05f);
            boolean okay=saveState(value,flowString,performance.isChecked(),half.isChecked());
            if(okay) {
                prefs.edit().putInt("framegen_multiplier",value)
                    .putInt("framegen_preferred_multiplier",value>=2 ? value : 
                              prefs.getInt("framegen_preferred_multiplier",2))
                    .putString("framegen_flow",flowString)
                    .putBoolean("framegen_performance",performance.isChecked())
                    .putBoolean("framegen_fp16",half.isChecked()).apply();
                if(applied!=null)applied.run();
            }
            Toast.makeText(activity,!okay?"Frame generation state could not be written":
                value>0 && (!dll.isFile()||dll.length()==0)?
                "Imported Lossless.dll required; engine remains off":
                value>0?"Bloodframe "+value+"× requested; verify FPS and status in this menu":
                "Bloodframe disabled",Toast.LENGTH_LONG).show();
          }).show();
    }
    private boolean saveState(int multiplier,String flow,boolean performance,boolean fp16) {
        File state=new File(base,"framegen.state"),tmp=new File(base,"framegen.state.tmp");
        if(!base.isDirectory()&&!base.mkdirs())return false;
        try(FileOutputStream stream=new FileOutputStream(tmp)) {
            String text="multiplier="+multiplier+"\nflow="+flow+
                        "\nperformance="+(performance?1:0)+"\nfp16="+(fp16?1:0)+"\n";
            stream.write(text.getBytes(StandardCharsets.US_ASCII));
            stream.getFD().sync();
        }catch(Exception exception){tmp.delete();return false;}
        return tmp.renameTo(state);
    }
}
