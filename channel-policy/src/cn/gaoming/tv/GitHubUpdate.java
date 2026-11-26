package cn.gaoming.tv;

import android.app.AlertDialog;
import android.app.PendingIntent;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.util.Log;
import android.widget.Toast;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.ref.WeakReference;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.regex.Pattern;
import javax.net.ssl.HttpsURLConnection;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

public final class GitHubUpdate {
    private static final String REPOSITORY = "chinayuli888-hash/tv";
    private static final String RELEASES = "https://github.com/" + REPOSITORY + "/releases";
    private static final String LATEST = "https://api.github.com/repos/" + REPOSITORY + "/releases/latest";
    private static final String TEST_CERT = "28164d64c98f91099936cdcfd5ab7ec9c94ad604fc191db5265a73cd5e992733";
    private static final String TAG = "GaomingTVUpdate";
    private static final int INSTALL_PERMISSION_REQUEST = 17416;
    private static final long MAX_APK_BYTES = 128L * 1024 * 1024;
    private static final Pattern VERSION = Pattern.compile("v?[0-9]{1,8}(\\.[0-9]{1,8}){2}");
    private static final AtomicBoolean BUSY = new AtomicBoolean();

    private static volatile WeakReference<MainActivity> foreground = new WeakReference<>(null);
    // Only the main thread sets or clears these two values.
    private static File awaitingPermission;
    private static Intent awaitingConfirmation;

    private GitHubUpdate() {}

    public static String settingsLabel(Context context) {
        return "软件更新    " + versionLabel(context);
    }

    private static String versionLabel(Context context) {
        try {
            PackageInfo info = installed(context, 0);
            return "v" + info.versionName + " (" + versionCode(info) + ")";
        } catch (PackageManager.NameNotFoundException error) {
            return "版本未知";
        }
    }

    public static void show(MainActivity activity) {
        foreground = new WeakReference<>(activity);
        boolean waiting = awaitingConfirmation != null;
        MainActivity.t(new AlertDialog.Builder(activity)
                .setTitle("软件更新")
                .setMessage("当前版本 " + versionLabel(activity) + "\n从 GitHub Releases 检查、下载并安装更新。")
                .setPositiveButton(waiting ? "继续安装" : "自动升级", (dialog, which) -> {
                    if (awaitingConfirmation != null) {
                        openConfirmation(activity, awaitingConfirmation);
                    } else {
                        check(activity);
                    }
                })
                .setNeutralButton("发布页面", (dialog, which) -> {
                    try {
                        activity.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(RELEASES)));
                    } catch (ActivityNotFoundException error) {
                        Toast.makeText(activity, "此设备没有可打开 GitHub 的浏览器", Toast.LENGTH_LONG).show();
                    }
                })
                .setNegativeButton("返回", null));
    }

    private static void check(MainActivity activity) {
        if (!BUSY.compareAndSet(false, true)) {
            Toast.makeText(activity, "更新正在处理中", Toast.LENGTH_SHORT).show();
            return;
        }
        Context context = activity.getApplicationContext();
        Toast.makeText(activity, "正在检查 GitHub 更新…", Toast.LENGTH_SHORT).show();
        new Thread(() -> prepare(context), "gaoming-release-check").start();
    }

    private static void prepare(Context context) {
        File file = null;
        try {
            PackageInfo current = installed(context, PackageManager.GET_SIGNATURES);
            JSONObject release = latestRelease();
            String tag = release.getString("tag_name");
            if (compareVersions(tag, current.versionName) <= 0) {
                finish(context, "当前版本 " + current.versionName + "，GitHub 最新 " + tag);
                return;
            }
            Asset asset = selectAsset(release, tag, isTestBuild(current));
            toast(context, "正在下载 " + tag + "…");
            file = download(context, asset);
            verifyApk(context, current, tag, file);
            File verified = file;
            runOnMain(() -> installOrRequestPermission(context, verified));
            file = null; // The installer or the permission flow now owns the file.
        } catch (UpdateException error) {
            finish(context, error.getMessage());
        } catch (PackageManager.NameNotFoundException | IOException | JSONException | RuntimeException error) {
            Log.w(TAG, "Update check failed: " + error.getClass().getSimpleName());
            finish(context, "无法完成更新，请检查 GitHub 网络连接后重试");
        } finally {
            delete(file);
        }
    }

    private static JSONObject latestRelease() throws IOException, JSONException {
        HttpsURLConnection connection = open(new URL(LATEST), false);
        try (InputStream input = connection.getInputStream(); ByteArrayOutputStream data = new ByteArrayOutputStream()) {
            copy(input, data, null, 2 * 1024 * 1024);
            return new JSONObject(new String(data.toByteArray(), StandardCharsets.UTF_8));
        } finally {
            connection.disconnect();
        }
    }

    static final class Asset {
        final URL url;
        final long size;
        final String sha256;

        Asset(URL url, long size, String sha256) {
            this.url = url;
            this.size = size;
            this.sha256 = sha256;
        }
    }

    static Asset selectAsset(JSONObject release, String tag, boolean testBuild) throws IOException, JSONException {
        if (release.optBoolean("draft") || release.optBoolean("prerelease")) {
            throw new UpdateException("GitHub 暂无正式发布的更新");
        }
        String version = stripV(tag);
        String expectedName = "gaoming-tv-" + version + (testBuild ? "-test.apk" : ".apk");
        JSONArray assets = release.getJSONArray("assets");
        for (int i = 0; i < assets.length(); i++) {
            JSONObject asset = assets.getJSONObject(i);
            if (!expectedName.equals(asset.optString("name")) || !"uploaded".equals(asset.optString("state"))) {
                continue;
            }
            String expectedUrl = RELEASES + "/download/" + tag + "/" + expectedName;
            long size = asset.optLong("size", -1);
            if (!expectedUrl.equals(asset.optString("browser_download_url")) || size <= 0 || size > MAX_APK_BYTES) {
                throw new UpdateException("发布附件地址或大小异常");
            }
            String digest = asset.isNull("digest") ? "" : asset.optString("digest");
            if (!digest.isEmpty() && !digest.matches("sha256:[0-9a-fA-F]{64}")) {
                throw new UpdateException("发布附件的 SHA-256 格式异常");
            }
            return new Asset(new URL(expectedUrl), size, digest.isEmpty() ? "" : digest.substring(7));
        }
        throw new UpdateException("发现 " + tag + "，GitHub 暂无此安装类型的已签名 APK");
    }

    static int compareVersions(String left, String right) throws IOException {
        if (left == null || right == null || !VERSION.matcher(left).matches() || !VERSION.matcher(right).matches()) {
            throw new UpdateException("无法识别发布版本号");
        }
        String[] a = stripV(left).split("\\.");
        String[] b = stripV(right).split("\\.");
        for (int i = 0; i < a.length; i++) {
            int order = Integer.compare(Integer.parseInt(a[i]), Integer.parseInt(b[i]));
            if (order != 0) {
                return order;
            }
        }
        return 0;
    }

    private static String stripV(String version) {
        return version.startsWith("v") ? version.substring(1) : version;
    }

    private static HttpsURLConnection open(URL url, boolean downloading) throws IOException {
        for (int redirects = 0; redirects <= 5; redirects++) {
            String host = url.getHost().toLowerCase(Locale.ROOT);
            boolean hostAllowed = downloading
                    ? host.equals("github.com") || host.endsWith(".githubusercontent.com")
                    : host.equals("api.github.com");
            if (!hostAllowed || !"https".equals(url.getProtocol()) || url.getUserInfo() != null
                    || (url.getPort() != -1 && url.getPort() != 443)) {
                throw new UpdateException("GitHub 返回了不受信的下载地址");
            }
            HttpsURLConnection connection = (HttpsURLConnection) url.openConnection();
            LegacyTls.configure(connection);
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(12000);
            connection.setReadTimeout(15000);
            connection.setRequestProperty("User-Agent", "GaomingTV-Updater");
            connection.setRequestProperty("Accept", downloading ? "application/octet-stream" : "application/vnd.github+json");
            int status;
            try {
                status = connection.getResponseCode();
            } catch (IOException error) {
                connection.disconnect();
                throw error;
            }
            if (status == 200) {
                return connection;
            }
            String location = connection.getHeaderField("Location");
            connection.disconnect();
            if (status >= 300 && status < 400 && location != null && downloading) {
                url = new URL(url, location);
                continue;
            }
            throw new UpdateException("GitHub 请求失败（HTTP " + status + "）");
        }
        throw new UpdateException("GitHub 附件跳转次数过多");
    }

    private static File download(Context context, Asset asset) throws IOException {
        HttpsURLConnection connection = open(asset.url, true);
        File file = null;
        boolean complete = false;
        try {
            file = File.createTempFile("gaoming-release-", ".apk", context.getCacheDir());
            MessageDigest hash = sha256();
            try (InputStream input = connection.getInputStream(); OutputStream output = new FileOutputStream(file)) {
                if (copy(input, output, hash, asset.size) != asset.size) {
                    throw new UpdateException("APK 下载不完整");
                }
            }
            if (!asset.sha256.isEmpty() && !asset.sha256.equalsIgnoreCase(hex(hash.digest()))) {
                throw new UpdateException("APK 的 SHA-256 校验失败");
            }
            complete = true;
            return file;
        } finally {
            connection.disconnect();
            if (!complete) {
                delete(file);
            }
        }
    }

    private static long copy(InputStream input, OutputStream output, MessageDigest hash, long limit) throws IOException {
        byte[] buffer = new byte[16384];
        long total = 0;
        int count;
        while ((count = input.read(buffer)) != -1) {
            total += count;
            if (total > limit) {
                throw new UpdateException("GitHub 响应超过预期大小");
            }
            output.write(buffer, 0, count);
            if (hash != null) {
                hash.update(buffer, 0, count);
            }
        }
        return total;
    }

    private static PackageInfo installed(Context context, int flags) throws PackageManager.NameNotFoundException {
        return context.getPackageManager().getPackageInfo(context.getPackageName(), flags);
    }

    private static boolean isTestBuild(PackageInfo info) {
        return info.signatures != null && info.signatures.length == 1
                && TEST_CERT.equals(hex(sha256().digest(info.signatures[0].toByteArray())));
    }

    private static int versionCode(PackageInfo info) {
        return info.versionCode;
    }

    private static void verifyApk(Context context, PackageInfo current, String tag, File file) throws IOException {
        PackageInfo candidate = context.getPackageManager().getPackageArchiveInfo(file.getAbsolutePath(),
                PackageManager.GET_SIGNATURES);
        if (candidate == null || !current.packageName.equals(candidate.packageName)
                || !stripV(tag).equals(candidate.versionName) || versionCode(candidate) <= versionCode(current)) {
            throw new UpdateException("APK 包名或版本与更新信息不符");
        }
        Signature[] expected = current.signatures;
        Signature[] actual = candidate.signatures;
        if (expected == null || expected.length == 0 || actual == null
                || !new HashSet<>(Arrays.asList(expected)).equals(new HashSet<>(Arrays.asList(actual)))) {
            throw new UpdateException("APK 签名与当前版本不匹配");
        }
    }

    private static void installOrRequestPermission(Context context, File apk) {
        if (Build.VERSION.SDK_INT >= 26 && !context.getPackageManager().canRequestPackageInstalls()) {
            MainActivity activity = foreground.get();
            if (activity != null && !activity.isFinishing() && !activity.isDestroyed()) {
                try {
                    awaitingPermission = apk;
                    Toast.makeText(activity, "允许高明 TV 安装应用后将继续升级", Toast.LENGTH_LONG).show();
                    activity.startActivityForResult(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                            Uri.parse("package:" + activity.getPackageName())), INSTALL_PERMISSION_REQUEST);
                    return;
                } catch (ActivityNotFoundException | SecurityException error) {
                    awaitingPermission = null;
                }
            }
            delete(apk);
            finish(context, "系统需要允许高明 TV 安装应用，请授权后重试");
            return;
        }
        submit(context, apk);
    }

    public static void onActivityResult(MainActivity activity, int requestCode) {
        if (requestCode != INSTALL_PERMISSION_REQUEST || awaitingPermission == null) {
            return;
        }
        foreground = new WeakReference<>(activity);
        File apk = awaitingPermission;
        awaitingPermission = null;
        if (Build.VERSION.SDK_INT >= 26 && activity.getPackageManager().canRequestPackageInstalls()) {
            submit(activity.getApplicationContext(), apk);
        } else {
            delete(apk);
            finish(activity, "系统安装权限未开启");
        }
    }

    private static void submit(Context context, File apk) {
        new Thread(() -> {
            try {
                if (Build.VERSION.SDK_INT >= 21) {
                    SessionInstall.commit(context, apk);
                    toast(context, "下载完成，正在交给系统安装");
                } else {
                    File dir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
                    if (dir == null) {
                        throw new UpdateException("外部存储不可用，无法打开系统安装器");
                    }
                    File installerFile = new File(dir, "gaoming-update.apk");
                    try (InputStream input = new FileInputStream(apk); OutputStream output = new FileOutputStream(installerFile)) {
                        copy(input, output, null, apk.length());
                    }
                    runOnMain(() -> {
                        openConfirmation(context, new Intent(Intent.ACTION_VIEW)
                                .setDataAndType(Uri.fromFile(installerFile), "application/vnd.android.package-archive"));
                        BUSY.set(false);
                    });
                }
            } catch (UpdateException error) {
                finish(context, error.getMessage());
            } catch (IOException | RuntimeException error) {
                Log.w(TAG, "Installer submission failed: " + error.getClass().getSimpleName());
                finish(context, "系统未能开始安装更新");
            } finally {
                delete(apk);
            }
        }, "gaoming-package-install").start();
    }

    private static final class SessionInstall {
        static void commit(Context context, File file) throws IOException {
            PackageInstaller installer = context.getPackageManager().getPackageInstaller();
            PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
            params.setAppPackageName(context.getPackageName());
            params.setSize(file.length());
            if (Build.VERSION.SDK_INT >= 31) {
                params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED);
            }
            int sessionId = installer.createSession(params);
            boolean committed = false;
            try (PackageInstaller.Session session = installer.openSession(sessionId)) {
                try (InputStream input = new FileInputStream(file);
                     OutputStream output = session.openWrite("base.apk", 0, file.length())) {
                    copy(input, output, null, file.length());
                    session.fsync(output);
                }
                Intent result = new Intent(context, UpdateInstallReceiver.class).setAction(UpdateInstallReceiver.ACTION);
                int flags = PendingIntent.FLAG_UPDATE_CURRENT;
                if (Build.VERSION.SDK_INT >= 31) {
                    flags |= PendingIntent.FLAG_MUTABLE;
                }
                PendingIntent callback = PendingIntent.getBroadcast(context, sessionId, result, flags);
                session.commit(callback.getIntentSender());
                committed = true;
            } finally {
                if (!committed) {
                    installer.abandonSession(sessionId);
                }
            }
        }
    }

    static void confirmInstall(Context context, Intent confirmation) {
        if (confirmation == null) {
            finish(context, "系统没有返回安装确认界面");
            return;
        }
        awaitingConfirmation = confirmation;
        openConfirmation(context, confirmation);
    }

    private static void openConfirmation(Context context, Intent confirmation) {
        MainActivity activity = foreground.get();
        try {
            if (activity != null && !activity.isFinishing() && !activity.isDestroyed()) {
                activity.startActivity(confirmation);
            } else {
                context.startActivity(new Intent(confirmation).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            }
        } catch (ActivityNotFoundException | SecurityException error) {
            Toast.makeText(context, "请从软件更新菜单继续系统安装", Toast.LENGTH_LONG).show();
        }
    }

    static void finish(Context context, String message) {
        runOnMain(() -> {
            awaitingConfirmation = null;
            BUSY.set(false);
            Toast.makeText(context, message, Toast.LENGTH_LONG).show();
        });
    }

    private static void toast(Context context, String message) {
        runOnMain(() -> Toast.makeText(context, message, Toast.LENGTH_LONG).show());
    }

    private static void runOnMain(Runnable action) {
        new Handler(Looper.getMainLooper()).post(action);
    }

    private static void delete(File file) {
        if (file != null && !file.delete() && file.exists()) {
            Log.w(TAG, "Unable to remove the temporary update file");
        }
    }

    private static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }

    private static String hex(byte[] digest) {
        StringBuilder result = new StringBuilder(digest.length * 2);
        for (byte value : digest) {
            result.append(Character.forDigit((value & 0xf0) >>> 4, 16));
            result.append(Character.forDigit(value & 0x0f, 16));
        }
        return result.toString();
    }

    private static final class UpdateException extends IOException {
        UpdateException(String message) {
            super(message);
        }
    }
}
