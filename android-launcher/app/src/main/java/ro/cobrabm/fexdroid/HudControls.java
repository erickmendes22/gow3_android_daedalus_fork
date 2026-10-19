package ro.cobrabm.fexdroid;

import android.app.Activity;
import android.app.AlertDialog;
import android.view.View;
import android.widget.*;
import java.io.File;
import java.util.LinkedHashMap;
import java.util.Map;

/** Same performance HUD controls in Graphics settings and the in-game Android drawer. */
final class HudControls {
    private final Switch enabled;
    private final RadioGroup alignment;
    private final RadioGroup vertical;
    private final Activity activity;
    private final File ini;

    HudControls(Activity activity, File ini, LinearLayout parent, HudConfig cfg) {
        this.activity = activity;
        this.ini = ini;
        float density = activity.getResources().getDisplayMetrics().density;
        TextView heading = new TextView(activity);
        heading.setText("Performance HUD — FPS / GPU / CPU");
        heading.setTextSize(16f);
        heading.setPadding(0, (int)(12 * density), 0, (int)(6 * density));
        parent.addView(heading);
        enabled = new Switch(activity);
        enabled.setText("Show performance HUD");
        enabled.setChecked(cfg.enabled);
        parent.addView(enabled);

        TextView alignText = new TextView(activity);
        alignText.setText("Horizontal position");
        parent.addView(alignText);
        alignment = new RadioGroup(activity);
        alignment.setOrientation(RadioGroup.HORIZONTAL);
        final int[] anchors = {0, 4, 1};
        final String[] choices = {"Left", "Center", "Right"};
        for (int i = 0; i < choices.length; i++) {
            RadioButton button = new RadioButton(activity);
            button.setId(View.generateViewId());
            button.setTag(anchors[i]);
            button.setText(choices[i]);
            alignment.addView(button);
            if (cfg.anchor == anchors[i]) alignment.check(button.getId());
        }
        parent.addView(alignment);

        TextView positionY = new TextView(activity);
        positionY.setText("Vertical position");
        parent.addView(positionY);
        vertical = new RadioGroup(activity);
        vertical.setOrientation(RadioGroup.HORIZONTAL);
        String[] verticalLabels = {"Top", "Center", "Bottom"};
        for (int i=0; i<verticalLabels.length; i++) {
            RadioButton button = new RadioButton(activity);
            button.setId(View.generateViewId());
            button.setTag(i);
            button.setText(verticalLabels[i]);
            vertical.addView(button);
            if (cfg.vertical == i) vertical.check(button.getId());
        }
        parent.addView(vertical);
        enabled.setOnCheckedChangeListener((button, value) -> {
            for (int i=0; i<alignment.getChildCount(); i++)
                alignment.getChildAt(i).setEnabled(value);
            for (int i=0; i<vertical.getChildCount(); i++)
                vertical.getChildAt(i).setEnabled(value);
        });
        for (int i=0; i<alignment.getChildCount(); i++)
            alignment.getChildAt(i).setEnabled(cfg.enabled);
        for (int i=0; i<vertical.getChildCount(); i++)
            vertical.getChildAt(i).setEnabled(cfg.enabled);
    }

    Map<String,String> values() {
        int anchor = 1;
        for (int i = 0; i < alignment.getChildCount(); i++) {
            RadioButton item = (RadioButton)alignment.getChildAt(i);
            if (item.isChecked()) anchor = (Integer)item.getTag();
        }
        int anchorY = 0;
        for (int i=0; i<vertical.getChildCount(); i++) {
            RadioButton item = (RadioButton)vertical.getChildAt(i);
            if (item.isChecked()) anchorY = (Integer)item.getTag();
        }
        Map<String,String> result = new LinkedHashMap<>();
        result.put(HudConfig.ENABLED, enabled.isChecked() ? "1" : "0");
        result.put(HudConfig.ANCHOR, String.valueOf(anchor));
        result.put(HudConfig.VERTICAL, String.valueOf(anchorY));
        // Retire R4 sliders: old offsets must not override the selected anchors.
        result.put(HudConfig.DX, "0");
        result.put(HudConfig.DY, "0");
        return result;
    }

    static void show(Activity activity, File ini, Runnable updated) {
        LinearLayout content = new LinearLayout(activity);
        content.setOrientation(LinearLayout.VERTICAL);
        int pad = Math.round(activity.getResources().getDisplayMetrics().density * 16);
        content.setPadding(pad, pad, pad, pad);
        HudControls controls = new HudControls(activity, ini, content, HudConfig.load(ini));
        ScrollView scroll = new ScrollView(activity);
        scroll.addView(content);
        new AlertDialog.Builder(activity)
            .setTitle("Performance HUD")
            .setView(scroll)
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Apply", (dialog, which) -> {
                if (HudConfig.update(ini, controls.values())) {
                    if (updated != null) updated.run();
                } else {
                    new AlertDialog.Builder(activity).setMessage("Cannot save performance HUD settings.")
                        .setPositiveButton("OK", null).show();
                }
            }).show();
    }
}
