package cn.gaoming.tv;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.content.pm.ResolveInfo;
import android.net.Uri;
import android.widget.Toast;

import java.text.Normalizer;
import java.util.regex.Pattern;

import o0.a;

public final class Cctv13Fallback {
    private static final String QX_PACKAGE = "com.tv.qx";
    private static final String QX_MAIN = "com.tv.core.ui.MainActivity";
    private static final Uri CCTV_PAGE = Uri.parse("https://tv.cctv.com/live/cctv13/m/index.shtml");
    private static final Pattern CHANNEL = Pattern.compile(
            "(?i)(?:CCTV|央视|中央)[\\s-]*13(?:套)?(?:[\\s-]*新闻(?:频道)?)?");

    private Cctv13Fallback() {}

    public static void show(Activity activity, a channel) {
        if (channel == null || channel.b == null || activity.isFinishing() || activity.isDestroyed()
                || !CHANNEL.matcher(Normalizer.normalize(channel.b, Normalizer.Form.NFKC).trim()).matches()) {
            return;
        }
        Intent launcher = new Intent(Intent.ACTION_MAIN)
                .addCategory(Intent.CATEGORY_LAUNCHER).setPackage(QX_PACKAGE);
        for (ResolveInfo match : activity.getPackageManager().queryIntentActivities(launcher, 0)) {
            ActivityInfo info = match.activityInfo;
            if (info != null && info.exported && QX_PACKAGE.equals(info.packageName) && QX_MAIN.equals(info.name)) {
                launcher.setClassName(QX_PACKAGE, QX_MAIN);
                new AlertDialog.Builder(activity)
                        .setTitle("央视 13 线路播放失败")
                        .setMessage("可在千寻选择央视 13，或打开央视网直播页面。")
                        .setPositiveButton("打开千寻", (dialog, which) -> {
                            try {
                                activity.startActivity(launcher);
                            } catch (ActivityNotFoundException | SecurityException unavailable) {
                                showWebsiteOption(activity);
                            }
                        })
                        .setNeutralButton("打开央视网", (dialog, which) -> openWebsite(activity))
                        .setNegativeButton("返回", null).show();
                return;
            }
        }
        showWebsiteOption(activity);
    }

    private static void showWebsiteOption(Activity activity) {
        new AlertDialog.Builder(activity)
                .setTitle("央视 13 线路播放失败")
                .setMessage("当前设备无法打开千寻。可前往央视网观看央视 13。")
                .setPositiveButton("打开央视网", (dialog, which) -> openWebsite(activity))
                .setNegativeButton("返回", null).show();
    }

    private static void openWebsite(Activity activity) {
        try {
            activity.startActivity(new Intent(Intent.ACTION_VIEW, CCTV_PAGE));
        } catch (ActivityNotFoundException | SecurityException unavailable) {
            Toast.makeText(activity, "当前设备无法打开央视网，请检查浏览器", Toast.LENGTH_LONG).show();
        }
    }
}
