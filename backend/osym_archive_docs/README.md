# ÖSYM arşivi (RAG)

Son 10 yılın çıkmış soru PDF veya düz metinlerini buraya koyun, ardından
`POST /admin/feed-osym-archives` tetikleyin.

- Desteklenen: `.pdf`, `.txt`, `.md`, `.json`
- Telif: orijinal ÖSYM kitapçıklarını depoya commit etmeyin; yerel `inbox/` kullanın.
- Motor kalıpları `osym_style_guide.json` ve veritabanındaki `osym_archive_docs` tablosunda tutar.
