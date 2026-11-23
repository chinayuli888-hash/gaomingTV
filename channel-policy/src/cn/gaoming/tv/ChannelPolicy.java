package cn.gaoming.tv;

import android.app.AlertDialog;
import android.content.Context;
import android.content.SharedPreferences;
import android.text.InputType;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;
import o0.a;

public final class ChannelPolicy {
    private static final String PREFERENCES = "channel_policy";
    private static final String HIDDEN_NAMES = "hidden_names";
    private static final String CLASSIFY_BY_TYPE = "classify_by_type";
    private static final String DEFAULT_HIDDEN_NAMES = "每日推荐\n好物严选\n乐享生活";
    private static final Set<String> DEFAULT_GROUPS = new HashSet<>(Arrays.asList(
            "中央", "直辖市", "省级", "市", "县", "其他", "我的导入"));
    private static final Pattern SPORTS_NUMBER = Pattern.compile("^cctv[ -]?(?:5|16)(?![0-9a-z])");
    private static final Pattern CHILDREN_NUMBER = Pattern.compile("^cctv[ -]?14(?![0-9a-z])");
    private static final Pattern FILM_NUMBER = Pattern.compile("^cctv[ -]?[68](?![0-9a-z])");

    private ChannelPolicy() {}

    private static SharedPreferences preferences(Context context) {
        return context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE);
    }

    static Set<String> hiddenNames(String lines) {
        Set<String> names = new HashSet<>();
        for (String line : lines.split("\\r?\\n")) {
            String name = normalize(line);
            if (!name.isEmpty()) {
                names.add(name);
            }
        }
        return names;
    }

    public static List<a> visible(Context context, List<a> catalog) {
        Set<String> hidden = hiddenNames(preferences(context)
                .getString(HIDDEN_NAMES, DEFAULT_HIDDEN_NAMES));
        if (hidden.isEmpty()) {
            return catalog;
        }
        List<a> visible = new ArrayList<>(catalog.size());
        for (a channel : catalog) {
            if (!hidden.contains(normalize(channel.b))) {
                visible.add(channel);
            }
        }
        return visible;
    }

    public static String label(Context context, a channel) {
        return preferences(context).getBoolean(CLASSIFY_BY_TYPE, false)
                ? classify(channel.b, channel.c) : channel.c;
    }

    static String classify(String name, String originalGroup) {
        if (!DEFAULT_GROUPS.contains(originalGroup)) {
            return originalGroup;
        }
        String channel = normalize(name);
        if (SPORTS_NUMBER.matcher(channel).find() || channel.contains("体育")
                || channel.contains("赛事") || channel.contains("足球")
                || channel.contains("台球") || channel.contains("网球")) {
            return "体育";
        }
        if (channel.contains("少儿") || channel.contains("卡通") || channel.contains("动漫")
                || CHILDREN_NUMBER.matcher(channel).find()) {
            return "少儿";
        }
        if (channel.contains("电影") || channel.contains("影视") || channel.contains("剧场")
                || channel.contains("电视剧") || FILM_NUMBER.matcher(channel).find()) {
            return "影视";
        }
        if (originalGroup.equals("中央") || channel.startsWith("cctv") || channel.startsWith("cgtn")) {
            return "央视";
        }
        if (channel.contains("卫视")) {
            return "卫视";
        }
        return originalGroup;
    }

    private static String normalize(String value) {
        return Normalizer.normalize(value, Normalizer.Form.NFKC).trim().toLowerCase(Locale.ROOT);
    }

    public static String[] settingsItems(String[] items) {
        String[] entries = Arrays.copyOf(items, items.length + 1);
        entries[items.length] = "频道整理";
        return entries;
    }

    public static void showSettings(MainActivity activity) {
        SharedPreferences prefs = preferences(activity);
        LinearLayout content = new LinearLayout(activity);
        content.setOrientation(LinearLayout.VERTICAL);
        int padding = Math.round(20 * activity.getResources().getDisplayMetrics().density);
        content.setPadding(padding, 0, padding, 0);

        CheckBox byType = new CheckBox(activity);
        byType.setText("按节目类型分类");
        byType.setChecked(prefs.getBoolean(CLASSIFY_BY_TYPE, false));
        content.addView(byType);

        EditText names = new EditText(activity);
        names.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        names.setMinLines(3);
        names.setMaxLines(5);
        names.setHint("隐藏频道，每行输入一个完整名称");
        names.setContentDescription("隐藏频道名单，每行一个频道名称");
        names.setText(prefs.getString(HIDDEN_NAMES, DEFAULT_HIDDEN_NAMES));
        content.addView(names);
        byType.requestFocus();

        MainActivity.t(new AlertDialog.Builder(activity)
                .setTitle("频道整理")
                .setView(content)
                .setNegativeButton("取消", null)
                .setPositiveButton("保存", (dialog, button) -> {
                    prefs.edit().putBoolean(CLASSIFY_BY_TYPE, byType.isChecked())
                            .putString(HIDDEN_NAMES, names.getText().toString()).apply();
                    activity.reloadChannelCatalog();
                }));
    }
}
