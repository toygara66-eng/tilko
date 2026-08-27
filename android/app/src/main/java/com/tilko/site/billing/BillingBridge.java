package com.tilko.site.billing;

import android.app.Activity;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import com.android.billingclient.api.AcknowledgePurchaseParams;
import com.android.billingclient.api.BillingClient;
import com.android.billingclient.api.BillingClientStateListener;
import com.android.billingclient.api.BillingFlowParams;
import com.android.billingclient.api.BillingResult;
import com.android.billingclient.api.PendingPurchasesParams;
import com.android.billingclient.api.ProductDetails;
import com.android.billingclient.api.Purchase;
import com.android.billingclient.api.PurchasesUpdatedListener;
import com.android.billingclient.api.QueryPurchasesParams;
import com.android.billingclient.api.QueryProductDetailsParams;

import org.json.JSONObject;

import java.lang.ref.WeakReference;
import java.util.Collections;
import java.util.List;

/**
 * WebView köprüsü: window.TilkoPlayBillingNative.launch(productId)
 * Sonuç: window.__tilkoBillingDone({ purchaseToken, productId, orderId }) veya { error }
 */
public final class BillingBridge implements PurchasesUpdatedListener {
    private final WeakReference<Activity> activityRef;
    private final WeakReference<WebView> webViewRef;
    private BillingClient client;
    private String pendingProductId = "";

    public BillingBridge(Activity activity, WebView webView) {
        this.activityRef = new WeakReference<>(activity);
        this.webViewRef = new WeakReference<>(webView);
        this.client = BillingClient.newBuilder(activity)
                .setListener(this)
                .enablePendingPurchases(
                        PendingPurchasesParams.newBuilder()
                                .enableOneTimeProducts()
                                .build())
                .enableAutoServiceReconnection()
                .build();
        this.client.startConnection(new BillingClientStateListener() {
            @Override
            public void onBillingSetupFinished(@NonNull BillingResult billingResult) {
                // ready when launch() is called
            }

            @Override
            public void onBillingServiceDisconnected() {
                // next launch reconnects (auto reconnect also enabled)
            }
        });
    }

    @JavascriptInterface
    public void launch(String productId) {
        Activity activity = activityRef.get();
        if (activity == null) {
            deliverError("Aktivite yok");
            return;
        }
        String sku = productId == null ? "" : productId.trim();
        if (sku.isEmpty()) {
            deliverError("Ürün kimliği boş");
            return;
        }
        pendingProductId = sku;
        activity.runOnUiThread(() -> ensureConnectedThenBuy(sku));
    }

    /** Daha önce alınmış aboneliği tekrar sunucuya göndermek için. */
    @JavascriptInterface
    public void restore() {
        Activity activity = activityRef.get();
        if (activity == null) {
            deliverError("Aktivite yok");
            return;
        }
        activity.runOnUiThread(this::ensureConnectedThenRestore);
    }

    private void ensureConnectedThenRestore() {
        if (client.isReady()) {
            queryOwned();
            return;
        }
        client.startConnection(new BillingClientStateListener() {
            @Override
            public void onBillingSetupFinished(@NonNull BillingResult billingResult) {
                if (billingResult.getResponseCode() != BillingClient.BillingResponseCode.OK) {
                    deliverError("Play Billing bağlanamadı (" + billingResult.getResponseCode() + ")");
                    return;
                }
                queryOwned();
            }

            @Override
            public void onBillingServiceDisconnected() {
                deliverError("Play Billing bağlantısı koptu");
            }
        });
    }

    private void queryOwned() {
        QueryPurchasesParams params = QueryPurchasesParams.newBuilder()
                .setProductType(BillingClient.ProductType.SUBS)
                .build();
        client.queryPurchasesAsync(params, (billingResult, purchases) -> {
            if (billingResult.getResponseCode() != BillingClient.BillingResponseCode.OK
                    || purchases == null
                    || purchases.isEmpty()) {
                deliverError("Geri yüklenecek abonelik bulunamadı");
                return;
            }
            Purchase purchase = null;
            for (Purchase item : purchases) {
                if (item.getPurchaseState() == Purchase.PurchaseState.PURCHASED) {
                    purchase = item;
                    break;
                }
            }
            if (purchase == null) {
                deliverError("Geri yüklenecek abonelik bulunamadı");
                return;
            }
            String token = purchase.getPurchaseToken();
            String orderId = purchase.getOrderId() == null ? "" : purchase.getOrderId();
            String productId = purchase.getProducts().isEmpty()
                    ? pendingProductId
                    : purchase.getProducts().get(0);
            deliverOk(token, productId, orderId);
        });
    }

    private void ensureConnectedThenBuy(String sku) {
        if (client.isReady()) {
            queryAndLaunch(sku);
            return;
        }
        client.startConnection(new BillingClientStateListener() {
            @Override
            public void onBillingSetupFinished(@NonNull BillingResult billingResult) {
                if (billingResult.getResponseCode() != BillingClient.BillingResponseCode.OK) {
                    deliverError("Play Billing bağlanamadı (" + billingResult.getResponseCode() + ")");
                    return;
                }
                queryAndLaunch(sku);
            }

            @Override
            public void onBillingServiceDisconnected() {
                deliverError("Play Billing bağlantısı koptu");
            }
        });
    }

    private void queryAndLaunch(String sku) {
        Activity activity = activityRef.get();
        if (activity == null) {
            deliverError("Aktivite yok");
            return;
        }
        QueryProductDetailsParams.Product product = QueryProductDetailsParams.Product.newBuilder()
                .setProductId(sku)
                .setProductType(BillingClient.ProductType.SUBS)
                .build();
        QueryProductDetailsParams params = QueryProductDetailsParams.newBuilder()
                .setProductList(Collections.singletonList(product))
                .build();
        client.queryProductDetailsAsync(params, (billingResult, productDetailsResult) -> {
            if (billingResult.getResponseCode() != BillingClient.BillingResponseCode.OK
                    || productDetailsResult == null) {
                deliverError("Abonelik ürünü bulunamadı. Play Console’da " + sku + " tanımlı mı?");
                return;
            }
            List<ProductDetails> productDetailsList = productDetailsResult.getProductDetailsList();
            if (productDetailsList == null || productDetailsList.isEmpty()) {
                deliverError("Abonelik ürünü bulunamadı. Play Console’da " + sku + " tanımlı mı?");
                return;
            }
            ProductDetails details = productDetailsList.get(0);
            List<ProductDetails.SubscriptionOfferDetails> offers = details.getSubscriptionOfferDetails();
            if (offers == null || offers.isEmpty()) {
                deliverError("Abonelik teklifi yok");
                return;
            }
            String offerToken = offers.get(0).getOfferToken();
            BillingFlowParams.ProductDetailsParams detailParams =
                    BillingFlowParams.ProductDetailsParams.newBuilder()
                            .setProductDetails(details)
                            .setOfferToken(offerToken)
                            .build();
            BillingFlowParams flowParams = BillingFlowParams.newBuilder()
                    .setProductDetailsParamsList(Collections.singletonList(detailParams))
                    .build();
            BillingResult launchResult = client.launchBillingFlow(activity, flowParams);
            if (launchResult.getResponseCode() != BillingClient.BillingResponseCode.OK) {
                deliverError("Ödeme ekranı açılamadı (" + launchResult.getResponseCode() + ")");
            }
        });
    }

    @Override
    public void onPurchasesUpdated(@NonNull BillingResult billingResult, @Nullable List<Purchase> purchases) {
        int code = billingResult.getResponseCode();
        if (code == BillingClient.BillingResponseCode.USER_CANCELED) {
            deliverError("Ödeme iptal edildi");
            return;
        }
        if (code != BillingClient.BillingResponseCode.OK || purchases == null || purchases.isEmpty()) {
            deliverError("Satın alma tamamlanamadı (" + code + ")");
            return;
        }
        Purchase purchase = purchases.get(0);
        String token = purchase.getPurchaseToken();
        String orderId = purchase.getOrderId() == null ? "" : purchase.getOrderId();
        String productId = pendingProductId;
        if (!purchase.getProducts().isEmpty()) {
            productId = purchase.getProducts().get(0);
        }
        if (purchase.getPurchaseState() == Purchase.PurchaseState.PURCHASED
                && !purchase.isAcknowledged()) {
            AcknowledgePurchaseParams ack = AcknowledgePurchaseParams.newBuilder()
                    .setPurchaseToken(token)
                    .build();
            client.acknowledgePurchase(ack, result -> {
                // Sunucu da acknowledge eder; yerelde en az bir kez deneriz.
            });
        }
        deliverOk(token, productId, orderId);
    }

    private void deliverOk(String token, String productId, String orderId) {
        try {
            JSONObject json = new JSONObject();
            json.put("purchaseToken", token);
            json.put("productId", productId);
            json.put("orderId", orderId);
            evaluate("window.__tilkoBillingDone && window.__tilkoBillingDone(" + json + ");");
        } catch (Exception exc) {
            deliverError("Sonuç JSON yazılamadı");
        }
    }

    private void deliverError(String message) {
        try {
            JSONObject json = new JSONObject();
            json.put("error", message == null ? "Bilinmeyen hata" : message);
            evaluate("window.__tilkoBillingDone && window.__tilkoBillingDone(" + json + ");");
        } catch (Exception ignored) {
            evaluate("window.__tilkoBillingDone && window.__tilkoBillingDone({error:'Hata'});");
        }
    }

    private void evaluate(String script) {
        Activity activity = activityRef.get();
        WebView webView = webViewRef.get();
        if (activity == null || webView == null) {
            return;
        }
        activity.runOnUiThread(() -> webView.evaluateJavascript(script, null));
    }
}
