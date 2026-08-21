# KPSS hazırlık — backend

YouTube ders videosunun altyazısını saniye damgalı çalışma notlarına ve ÖSYM tarzı sorulara
çevirir. Notlar; tanım, anahtar bilgiler, hafıza tekniği ve ÖSYM tuzağı uyarısı içerir.

## Kurulum

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

`.env` içinde bir sağlayıcı seç ve `LLM_PROVIDER` değerini ona göre ayarla.

## Çalıştırma

```powershell
uvicorn app.main:app --reload
```

- Arayüz: <http://127.0.0.1:8000>
- Dokümantasyon: <http://127.0.0.1:8000/docs>
- Sağlık: <http://127.0.0.1:8000/health>

## Sağlayıcı seçenekleri

| Sağlayıcı | Ayar | Notlar |
|---|---|---|
| Groq | `LLM_PROVIDER=groq` | Ücretsiz katman dar; Developer ile ucuz 120B |
| OpenRouter | `LLM_PROVIDER=openrouter` | Tek anahtarla birçok model; `:free` modeller ücretsiz |
| Gemini | `LLM_PROVIDER=gemini` | Ücretsiz katman **günde 20 istek**; hızlı ama sınırlı |
| OpenAI | `LLM_PROVIDER=openai` | Kredi gerekir, kalite yüksek |
| Hugging Face | `LLM_PROVIDER=huggingface` | Aylık ücretsiz kredi; bitince 402 döner |
| Ollama | `LLM_PROVIDER=ollama` | Yerel, ücretsiz, kota yok; çok yavaş |

Sağlayıcıya göre parça boyutu, çağrı başına soru sayısı ve paralellik otomatik ayarlanır
(`app/config.py`). Yerel modelde bağlam küçük tutulur ve istekler sıraya alınır.

### Groq

<https://console.groq.com/keys> adresinden anahtar al ve `.env` içine yaz:

```
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-120b
```

Ücretsiz katmanda `openai/gpt-oss-120b` dakikada 8.000 jeton kabul eder. 24.000 karakterlik
parça bu tavanı aşar; kod Groq'ta parçaları 8.000 karakterde tutar ve istekleri sıraya koyar.

Hız sınırında sağlayıcı kaç saniye bekleneceğini söyler; kod milisaniye dahil bu süreyi
okuyup tekrarlar. Kota biterse `LLM_FALLBACK=ollama` yedeğe düşer (yavaş ama durmaz).

**7/24 ve kota doldurmamak:** ücretsiz Groq günde ~30 istek verir, bu yüzden doluyor.
GPU kiralamak (~$50/ay) 7B çalıştırır, 120B kalitesini vermez. Ucuz çözüm Groq Developer:

1. <https://console.groq.com/settings/billing> — kart ekle, **$5** yükle (abonelik yok).
2. Aynı `GROQ_API_KEY` kalır; tavan 8K TPM → ~250K TPM çıkar, günlük 200K jeton kalkar.
3. `gpt-oss-120b` fiyatı kabaca **4 saatlik video başına ~0,06 $**. Önbellek sayesinde
   aynı video ikinci kez ücretsiz. Ayda 30 yeni uzun video ≈ **2 $**.

Bilgisayar uykuya geçmesin: Windows’ta “Ekranı kapat / uyku” → Asla. Ollama yedek olarak
arka planda kalsın.

### OpenRouter

<https://openrouter.ai/keys> adresinden anahtar al (`sk-or-v1-...`) ve `.env` içine yaz:

```
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openai/gpt-oss-120b
```

Ücretsiz denemek için model adına `:free` ekle, örneğin `openai/gpt-oss-20b:free`.
Bu modellerin hız sınırı dardır; kod parçayı küçültüp istekleri sıraya koyar. Ücretsiz
kuyruk dolunca yine 429 döner — kalıcı 7/24 için OpenRouter’a da birkaç dolar yüklemek
veya ücretli `openai/gpt-oss-120b` kullanmak gerekir.

Modeller: <https://openrouter.ai/models>

### Hugging Face

<https://huggingface.co/settings/tokens> adresinden bir token al ve `.env` içine yaz:

```
LLM_PROVIDER=huggingface
HF_API_KEY=hf_...
HF_MODEL=openai/gpt-oss-120b
```

Token oluştururken **"Make calls to Inference Providers"** iznini işaretle; bu izin olmadan
istekler 403 döner.

İstek `https://router.huggingface.co/v1` üzerinden en hızlı sağlayıcıya yönlenir. Belirli bir
sağlayıcı istersen model adına sonek ekle: `openai/gpt-oss-120b:groq`.

Ölçtüğüm süreler (4 satırlık örnek altyazı, not + 5 soru):

| Model | Süre | Not |
|---|---|---|
| `openai/gpt-oss-120b` | ~4 sn | Önerilen; hızlı ve tutarlı |
| `Qwen/Qwen2.5-72B-Instruct` | ~53 sn | Çalışır, hafıza teknikleri zayıf |
| `gemma2:9b` (yerel) | ~250 sn | Kotasız ama yavaş |

### Yerel model (Ollama)

```powershell
winget install -e --id Ollama.Ollama
ollama pull gemma2:9b
```

Ardından `.env` içinde:

```
LLM_PROVIDER=ollama
OLLAMA_MODEL=gemma2:9b
```

Ollama servisi kurulumla birlikte arka planda çalışır. Kapalıysa `ollama serve` ile başlatılır.
`ollama ps` çıktısındaki PROCESSOR sütunu GPU yazıyorsa hızlanma etkindir.

Model seçimi (8 GB VRAM için):

| Model | Boyut | Not |
|---|---|---|
| `gemma2:9b` | 5,4 GB | Türkçesi iyi, önerilen |
| `qwen2.5:7b-instruct` | 4,7 GB | Daha hızlı, Türkçede zaman zaman hata yapar |
| `qwen2.5:3b-instruct` | 1,9 GB | En hızlı, kalite düşük |

Yerel model yavaştır: bir altyazı parçası için 2-3 dakika. Uzun bir ders videosu yarım saati
aşabilir. Önbellek sayesinde bu bedel video başına bir kez ödenir.

## Sağlayıcıyı sınama

Uzun bir analizi beklemeden ayarların doğru olduğunu görmek için:

```powershell
.\.venv\Scripts\python.exe tools\check_provider.py
```

## İstek ekonomisi

Ücretsiz kotalar **istek sayısına** göre sayıldığı için:

- Altyazı büyük parçalara bölünür (bulutta 24.000 karakter), böylece çağrı sayısı azalır.
- Bir çağrıda 25'e kadar soru üretilir.
- LLM istemcisinin kendi tekrarları kapatılmıştır; tekrar mantığı tek yerde yönetilir.
- Günlük kota bitince `LLM_FALLBACK` (varsayılan: Ollama) devreye girer; uygulama durmaz.
- Sonuçlar `backend/.cache` altında saklanır; aynı video + aynı ayar ikinci kez istek harcamaz.

## Tuzak defteri ve aralıklı tekrar

Yanlış sorular SQLite'ta (`backend/data/kpss.db`) saklanır. Ebbinghaus basamakları:
yanlış → 24 saat, doğru tekrar → 3 gün, sonra 7, sonra 15 gün.

```
POST /save_trap          yanlış + süre (time_spent_seconds)
GET  /daily_missions/{user_id}
POST /complete_trap      günlük görevi doğru/yanlış işaretle
GET  /progress/{user_id}
GET  /leaderboard
GET  /bulletin/latest
GET  /bulletin/{hafta}.html
POST /bulletin/generate
```

60 saniyeden uzun çözüm `time_trap_triggered=true` kaydeder ve şu uyarıyı döner:
"Dikkat! Bilgiden değil, süreden kaybediyorsun. ÖSYM seni 60 saniyeden fazla oyaladı."

### Haftanın Tuzakları

Her ISO haftası, tuzak defterindeki **anonim** düşüşleri tarar ve en çok kayılan 3 tuzağı
gazete manşeti HTML'ine çevirir. Kimlik yok; yüzde, o hafta deftere düşen adaylar içindedir.

Pazar akşamı (görev zamanlayıcı):

```powershell
.\.venv\Scripts\python.exe tools\weekly_bulletin.py
```

HTML yazdırma diyaloğu (Ctrl+P) PDF üretir; ekstra PDF motoru yok.

### Oyunlaştırma

Doğru temizlik XP verir. Günün tüm tuzakları bitince seri (streak) artar. Rozetler:
ilk düşüş, ilk temizlik, 3/7/15 gün seri, 10/50 av. Seviye 2 bülteni, seviye 3 liderliği açar.
Liderlik tablosu `user_id` göstermez, `Aday-A3F2` gibi takma ad kullanır.
