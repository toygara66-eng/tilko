# TİLKO Play çıktısı

APK, uygulamayı telefona koyar. Analiz/notlar **senin domainindeki API** üzerinden gider.

## 0) Domain aldın — sıra DNS + sunucu

Domain sadece isim. Telefon `https://api.senin-domain.com` diyecek; o adresin arkasında 7/24 açık bir Linux sunucu olmalı (aylık ~5–8€ VPS: Hetzner / Contabo / DigitalOcean).

**DNS (domain panelinde, A kaydı):**

| İsim | Tip | Değer |
|---|---|---|
| `@` | A | VPS’in IPv4 adresi |
| `api` | A | aynı IPv4 |
| `www` | CNAME | `senin-domain.com` |

TTL 300 yeter. 5–30 dk sonra `ping api.senin-domain.com` VPS IP’sini göstermeli.

**Sunucuda (Ubuntu):**

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
# projeyi sunucuya kopyala (scp / git)
cd kpss-prep/deploy
# backend/.env üretim değerleriyle dolu olmalı (aşağıdaki 1. madde)
DOMAIN=senin-domain.com docker compose up -d --build
```

Caddy Let’s Encrypt ile HTTPS’i kendisi alır. Test:

```
https://api.senin-domain.com/health
```

`{"status":"ok"}` dönmeli.

Sonra bu makinede:

```
frontend/.env.production  →  NEXT_PUBLIC_API_BASE=https://api.senin-domain.com
CORS_ORIGINS=https://localhost,https://senin-domain.com,https://www.senin-domain.com,https://api.senin-domain.com
```

Domain adını buraya yaz, DNS’i bağlarız; sonra `android:prep`.

## 1) Canlı backend

`backend/.env` üretim:

```
APP_ENV=production
JWT_SECRET=  (en az 32 karakter, rastgele)
ADMIN_API_SECRET=  (en az 24 karakter)
PLAY_BILLING_SANDBOX=false
PLAY_WEBHOOK_SECRET=
PLAY_SERVICE_ACCOUNT_FILE=
CORS_ORIGINS=https://localhost
```

Sunucuyu HTTPS arkasına al (nginx / caddy). `CORS_ORIGINS` Capacitor Android için `https://localhost` olmalı; web de varsa virgülle ekle.

## 2) Frontend API adresi

```powershell
cd frontend
copy .env.production.example .env.production
```

`NEXT_PUBLIC_API_BASE` = 1. adımdaki HTTPS API (**telefonda `127.0.0.1` çalışmaz**). Kaydet, sonra:

```powershell
npm install
npm run android:prep
```

Bu `next build` (statik `out/`) + `npx cap sync android` çalıştırır.

## 3) İmza (Play)

```powershell
cd android
keytool -genkeypair -v -keystore tilko-release.jks -keyalg RSA -keysize 2048 -validity 10000 -alias tilko
copy keystore.properties.example keystore.properties
```

`keystore.properties` içini doldur. Play Console > App integrity > App signing key certificate SHA-256'yı `android/gradle.properties` içine:

```
TILKO_PLAY_CERT_SHA256=AB:CD:...
```

`tilko-release.jks` ve `keystore.properties` git'e gitmez.

## 4) AAB (Play'e yüklenen dosya)

Android Studio’da `android` klasörünü aç → **Build > Generate Signed App Bundle**.

Komut satırı (Gradle wrapper yoksa Android Studio kullan):

```powershell
cd android
.\gradlew bundleRelease
```

Çıktı: `android/app/build/outputs/bundle/release/app-release.aab`

APK denemek için: **Build > Build Bundle(s) / APK(s) > Build APK(s)**


## 5) Kontrol listesi

- [ ] API HTTPS ve `NEXT_PUBLIC_API_BASE` doğru (APK'ya gömülür, yanlışsa yeni build gerekir)
- [ ] `APP_ENV=production` ile backend ayağa kalkıyor
- [ ] Play sandbox kapalı
- [ ] İmza SHA-256 gradle'da
- [ ] `versionCode` / `versionName` `android/app/build.gradle` içinde artırıldı
- [ ] Cihazda YouTube analiz, giriş, Notlarım, tuzak defteri denendi
- [ ] Korsan imza tuzağı: SHA boşken debug geçer; release'de boş SHA `isOfficial=true` kalır — Play'e çıkmadan SHA doldur

Canlı API adresi ve keystore hazırsa bir sonraki adım `npm run android:prep` + `bundleRelease`.
