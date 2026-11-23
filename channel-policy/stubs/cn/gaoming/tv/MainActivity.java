package cn.gaoming.tv;

import android.app.Activity;
import android.app.AlertDialog;

// Compile-time signatures from the pinned APK and its catalog hooks. Never packed into the APK.
public abstract class MainActivity extends Activity {
    public static void t(AlertDialog.Builder builder) {
        throw new AssertionError();
    }

    public abstract void reloadChannelCatalog();
}
