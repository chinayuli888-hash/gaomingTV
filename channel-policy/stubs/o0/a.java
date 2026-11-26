package o0;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

// Compile-time channel model signatures. Never packed into the APK.
public final class a {
    public final String a;
    public final String b;
    public final String c;
    public final List<c> d;

    public a(String name, String group, ArrayList<c> routes) {
        a = group.length() + ":" + group + name;
        b = name;
        c = group;
        d = Collections.unmodifiableList(new ArrayList<>(routes));
    }
}
