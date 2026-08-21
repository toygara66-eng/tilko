# TİLKO release — R8 full mode. Class/method names are rewritten.
-repackageclasses "t"
-allowaccessmodification
-overloadaggressively
-optimizationpasses 5

-keepattributes *Annotation*,Signature,InnerClasses,EnclosingMethod,JavascriptInterface,SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile

# JS bridge: obfuscate the Java class, keep only @JavascriptInterface names
# so WebView can still call isOfficial / fingerprints / openPlayStore.
-keepclassmembers,allowobfuscation class * {
    @android.webkit.JavascriptInterface <methods>;
}
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}

# Capacitor (present after `npx cap sync`) — obfuscate plugin classes,
# keep annotated plugin methods the WebView invokes by name.
-keep,allowobfuscation @com.getcapacitor.annotation.CapacitorPlugin class * {
    <init>(...);
}
-keepclassmembers class * {
    @com.getcapacitor.PluginMethod <methods>;
}
-dontwarn com.getcapacitor.**
-dontwarn com.capacitorjs.**

-dontwarn javax.annotation.**
-dontwarn org.bouncycastle.**
