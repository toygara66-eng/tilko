# Flutter istemci

Kaynak kod hazır. Bu makinede Flutter SDK yok; kurulunca:

```powershell
cd mobile
flutter create . --project-name kpss_prep
flutter pub get
flutter run -d chrome --dart-define=API_BASE=http://127.0.0.1:8000
```

Android emülatör backend adresi `http://10.0.2.2:8000` (bkz. `lib/api.dart`).
Fiziksel telefonda bilgisayarın LAN IP’sini kullan.

Şimdilik tarayıcı arayüzü: backend çalışırken http://127.0.0.1:8000
