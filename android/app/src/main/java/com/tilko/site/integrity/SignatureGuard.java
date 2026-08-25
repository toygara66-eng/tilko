package com.tilko.site.integrity;

import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.content.pm.SigningInfo;
import android.os.Build;

import com.tilko.site.BuildConfig;

import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** Play imza SHA-256 doğrulaması. Sınıf adı R8 ile karışır. */
public final class SignatureGuard {
    private SignatureGuard() {}

    public static boolean debuggable(Context context) {
        return (context.getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0;
    }

    public static boolean isOfficial(Context context) {
        if (debuggable(context)) {
            return true;
        }
        String allow = BuildConfig.TILKO_PLAY_CERT_SHA256;
        if (allow == null || allow.trim().isEmpty()) {
            return true;
        }
        List<String> found = fingerprints(context);
        for (String allowed : allow.split("[,;]+")) {
            String needle = normalize(allowed);
            if (needle.isEmpty()) {
                continue;
            }
            for (String have : found) {
                if (needle.equals(have)) {
                    return true;
                }
            }
        }
        return false;
    }

    public static List<String> fingerprints(Context context) {
        List<String> out = new ArrayList<>();
        try {
            Signature[] sigs = signatures(context);
            MessageDigest sha = MessageDigest.getInstance("SHA-256");
            for (Signature sig : sigs) {
                byte[] digest = sha.digest(sig.toByteArray());
                sha.reset();
                out.add(toHex(digest));
            }
        } catch (Exception ignored) {
            /* boş liste → isOfficial false (allowlist doluysa) */
        }
        return out;
    }

    @SuppressWarnings("deprecation")
    private static Signature[] signatures(Context context) throws PackageManager.NameNotFoundException {
        PackageManager pm = context.getPackageManager();
        String pkg = context.getPackageName();
        if (Build.VERSION.SDK_INT >= 28) {
            PackageInfo info = pm.getPackageInfo(pkg, PackageManager.GET_SIGNING_CERTIFICATES);
            SigningInfo signing = info.signingInfo;
            if (signing == null) {
                return new Signature[0];
            }
            if (signing.hasMultipleSigners()) {
                return signing.getApkContentsSigners();
            }
            return signing.getSigningCertificateHistory();
        }
        PackageInfo info = pm.getPackageInfo(pkg, PackageManager.GET_SIGNATURES);
        Signature[] raw = info.signatures;
        return raw == null ? new Signature[0] : raw;
    }

    public static String normalize(String raw) {
        if (raw == null) {
            return "";
        }
        return raw.replace(":", "").replace(" ", "").trim().toUpperCase(Locale.US);
    }

    private static String toHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            sb.append(String.format(Locale.US, "%02X", b));
        }
        return sb.toString();
    }
}
