# Kendi KPSS modelini eğitmek

Amaç: açık ağırlıklı bir modeli, uygulamanın istediği JSON'u ÖSYM üslubunda üretecek şekilde
ince ayardan geçirmek. Sonuçta ücretsiz, kotasız ve KPSS'ye özel bir model olur.

Sıfırdan model yazmıyoruz; hazır bir modele KPSS'yi öğretiyoruz. Buna **LoRA ince ayarı**
denir: modelin milyarlarca ağırlığını dondurup aralara küçük eğitilebilir katmanlar koyarız.
Ücretsiz Colab GPU'sunda birkaç saat sürer.

## Süreç

```
1. Veri topla        →  guclu model calisirken istek/yanit ciftleri kaydedilir
2. Veri setini kur   →  build_dataset.py  (temizler, eler, boler)
3. Egit              →  kpss_lora_colab.ipynb  (Colab T4)
4. Kullan            →  Ollama'ya yukle, .env icinde modeli sec
```

## 1. Veri topla

`backend/.env` içinde:

```
CAPTURE_TRAINING_DATA=true
LLM_PROVIDER=gemini        # veya huggingface — guclu bir model olmali
```

Artık her analiz, istek ve yanıtı `training/data/raw/` altına yazar. Ne kadar çok ders
videosu analiz edersen veri o kadar zenginleşir. Küçük model burada büyük modeli taklit
etmeyi öğrenir; buna **damıtma** denir.

Yerel model (`ollama`) ile veri toplamak işe yaramaz: model kendi hatalarını öğrenir.

## 2. Elindeki gerçek soruları ekle

Damıtma verisi biçimi öğretir, gerçek ÖSYM soruları üslubu öğretir. İkisi birlikte en iyi
sonucu verir. CSV veya JSON olarak topladığın soruları içe aktar:

```powershell
python import_questions.py sorular.csv --subject "Anayasa"
```

Beklenen sütunlar: `soru, a, b, c, d, e, dogru, aciklama, konu, zorluk`
(`aciklama`, `konu` ve `zorluk` isteğe bağlıdır.)

## 3. Veri setini kur

```powershell
cd training
python build_dataset.py
```

Script; bozuk satırları atar, aynı örneği iki kez almaz ve eksik alanlı yanıtları eler.
Zayıf örnek modele zarar verir, bu yüzden eleme sıkıdır: notlarda başlık, en az 80 karakter
detay ve hafıza tekniği; sorularda beş şıkkın tamamı ve geçerli bir doğru cevap aranır.

Çıktı: `data/train.jsonl` ve `data/val.jsonl`.

## 4. Eğit

`kpss_lora_colab.ipynb` dosyasını [Colab](https://colab.research.google.com/)'a yükle,
çalışma zamanını **T4 GPU** yap ve hücreleri sırayla çalıştır. İki dosyayı (`train.jsonl`,
`val.jsonl`) sol paneldeki dosya alanına sürükle.

## 5. Kullan

Defterin son hücresi modeli GGUF'a çevirir. İndirdikten sonra:

```powershell
ollama create kpss -f Modelfile
```

`backend/.env` içinde:

```
LLM_PROVIDER=ollama
OLLAMA_MODEL=kpss
```

## Ne kadar veri gerekir?

| Örnek sayısı | Beklenti |
|---|---|
| < 100 | Biçim bile tam oturmaz |
| 200-500 | JSON biçimi güvenilir hâle gelir |
| 1000+ | Üslup ve konu kapsamı gerçekten iyileşir |

Bir video analizi ortalama 2-4 kayıt üretir. 1000 örnek için birkaç yüz video gerekir;
bu yüzden veri toplamayı günlük kullanımın doğal parçası hâline getirmek en pratik yoldur.

## Donanım notu

Eğitim araçları NVIDIA CUDA'ya bağlıdır; bu makinedeki Intel Arc A750 eğitim için
kullanılamaz. Bu yüzden eğitim Colab'da yapılır, sonuç yerelde çalıştırılır.
