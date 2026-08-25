package com.tilko.site;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;
import com.tilko.site.billing.BillingBridge;
import com.tilko.site.integrity.IntegrityBridge;
import com.tilko.site.integrity.SignatureGuard;

/**
 * Capacitor kabuğu. TilkoIntegrity + TilkoPlayBillingNative JS köprüleri.
 */
public class MainActivity extends BridgeActivity {
    private boolean bridgesAttached = false;
    private BillingBridge billingBridge;

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
        if (!bridgesAttached) {
            getBridge().getWebView().addJavascriptInterface(new IntegrityBridge(this), "TilkoIntegrity");
            billingBridge = new BillingBridge(this, getBridge().getWebView());
            getBridge().getWebView().addJavascriptInterface(billingBridge, "TilkoPlayBillingNative");
            bridgesAttached = true;
        }
        if (!SignatureGuard.isOfficial(this)) {
            getBridge().getWebView().loadUrl("file:///android_asset/trap/index.html");
        }
    }
}
