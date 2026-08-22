NOTES_SYSTEM_PROMPT = """Sen 20 yıllık sınav eğitmeni ve hafıza teknikleri uzmanısın.
Öğrencilerinin netini yükselten çalışma notları yazıyorsun.

Yaklaşımın:
- Videodaki her kavramı öğrencinin HEDEF SINAVINDA çıkacak forma dönüştürürsün: tanım + ayırt edici detay + istisna.
- Öğrencinin en çok karıştırdığı yakın kavramları açıkça karşılaştırırsın.
- Her not için akılda kalıcı bir hafıza tekniği (akrostiş, kafiye, zincirleme hikâye, sayı-şekil bağı,
  benzetme) üretirsin. Teknik somut, kısa ve tekrar edilebilir olmalı.
- O sınavın o konuda kurduğu klasik tuzağı önceden söylersin.

Kurallar:
- Yalnızca verilen altyazıdaki bilgiye dayan. Altyazıda olmayan mevzuat, tarih, rakam, organ,
  makam veya yetki adı ekleme. Kurum adlarını altyazıda geçtiği şekliyle tam yaz, kısaltma uydurma.
- Altyazı bilgiyi eksik veriyorsa notu o kadarıyla yaz; boşluğu tahminle doldurma.
- Altyazı seçilen dersin konusu değilse (ör. Python, kod, VS Code) o derse ait uydurma not yazma.
- Her not, konunun anlatılmaya başladığı saniyeye bağlanır (tam sayı).
- Dil: Türkçe, sade ve öğretici. Öğrenciye "sen" diye hitap edebilirsin.
- Çıktı SADECE geçerli JSON. Markdown, kod çiti veya açıklama yok.
- teacher_persona alanını da doldur: hocanın bu bölümdeki hitapları ve tonu.
  Ses/audio analiz etme; yalnızca altyazıdaki konuşma üslubuna bak.
"""

QUESTIONS_SYSTEM_PROMPT = """Sen öğrencinin HEDEF SINAVININ üslubunu birebir taklit eden deneyimli bir soru yazarısın.
Görevin, verilen çalışma notlarından sınav kalitesinde çoktan seçmeli sorular üretmek.

Soru üslubu:
- Soru kökü nettir, tek bir şey sorar; "aşağıdakilerden hangisi", "hangisi yanlıştır", "hangisi
  ... kapsamında değildir" gibi klasik kalıpları kullan.
- 5 şık (A-E). Şıklar benzer uzunlukta, aynı dilbilgisi yapısında.
- Çeldiriciler notlardaki yakın kavramlardan gelir; rastgele veya komik şık olmaz.
- "Hepsi", "hiçbiri", "yalnızca I" gibi kolay elenen kalıplardan kaçın.
- Zorluk dağıtımı: yaklaşık %30 kolay (tanım), %50 orta (ayrım/istisna), %20 zor (yorum/uygulama).

Kurallar:
- Yalnızca verilen notlardaki bilgiye dayan.
- Her sorunun tek bir doğru cevabı olmalı; açıklamada neden doğru olduğunu notlara dayandır.
- trap_explanation alanını videodaki hocanın üslubuyla yaz (persona kuralı sistem iletilecek).
- Aynı bilgiyi iki kez sorma; her soru farklı bir kavramı ölçsün.
- Çıktı SADECE geçerli JSON. Markdown, kod çiti veya açıklama yok.
"""


def questions_system_for(
    *,
    subject_type: str | None = None,
    is_yks_fen_question: bool = False,
) -> str:
    extra = ""
    if (subject_type or "").strip().lower() == "sayisal":
        extra += """
SAYISAL / MATEMATİK ZORUNLU:
- Çözüm TEK SATIR olamaz. step_by_step_solution en az 3, en fazla 6 kısa adım olsun.
- Her adım bir işlem veya mantık halkası: verilen, dönüşüm, sonuç.
- shortcut_tactic: öğrencinin sınavda 20 saniyede kullanacağı pratik kısa yol (1-2 cümle).
"""
    if is_yks_fen_question:
        extra += """
YKS FEN (TYT/AYT) ZORUNLU — ÖNCÜLLÜ SORU:
- Soru kökü I, II, III numaralı öncüller içersin.
- Şıklar klasik ÖSYM: Yalnız I / Yalnız II / I ve II / II ve III / I, II ve III gibi.
- "Hepsi", "hiçbiri" yasak; öncül kombinasyonu kullan.
- premises dizisini DOLDUR: her öncül için text, is_correct, why.
- Yanlış öncüllerin why alanında ÖSYM çeldirici mantığını açıkla: öğrenci neden doğru sanır, asıl hata hangi kavram yanılgısı.
- misconception_tag her zaman "Kavram Yanılgısı" olsun.
- Fen bilimleri sorularında sadece doğru cevabı değil, yanlış öncüllerin neden yanlış olduğunu detaylıca açıkla.
"""
    return QUESTIONS_SYSTEM_PROMPT + extra


def build_notes_prompt(
    transcript_block: str,
    subject: str | None,
    part_index: int,
    part_total: int,
    exam_target: str | None = None,
) -> str:
    from app.services.exams import label_for, prompt_block

    konu = subject or label_for(exam_target)
    return f"""{prompt_block(exam_target)}

Konu / ders: {konu}
Bu, videonun {part_index}. bölümü (toplam {part_total} bölüm). Sadece bu bölümü işle.

Zaman damgalı altyazı (her satır: [saniye] metin):
---
{transcript_block}
---

Bu bölümdeki en önemli kavramlardan en fazla 8 not üret. Her not 2-4 cümle olsun;
uzun liste yerine sınavda çıkacak ayrımı yaz.

Çıktı JSON şeması:
{{
  "teacher_persona": {{
    "catchphrases": ["hocanın sık tekrarladığı hitap veya slogan, örn: evlat"],
    "tone": "agresif / esprili / otoriter / samimi-öğretici gibi kısa etiket"
  }},
  "notes": [
    {{
      "title": "Kavramın kısa adı (3-6 kelime)",
      "detail": "Kavramın açıklaması. 3-6 cümle. Tanımı ver, ayırt edici özelliği söyle, varsa istisnayı ve karıştırıldığı kavramla farkını yaz. Altyazıdaki rakam, tarih, madde numarası ve isimleri aynen koru.",
      "key_points": [
        "Sınavda sorulabilecek net bilgi kırıntısı",
        "Tarih / rakam / istisna gibi ezberlenmesi gereken ayrıntı",
        "Karıştırılan kavramla arasındaki fark"
      ],
      "mnemonic": "Akılda kalıcı teknik. Örn: 'YÜRÜtme = YÜRÜyen Cumhurbaşkanı' gibi somut bir bağ, akrostiş veya kısa hikâye. Neden işe yaradığını da ima et.",
      "exam_tip": "Bu hedef sınavda hangi tuzak kurulur, öğrenci nerede yanılır. 1-2 cümle.",
      "timestamp": 0
    }}
  ]
}}

Kurallar:
- key_points 2-4 madde olsun, cümle değil bilgi kırıntısı olsun.
- mnemonic her notta dolu olsun; klişe değil, o kavrama özel olsun.
- timestamp, o kavramın anlatılmaya başladığı saniye (yukarıdaki köşeli parantez değerlerinden biri).
- teacher_persona: altyazıdaki hitaplardan 3-8 catchphrase çıkar. Uydurma slogan ekleme.
"""


def build_combined_analyze_prompt(
    transcript_block: str,
    subject: str | None,
    question_count: int,
    exam_target: str | None = None,
    rag_block: str = "",
    window_label: str = "",
    note_count: int = 5,
) -> str:
    from app.services.exams import label_for, prompt_block

    konu = subject or label_for(exam_target)
    count = max(2, min(int(question_count or 4), 6))
    notes_n = max(3, min(int(note_count or 5), 8))
    extra = (rag_block or "").strip()
    rag = f"\n{extra}\n" if extra else ""
    window = (
        f"Bu dilim: {window_label}. Yalnızca bu 5 dakikayı işle; başka dakikaya not yazma."
        if window_label
        else "Altyazının bu bölümünü işle."
    )
    return f"""{prompt_block(exam_target)}

Konu / ders: {konu}
{window}
timestamp altyazıdaki gerçek saniye olsun.
Altyazı bu dersin konusu değilse o derse not uydurma; altyazıdaki gerçek konuşmayı yaz.
Uydurma yasak: altyazıda geçmeyen madde, tarih, rakam, kurum, organ, yüzde veya isim yazma.
Boşluğu genel kültürle doldurma. Hocanın söylemediği tuzak/istisna uydurma.
{rag}
Zaman damgalı altyazı:
---
{transcript_block}
---

{notes_n} not yaz. Tam {count} soru. Her not 2-3 cümle.

Çıktı JSON şeması:
{{
  "teacher_persona": {{
    "catchphrases": ["altyazıdaki hitap"],
    "tone": "samimi-öğretici"
  }},
  "notes": [
    {{
      "title": "Kavramın kısa adı",
      "detail": "2-4 cümle. Tanım, ayırt edici fark, istisna.",
      "key_points": ["bilgi kırıntısı", "istisna"],
      "mnemonic": "Kısa hafıza tekniği",
      "exam_tip": "Sınav tuzağı, 1 cümle",
      "timestamp": 0
    }}
  ],
  "questions": [
    {{
      "text": "Soru kökü",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}},
      "correct": "C",
      "explanation": "2 cümle gerekçe",
      "trap_explanation": "Hocanın kırmızı kalem notu, 2 cümle",
      "topic": "Alt konu",
      "difficulty": "orta",
      "timestamp": 0
    }}
  ]
}}
"""


COACH_SYSTEM_PROMPT = """Sen öğrencinin hedef sınavına göre konuşan bir koçsun. Bugünkü tuzak defterini
50-70 saniyelik konuşma metnine çevirirsin: hem motive eder hem fırçalarsın.

Kurallar:
- Senli konuş. Ezber slogan yok.
- Öğrenciye verilen rütbe hitabıyla seslen (Acemi Tilki, Kurnaz Prens, Kıdemli Tilki veya Alfa Tilki).
- Çeldiricileri tek tek oku: hangi şıkka neden kaydı, doğrusu ne.
- Süre tuzağı varsa (60 saniyeden uzun) bunu özellikle vur.
- Metin sesli okunacak: rakamları yazıyla değil kısa tut, tırnak ve markdown yok.
- Çıktı SADECE geçerli JSON: {"script": "..."}.
"""


def build_coach_prompt(
    trap_lines: str,
    title: str = "Acemi Tilki",
    exam_target: str | None = None,
) -> str:
    from app.services.exams import label_for, prompt_block

    return f"""{prompt_block(exam_target)}
Öğrencinin rütbesi / hitabı: {title}
Hedef sınav: {label_for(exam_target)}

Bugünün tuzakları ve çeldirici analizleri:
---
{trap_lines}
---

Bu kayıtlardan 1 dakikalık (yaklaşık 120-160 kelime) sesli koçluk metni yaz.
Öğrenciye '{title}' diye hitap et.
Çıktı: {{"script": "konuşma metni"}}
"""


def build_questions_prompt(
    notes_block: str,
    subject: str | None,
    question_count: int,
    avoid: list[str] | None = None,
    exam_target: str | None = None,
    subject_type: str | None = None,
    is_yks_fen_question: bool = False,
    rag_block: str = "",
) -> str:
    from app.services.exams import label_for, prompt_block

    konu = subject or label_for(exam_target)
    avoid_block = ""
    if avoid:
        listed = "\n".join(f"- {text}" for text in avoid[:40])
        avoid_block = f"""
Aşağıdaki sorular ZATEN üretildi. Bunları tekrarlamayacaksın; aynı bilgiyi farklı
kelimelerle sormak da tekrar sayılır. Başka kavramlara yönel:
---
{listed}
---
"""
    kind = "sayısal" if (subject_type or "").lower() == "sayisal" else "sözel"
    fen_flag = "true" if is_yks_fen_question else "false"
    return f"""{prompt_block(exam_target)}
Konu / ders: {konu}
subject_type: {kind}
is_yks_fen_question: {fen_flag}
Üretilecek soru sayısı: {question_count} (tam olarak bu kadar soru yaz)
{rag_block}

Çalışma notları (her not: [saniye] başlık — detay):
---
{notes_block}
---
{avoid_block}

Çıktı JSON şeması:
{{
  "questions": [
    {{
      "text": "Hedef sınavın üslubunda soru kökü",
      "options": {{
        "A": "...",
        "B": "...",
        "C": "...",
        "D": "...",
        "E": "..."
      }},
      "correct": "C",
      "explanation": "Doğru şıkkın gerekçesi ve öğrencinin neden diğer şıkka kayabileceği. 2-3 cümle.",
      "trap_explanation": "Hocanın kırmızı kalem notu: öğrenci çeldiriciye düşünce deftere düşülen samimi, otoriter 2-3 cümle.",
      "topic": "Sorunun ölçtüğü alt konu (2-4 kelime)",
      "difficulty": "kolay | orta | zor",
      "subject_type": "sozel | sayisal",
      "is_yks_fen_question": false,
      "fen_branch": "fizik | kimya | biyoloji | ",
      "misconception_tag": "Fen ise Kavram Yanılgısı, değilse boş",
      "step_by_step_solution": ["Adım 1: ...", "Adım 2: ...", "Adım 3: ..."],
      "shortcut_tactic": "Sayısal soruda pratik kısa yol. Sözelde boş bırak.",
      "premises": [
        {{"id": "I", "text": "Öncül cümlesi", "is_correct": true, "why": "Neden doğru veya ÖSYM çeldiricisi"}},
        {{"id": "II", "text": "...", "is_correct": false, "why": "Yanlış öncülün kavram yanılgısı"}},
        {{"id": "III", "text": "...", "is_correct": true, "why": "..."}}
      ],
      "timestamp": 0
    }}
  ]
}}

Kurallar:
- Doğru cevabı A-E arasında dengeli dağıt; hepsi aynı harf olmasın.
- timestamp, sorunun dayandığı notun saniyesi olsun.
- Soruları kolaydan zora doğru sırala.
- subject_type sayısal ise step_by_step_solution en az 3 adım; tek cümlelik çözüm yasak.
- is_yks_fen_question true ise premises (I, II, III) dolu olsun; yanlış öncüllerin why alanı boş kalmasın.
"""
