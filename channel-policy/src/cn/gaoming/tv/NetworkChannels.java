package cn.gaoming.tv;

import android.content.Context;
import android.util.Log;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import o0.a;
import o0.c;
import o0.d;

public final class NetworkChannels {
    private static final String PLAYLIST = "public-network.m3u";
    private static volatile Set<String> publicUrls = Collections.emptySet();
    private static volatile Set<String> originalUrls = Collections.emptySet();

    private NetworkChannels() {}

    public static List<a> addToBuiltIn(Context context, List<a> builtIn) {
        List<a> publicChannels;
        try (InputStream input = context.getAssets().open(PLAYLIST)) {
            ByteArrayOutputStream playlist = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096];
            int count;
            while ((count = input.read(buffer)) != -1) {
                playlist.write(buffer, 0, count);
            }
            publicChannels = d.l(new String(playlist.toByteArray(), StandardCharsets.UTF_8), "直播");
        } catch (IOException error) {
            Log.w("GaomingTV", "Cannot load the public network playlist", error);
            return builtIn;
        }
        if (publicChannels.isEmpty()) {
            return builtIn;
        }

        // The existing merge deduplicates routes and preserves first-list priority.
        Map<String, a> merged = new LinkedHashMap<>();
        for (a channel : d.c(publicChannels, builtIn)) {
            merged.put(channel.a, channel);
        }
        List<a> ordered = new ArrayList<>(merged.size());
        for (a channel : builtIn) {
            a combined = merged.remove(channel.a);
            ordered.add(combined != null ? combined : channel);
        }
        ordered.addAll(merged.values());

        originalUrls = routeUrls(builtIn);
        publicUrls = routeUrls(publicChannels);
        return ordered;
    }

    private static Set<String> routeUrls(List<a> catalog) {
        Set<String> urls = new HashSet<>();
        for (a channel : catalog) {
            for (c route : channel.d) {
                urls.add(route.a);
            }
        }
        return Collections.unmodifiableSet(urls);
    }

    public static boolean hasPublicRoute(a channel) {
        Set<String> urls = publicUrls;
        for (c route : channel.d) {
            if (urls.contains(route.a)) {
                return true;
            }
        }
        return false;
    }

    public static a forPublicPlayback(a channel) {
        if (!hasPublicRoute(channel)) {
            return channel;
        }
        Set<String> urls = publicUrls;
        Set<String> original = originalUrls;
        ArrayList<c> publicRoutes = new ArrayList<>(channel.d.size());
        for (c route : channel.d) {
            if (urls.contains(route.a) || !original.contains(route.a)) {
                publicRoutes.add(route);
            }
        }
        if (publicRoutes.isEmpty() || publicRoutes.size() == channel.d.size()) {
            return channel;
        }
        return new a(channel.b, channel.c, publicRoutes);
    }
}
