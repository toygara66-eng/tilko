package com.tilko.app;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;
import com.tilko.app.integrity.IntegrityBridge;
import com.tilko.app.integrity.SignatureGuard;

/**
 * Capacitor kabuğu. TilkoIntegrity JS köprüsü onStart'ta eklenir.
 * Korsan imzada tuzak sayfası yüklenir.
 */
public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
    }

    @Override
    public void onStart() {
        super.onStart();
        if (getBridge() == null || getBridge().getWebView() == null) {
            return;
        }
        getBridge().getWebView().addJavascriptInterface(new IntegrityBridge(this), "TilkoIntegrity");
        if (!SignatureGuard.isOfficial(this)) {
            getBridge().getWebView().loadUrl("file:///android_asset/trap/index.html");
        }
    }
}
