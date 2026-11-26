package cn.gaoming.tv;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.ActivityInfo;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.util.DisplayMetrics;

public final class DeviceLayout {
    // The existing layout uses a 960 × 540 canvas and a 422-unit channel guide.
    private static final float CANVAS_WIDTH = 960f;
    private static final float CANVAS_HEIGHT = 540f;
    private static final float GUIDE_WIDTH = 422f;
    private static final float DISMISS_STRIP_DP = 32f;
    private static final int ORIGINAL_ASPECT = 3;
    private static final int FILL_SCREEN = 4;

    private DeviceLayout() {}

    public static float configure(Activity activity) {
        boolean television = isTelevision(activity);
        int orientation = television ? ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
                : ActivityInfo.SCREEN_ORIENTATION_FULL_USER;
        if (activity.getRequestedOrientation() != orientation) {
            activity.setRequestedOrientation(orientation);
        }

        DisplayMetrics metrics = activity.getResources().getDisplayMetrics();
        if (television) {
            metrics = new DisplayMetrics();
            activity.getWindowManager().getDefaultDisplay().getRealMetrics(metrics);
        }
        return calculateScale(metrics.widthPixels, metrics.heightPixels, metrics.density, television);
    }

    public static float scale(Activity activity, int width, int height) {
        return calculateScale(width, height, activity.getResources().getDisplayMetrics().density,
                isTelevision(activity));
    }

    public static int aspectMode(Activity activity, SharedPreferences preferences) {
        int legacyMode = preferences.getInt("aspect", 0);
        if (legacyMode == 0) {
            boolean portraitDefault = !preferences.contains("aspect")
                    && activity.getResources().getConfiguration().orientation == Configuration.ORIENTATION_PORTRAIT
                    && !isTelevision(activity);
            legacyMode = portraitDefault ? ORIGINAL_ASPECT : FILL_SCREEN;
        }
        int mode = preferences.getInt("display_mode", legacyMode);
        return mode >= 0 && mode <= FILL_SCREEN ? mode : FILL_SCREEN;
    }

    static float calculateScale(int width, int height, float density, boolean television) {
        float canvasScale = Math.min(width / CANVAS_WIDTH, height / CANVAS_HEIGHT);
        if (television || width >= height) {
            return canvasScale;
        }
        // Keep a strip of the player tappable to dismiss the guide on touch screens.
        float guideScale = Math.min((width - DISMISS_STRIP_DP * density) / GUIDE_WIDTH,
                height / CANVAS_HEIGHT);
        return Math.max(canvasScale, Math.min(density, guideScale));
    }

    private static boolean isTelevision(Context context) {
        int mode = context.getResources().getConfiguration().uiMode & Configuration.UI_MODE_TYPE_MASK;
        if (mode == Configuration.UI_MODE_TYPE_TELEVISION) {
            return true;
        }
        PackageManager packages = context.getPackageManager();
        return packages.hasSystemFeature("android.software.leanback")
                || packages.hasSystemFeature("android.hardware.type.television");
    }
}
