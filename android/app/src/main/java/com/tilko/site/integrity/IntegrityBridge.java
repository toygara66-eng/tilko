package com.tilko.site.integrity;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.webkit.JavascriptInterface;

import com.tilko.site.BuildConfig;

import java.lang.ref.WeakReference;
import java.util.List;

/**
 * WebView köprüsü. Sınıf R8 ile obfuscate olur; @JavascriptInterface
 * metot adları JS tarafı için korunur.
 */
public final class IntegrityBridge {
    private final WeakReference<Activity> activityRef;
    private final boolean official;
    private final String fingerprintsJson;

    public IntegrityBridge(Activity activity) {
        this.activityRef = new WeakReference<>(activity);
        this.official = SignatureGuard.isOfficial(activity);
        List<String> prints = SignatureGuard.fingerprints(activity);
        StringBuilder json = new StringBuilder("[");
        for (int i = 0; i < prints.size(); i++) {
            if (i > 0) {
                json.append(',');
            }
            json.append('"').append(prints.get(i)).append('"');
        }
        json.append(']');
        this.fingerprintsJson = json.toString();
    }

    @JavascriptInterface
    public boolean isOfficial() {
        return official;
    }

    @JavascriptInterface
    public String fingerprints() {
        return fingerprintsJson;
    }

    @JavascriptInterface
    public String packageName() {
        return BuildConfig.TILKO_PLAY_PACKAGE;
    }

    @JavascriptInterface
    public void openPlayStore() {
        Activity activity = activityRef.get();
        if (activity == null) {
            return;
        }
        String pkg = BuildConfig.TILKO_PLAY_PACKAGE;
        Intent market = new Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=" + pkg));
        market.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            activity.startActivity(market);
        } catch (Exception ignored) {
            Intent web = new Intent(
                    Intent.ACTION_VIEW,
                    Uri.parse("https://play.google.com/store/apps/details?id=" + pkg)
            );
            web.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            activity.startActivity(web);
        }
    }
}
