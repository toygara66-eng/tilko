import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import ChallengeLeaderboard, DailyChallenge, UserStats
from app.services.gamification import alias_for, award_hunt
from app.services import anti_cheat
from app.services.penalty import get_or_create_user
from app.services.ranks import address_for
from app.services.exams import DEFAULT_EXAM, exam_of

ISTANBUL_OFFSET = timezone(timedelta(hours=3))

KPSS = ("kpss_lisans", "kpss_onlisans", "kpss_ortaogretim")

ISTANBUL_OFFSET = timezone(timedelta(hours=3))


def today_istanbul():
    try:
        return datetime.now(ZoneInfo("Europe/Istanbul")).date()
    except ZoneInfoNotFoundError:
        return datetime.now(ISTANBUL_OFFSET).date()


TOP_N = 10

QUESTION_BANK = [
    {
        "question_text": "Tanzimat Fermanı hangi yılda ilan edilmiştir?",
        "options": {
            "A": "1839",
            "B": "1856",
            "C": "1876",
            "D": "1908",
            "E": "1923",
        },
        "correct_answer": "A",
        "trap_explanation": "1856’ya atladıysan sazan oldun. Tanzimat 1839, Islahat 1856. ÖSYM her yıl aynı yemi atar.",
        "exams": list(KPSS) + ["oabt"],
    },
    {
        "question_text": "Türkiye’de yürürlükteki Anayasa hangi yılda kabul edilmiştir?",
        "options": {
            "A": "1921",
            "B": "1924",
            "C": "1961",
            "D": "1982",
            "E": "2017",
        },
        "correct_answer": "D",
        "trap_explanation": "2017 değişiklik yılıdır, kabul yılı değildir. Yürürlükteki metin 1982 Anayasası.",
    },
    {
        "question_text": "Kanun-i Esasi hangi olayla yürürlüğe girmiştir?",
        "options": {
            "A": "Tanzimat",
            "B": "Islahat",
            "C": "I. Meşrutiyet",
            "D": "II. Meşrutiyet",
            "E": "Cumhuriyet’in ilanı",
        },
        "correct_answer": "C",
        "trap_explanation": "1908’e sapıttın. Kanun-i Esasi = I. Meşrutiyet, 1876. II. Meşrutiyet 1908’dir.",
    },
    {
        "question_text": "TBMM hangi tarihte açılmıştır?",
        "options": {
            "A": "19 Mayıs 1919",
            "B": "23 Nisan 1920",
            "C": "30 Ağustos 1922",
            "D": "29 Ekim 1923",
            "E": "3 Mart 1924",
        },
        "correct_answer": "B",
        "trap_explanation": "19 Mayıs Samsun, 29 Ekim Cumhuriyet. Meclis 23 Nisan 1920’de açılır. Tarihleri karıştırma.",
    },
    {
        "question_text": "Saltanat hangi tarihte kaldırılmıştır?",
        "options": {
            "A": "23 Nisan 1920",
            "B": "1 Kasım 1922",
            "C": "29 Ekim 1923",
            "D": "3 Mart 1924",
            "E": "20 Ocak 1921",
        },
        "correct_answer": "B",
        "trap_explanation": "Cumhuriyet 29 Ekim, halifelik 3 Mart 1924. Saltanat 1 Kasım 1922’de gider. Üçlü tuzak.",
    },
    {
        "question_text": "Halifelik hangi tarihte kaldırılmıştır?",
        "options": {
            "A": "1 Kasım 1922",
            "B": "29 Ekim 1923",
            "C": "3 Mart 1924",
            "D": "20 Nisan 1924",
            "E": "17 Kasım 1922",
        },
        "correct_answer": "C",
        "trap_explanation": "3 Mart 1924 paketi: Tevhid-i Tedrisat, Şer’iye ve Evkaf’ın kaldırılması, halifeliğin ilgası. Saltanatla karıştırma.",
    },
    {
        "question_text": "1982 Anayasası’na göre yasama yetkisi kime aittir?",
        "options": {
            "A": "Cumhurbaşkanı",
            "B": "Bakanlar Kurulu",
            "C": "TBMM",
            "D": "Anayasa Mahkemesi",
            "E": "Hâkimler ve Savcılar Kurulu",
        },
        "correct_answer": "C",
        "trap_explanation": "Yasama TBMM’dedir. Cumhurbaşkanlığı sistemi yürütmeyi şişirdi diye yasamayı kaptırma.",
    },
    {
        "question_text": "I. Meşrutiyet hangi padişah döneminde ilan edilmiştir?",
        "options": {
            "A": "Abdülmecid",
            "B": "Abdülaziz",
            "C": "II. Abdülhamid",
            "D": "V. Mehmet Reşad",
            "E": "II. Mahmud",
        },
        "correct_answer": "C",
        "trap_explanation": "Abdülmecid Tanzimat, Abdülaziz Islahat sonrası. I. Meşrutiyet 1876’da II. Abdülhamid.",
    },
    {
        "question_text": "Lozan Antlaşması hangi yılda imzalanmıştır?",
        "options": {
            "A": "1920",
            "B": "1921",
            "C": "1922",
            "D": "1923",
            "E": "1924",
        },
        "correct_answer": "D",
        "trap_explanation": "Sevr 1920, Mudanya 1922, Lozan 24 Temmuz 1923. Yıl tuzağı klasik.",
    },
    {
        "question_text": "2017 Anayasa değişikliği ile Türkiye’de hangi hükümet sistemine geçilmiştir?",
        "options": {
            "A": "Parlamenter sistem",
            "B": "Yarı başkanlık",
            "C": "Cumhurbaşkanlığı hükümet sistemi",
            "D": "Meclis hükümeti",
            "E": "Anayasal monarşi",
        },
        "correct_answer": "C",
        "trap_explanation": "2017 referandumu başkanlık değil; resmî adı Cumhurbaşkanlığı hükümet sistemidir. Şık diline dikkat.",
        "exams": list(KPSS) + ["oabt"],
    },
    {
        "question_text": "TYT Türkçe’de ‘anlamca çelişen cümle’ sorusunda asıl tuzak nedir?",
        "options": {
            "A": "Noktalama",
            "B": "Yakın anlamlıyı zıt sanmak",
            "C": "Yazım yanlışı",
            "D": "Paragraf uzunluğu",
            "E": "Sözcük türü",
        },
        "correct_answer": "B",
        "trap_explanation": "YKS sazanlığı: yakın anlamlıyı zıt sanmak. Kökteki ‘çelişen’i kaçırma.",
        "exams": ["yks"],
    },
    {
        "question_text": "AYT matematikte türev-limit çeldiricisi en çok nerede kurulur?",
        "options": {
            "A": "Toplama işlemi",
            "B": "Süreklilik ile türevin karıştırılması",
            "C": "Üslü sayı",
            "D": "Oran-orantı",
            "E": "Temel çarpma",
        },
        "correct_answer": "B",
        "trap_explanation": "Limit var diye türev vardır sanmak klasik AYT yemi. Süreklilik ≠ türev.",
        "exams": ["yks"],
        "subject_type": "sayisal",
        "shortcut_tactic": "Limit var ≠ türev var. Önce süreklilik, sonra iki yanlı türev.",
        "step_by_step_solution": [
            "Limitin varlığı sürekliliğin, süreklilik türevin gerekli şartıdır; yeterli değildir.",
            "Köşe, mutlak değer, |x| gibi noktalarda limit vardır, türev yoktur.",
            "AYT tuzağı: ‘limit hesapladım o hâlde türev vardır’ cümlesini reddet.",
        ],
    },
    {
        "question_text": "ÖABT’de Bloom taksonomisinde ‘analiz’ basamağı hangisine karşılık gelir?",
        "options": {
            "A": "Ezber",
            "B": "Kavrama",
            "C": "Uygulama",
            "D": "Ögeleri ayırt edip ilişkileri görme",
            "E": "Değerlendirme",
        },
        "correct_answer": "D",
        "trap_explanation": "Uygulama ile analizi, sentez ile değerlendirmeyi karıştırma. Analiz: parçala, ilişkiyi gör.",
        "exams": ["oabt"],
    },
    {
        "question_text": "LGS fen’de ‘katı-sıvı-gaz’ yoğunluk karşılaştırmasında en sık düşülen tuzak nedir?",
        "options": {
            "A": "Renk",
            "B": "Kütle ile yoğunluğu karıştırmak",
            "C": "Ses",
            "D": "Işık",
            "E": "Tat",
        },
        "correct_answer": "B",
        "trap_explanation": "Ağır olan yoğundur sanmak LGS yemi. Yoğunluk = kütle / hacim.",
        "exams": ["lgs", "other"],
        "subject_type": "sayisal",
    },
    {
        "question_text": (
            "Bir sınıfta öğrencilerin %40’ı matematik, %30’u Türkçe seçmeli alıyor. "
            "İkisini birden alanlar %10 ise, hiçbirini almayanların oranı kaçtır?"
        ),
        "options": {"A": "%30", "B": "%40", "C": "%50", "D": "%60", "E": "%70"},
        "correct_answer": "B",
        "trap_explanation": (
            "%40+%30=%70 deyip %10’u unuttun. Kesişim iki kez sayılır. "
            "En az birini alan = 40+30-10=60; hiçbiri = 40."
        ),
        "subject_type": "sayisal",
        "shortcut_tactic": "En az biri = A+B−kesişim. Hiçbiri = 100 − o toplam.",
        "step_by_step_solution": [
            "Matematik veya Türkçe alanları birleşim olarak yaz: |A∪B| = |A|+|B|−|A∩B|.",
            "40 + 30 − 10 = 60. Sınıfın %60’ı en az bir dersi alıyor.",
            "Hiçbirini almayan = 100 − 60 = 40.",
        ],
        "exams": list(KPSS) + ["yks", "lgs", "oabt", "other"],
    },
    {
        "question_text": (
            "3, 6, 12, 24, 48, … dizisinde 6. terim 48 ise 8. terim kaçtır? "
            "Dikkat: her terim bir öncekinin 2 katıdır."
        ),
        "options": {"A": "72", "B": "96", "C": "144", "D": "192", "E": "96 ile 144 arası"},
        "correct_answer": "D",
        "trap_explanation": (
            "6. terimden 2 adım daha: 48→96→192. 72’ye sapmak aritmetik dizi yemidir."
        ),
        "subject_type": "sayisal",
        "shortcut_tactic": "Geometrik dizi: a₈ = a₆ × 2² = 48 × 4 = 192.",
        "step_by_step_solution": [
            "Çarpan 2; dizi geometriktir, ortak fark değildir.",
            "8. terim, 6. terimden 2 adım ileride: 48 × 2 × 2.",
            "48 × 4 = 192.",
        ],
        "exams": list(KPSS) + ["yks", "lgs", "other"],
    },
    {
        "question_text": (
            "f(x)=x² için lim x→0 [f(x)/x] değeri hangisidir? "
            "Türev tanımıyla karıştırma."
        ),
        "options": {"A": "0", "B": "1", "C": "2", "D": "tanımsız", "E": "∞"},
        "correct_answer": "A",
        "trap_explanation": (
            "x²/x = x, x→0 iken 0. Türev tanımındaki [f(x)−f(0)]/x ile karıştırıp 0 sandın "
            "doğru; 2’ye zıpladıysan f'(x)=2x tuzağına düştün — o limit türevin kendisi değil."
        ),
        "subject_type": "sayisal",
        "shortcut_tactic": "Sadeleştir: x²/x = x (x≠0). Limit 0. Türev formülünü ezbere basma.",
        "step_by_step_solution": [
            "x≠0 iken x²/x = x yaz.",
            "lim x→0 x = 0.",
            "Bu, f'(0) sorusu değil; paydada yalnız x var, f(0) çıkarılmamış.",
        ],
        "exams": ["yks"],
    },
    {
        "question_text": (
            "I, II ve III numaralı ifadelerden hangileri doğrudur?\n"
            "I. Sürtünmesiz yatay düzlemde net kuvvet yoksa cisim durur.\n"
            "II. ivme, net kuvvetle aynı yöndedir.\n"
            "III. Kütle artarsa aynı net kuvvette ivme azalır."
        ),
        "options": {
            "A": "Yalnız I",
            "B": "Yalnız II",
            "C": "I ve II",
            "D": "II ve III",
            "E": "I, II ve III",
        },
        "correct_answer": "D",
        "trap_explanation": (
            "I klasik kavram yanılgısı: net kuvvet yoksa durmak zorunda değil, "
            "sabit hızlı hareket de olur. Newton I."
        ),
        "subject_type": "sayisal",
        "is_yks_fen": True,
        "fen_branch": "fizik",
        "misconception_tag": "Kavram Yanılgısı",
        "shortcut_tactic": "Net kuvvet 0 ⇒ ivme 0, hız sabit (sıfır olmak zorunda değil).",
        "step_by_step_solution": [
            "I yanlış: Fnet=0 iken v sabit olabilir; durma özel durumdur.",
            "II doğru: a = Fnet/m, yön net kuvvetin yönüdür.",
            "III doğru: m artınca aynı F için a küçülür.",
        ],
        "premises": [
            {
                "id": "I",
                "text": "Sürtünmesiz yatay düzlemde net kuvvet yoksa cisim durur.",
                "is_correct": False,
                "why": "ÖSYM çeldiricisi: ‘kuvvet yok = durur’. Doğrusu ivme sıfırdır; hız sıfır olmak zorunda değildir.",
            },
            {
                "id": "II",
                "text": "ivme, net kuvvetle aynı yöndedir.",
                "is_correct": True,
                "why": "Newton II: a vektörü Fnet ile aynı yöndedir.",
            },
            {
                "id": "III",
                "text": "Kütle artarsa aynı net kuvvette ivme azalır.",
                "is_correct": True,
                "why": "a = F/m; m paydada. Kütle eylemsizliktir, kuvvet değildir.",
            },
        ],
        "exams": ["yks"],
    },
    {
        "question_text": (
            "I, II ve III numaralı ifadelerden hangileri doğrudur?\n"
            "I. Asitler suda H⁺ (veya H₃O⁺) verir.\n"
            "II. Tüm bazlar OH⁻ içermek zorundadır.\n"
            "III. Nötrleşme, asit ile bazın tuz ve su vermesidir (sulu çözeltide klasik tanım)."
        ),
        "options": {
            "A": "Yalnız I",
            "B": "I ve II",
            "C": "I ve III",
            "D": "II ve III",
            "E": "I, II ve III",
        },
        "correct_answer": "C",
        "trap_explanation": (
            "II kavram yanılgısı: NH₃ bazdır ama OH⁻ taşımaz; proton alır. Arrhenius’u "
            "Brønsted ile karıştırma."
        ),
        "subject_type": "sayisal",
        "is_yks_fen": True,
        "fen_branch": "kimya",
        "misconception_tag": "Kavram Yanılgısı",
        "shortcut_tactic": "NH₃ / amin görürsen ‘OH yoksa baz değildir’ yemini çöpe at.",
        "step_by_step_solution": [
            "I doğru: Arrhenius/Brønsted asit tanımına uyar.",
            "II yanlış: Brønsted bazı proton alır; OH⁻ taşımak zorunda değildir.",
            "III doğru: klasik lise nötrleşme tanımı.",
        ],
        "premises": [
            {
                "id": "I",
                "text": "Asitler suda H⁺ (veya H₃O⁺) verir.",
                "is_correct": True,
                "why": "Arrhenius asit tanımı; TYT’de hâlâ geçerlidir.",
            },
            {
                "id": "II",
                "text": "Tüm bazlar OH⁻ içermek zorundadır.",
                "is_correct": False,
                "why": "ÖSYM çeldiricisi: baz = hidroksit. NH₃ OH⁻ içermez ama bazdır.",
            },
            {
                "id": "III",
                "text": "Nötrleşme, asit ile bazın tuz ve su vermesidir (sulu çözeltide klasik tanım).",
                "is_correct": True,
                "why": "Lise müfredatındaki klasik nötrleşme ifadesi.",
            },
        ],
        "exams": ["yks"],
    },
    {
        "question_text": (
            "I, II ve III numaralı ifadelerden hangileri doğrudur?\n"
            "I. Mitozda yavru hücrelerin kromozom sayısı ana hücreyle aynıdır.\n"
            "II. Mayoz, vücut hücrelerinde sürekli tekrarlanır.\n"
            "III. DNA eşlenmesi mitozun interfazındadır, metafazda değil."
        ),
        "options": {
            "A": "Yalnız I",
            "B": "I ve III",
            "C": "II ve III",
            "D": "Yalnız III",
            "E": "I, II ve III",
        },
        "correct_answer": "B",
        "trap_explanation": (
            "II kavram yanılgısı: mayoz eşey ana hücrelerinde olur, karaciğer hücresinde "
            "sürekli mitoz beklenir. Metafaz = dizilim, eşlenme değil."
        ),
        "subject_type": "sayisal",
        "is_yks_fen": True,
        "fen_branch": "biyoloji",
        "misconception_tag": "Kavram Yanılgısı",
        "shortcut_tactic": "Mayoz = gamet hattı. Eşlenme = S fazı / interfaz, metafaz değil.",
        "step_by_step_solution": [
            "I doğru: mitoz kromozom sayısını korur.",
            "II yanlış: mayoz eşey ana hücrelerine özgüdür, somatik hücrede sürekli olmaz.",
            "III doğru: replikasyon S fazında; metafazda kromozomlar ekvator düzlemine dizilir.",
        ],
        "premises": [
            {
                "id": "I",
                "text": "Mitozda yavru hücrelerin kromozom sayısı ana hücreyle aynıdır.",
                "is_correct": True,
                "why": "Mitoz eşit bölünmedir; 2n → 2n.",
            },
            {
                "id": "II",
                "text": "Mayoz, vücut hücrelerinde sürekli tekrarlanır.",
                "is_correct": False,
                "why": "ÖSYM çeldiricisi: her hücre bölünmesi mayoz sanmak. Mayoz gamet oluşumuna özgüdür.",
            },
            {
                "id": "III",
                "text": "DNA eşlenmesi mitozun interfazındadır, metafazda değil.",
                "is_correct": True,
                "why": "S fazı interfazdadır. Metafaz = dizilim tuzağı.",
            },
        ],
        "exams": ["yks"],
    },
]


def rank_title(rank: int) -> dict[str, str]:
    if rank == 1:
        return {"title": "Alfa Tilki", "emoji": "🦊", "badge": "fox"}
    if rank == 2:
        return {"title": "Kıdemli Tilki", "emoji": "🥈", "badge": "silver"}
    if rank == 3:
        return {"title": "Kurnaz Prens", "emoji": "🥉", "badge": "bronze"}
    return {"title": "Yavru Tilki", "emoji": "🐾", "badge": "pup"}


def parse_options(raw: str) -> dict[str, str]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def _display_name(db: Session, user_id: str) -> str:
    stats = db.get(UserStats, user_id)
    if stats and stats.display_name:
        return stats.display_name
    return alias_for(user_id)


def bank_for(exam_target: str | None) -> list[dict]:
    from app.services.exams import matches_exam

    pool = [item for item in QUESTION_BANK if matches_exam(item, exam_target)]
    return pool


def pick_from_bank(pool: list[dict], day) -> dict:
    """Çift ISO haftasında sayısal mantık; YKS'de 4. hafta diliminde Fen öncüllü tuzak."""
    week = day.isocalendar()[1]
    numerical = [q for q in pool if (q.get("subject_type") or "") == "sayisal"]
    fen = [q for q in pool if q.get("is_yks_fen") or q.get("is_yks_fen_question")]
    logic = [q for q in numerical if q not in fen]
    verbal = [q for q in pool if q not in numerical]
    if week % 2 == 0 and logic:
        bucket = logic
    elif week % 4 == 3 and fen:
        bucket = fen
    else:
        bucket = verbal or pool
    return bucket[day.toordinal() % len(bucket)]


def _apply_pick(row: DailyChallenge, pick: dict) -> None:
    from app.services.subjects import parse_premises, parse_steps

    row.subject_type = str(pick.get("subject_type") or "sozel")
    row.shortcut_tactic = str(pick.get("shortcut_tactic") or "")
    row.steps_json = json.dumps(
        parse_steps(pick.get("step_by_step_solution")), ensure_ascii=False
    )
    row.premises_json = json.dumps(parse_premises(pick.get("premises")), ensure_ascii=False)
    row.misconception_tag = str(pick.get("misconception_tag") or "")
    row.fen_branch = str(pick.get("fen_branch") or "")
    row.is_yks_fen = bool(pick.get("is_yks_fen") or pick.get("is_yks_fen_question"))


def coaching_fields(row: DailyChallenge, *, reveal: bool) -> dict:
    from app.services.subjects import parse_premises, parse_steps

    steps = parse_steps(getattr(row, "steps_json", None))
    premises = parse_premises(getattr(row, "premises_json", None))
    if not reveal:
        premises = [
            {**item, "why": "", "is_correct": False}
            for item in premises
        ]
        return {
            "subject_type": getattr(row, "subject_type", "") or "sozel",
            "is_yks_fen_question": bool(getattr(row, "is_yks_fen", False)),
            "fen_branch": getattr(row, "fen_branch", "") or "",
            "premises": premises,
        }
    return {
        "subject_type": getattr(row, "subject_type", "") or "sozel",
        "shortcut_tactic": getattr(row, "shortcut_tactic", "") or "",
        "step_by_step_solution": steps,
        "premises": premises,
        "misconception_tag": getattr(row, "misconception_tag", "") or "",
        "fen_branch": getattr(row, "fen_branch", "") or "",
        "is_yks_fen_question": bool(getattr(row, "is_yks_fen", False)),
    }


def ensure_today(db: Session, exam_target: str | None = None, user_id: str | None = None) -> DailyChallenge:
    from app.services.exams import label_for, normalize

    target = normalize(exam_target or (exam_of(db, user_id) if user_id else DEFAULT_EXAM))
    day = today_istanbul()
    row = db.scalars(
        select(DailyChallenge)
        .where(DailyChallenge.date == day)
        .where(DailyChallenge.exam_target == target)
    ).first()
    if row:
        return row
    pick = None
    try:
        from app.services.rag import compose_hunt_question

        pick = compose_hunt_question(db, target, day)
    except Exception:
        pick = None
    if pick is None:
        pool = bank_for(target)
        pick = pick_from_bank(pool, day)
    row = DailyChallenge(
        question_text=pick["question_text"],
        options=json.dumps(pick["options"], ensure_ascii=False),
        correct_answer=str(pick["correct_answer"]).strip().upper()[:1],
        trap_explanation=f"{pick['trap_explanation']} Hedef: {label_for(target)}.",
        date=day,
        exam_target=target,
    )
    _apply_pick(row, pick)
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError:
        db.rollback()
        legacy = db.scalars(
            select(DailyChallenge)
            .where(DailyChallenge.date == day)
            .where(DailyChallenge.exam_target == target)
        ).first()
        if legacy:
            return legacy
        raise


def public_challenge(row: DailyChallenge) -> dict:
    payload = {
        "id": row.id,
        "question_text": row.question_text,
        "options": parse_options(row.options),
        "date": row.date.isoformat() if row.date else None,
    }
    payload.update(coaching_fields(row, reveal=False))
    return payload


def today_state(db: Session, user_id: str | None = None) -> dict:
    challenge = ensure_today(db, user_id=user_id)
    payload = public_challenge(challenge)
    attempt = get_attempt(db, user_id, challenge.id) if user_id else None
    payload["already_attempted"] = bool(attempt)
    payload["result"] = pack_result(db, challenge, attempt, already=True) if attempt else None
    return payload


def get_attempt(db: Session, user_id: str, challenge_id: int) -> ChallengeLeaderboard | None:
    return db.scalars(
        select(ChallengeLeaderboard)
        .where(ChallengeLeaderboard.user_id == user_id)
        .where(ChallengeLeaderboard.challenge_id == challenge_id)
    ).first()


def wrong_count(db: Session, challenge_id: int) -> int:
    rows = db.scalars(
        select(ChallengeLeaderboard).where(ChallengeLeaderboard.challenge_id == challenge_id)
    ).all()
    return sum(1 for row in rows if not row.is_correct)


def wrong_message(fallen: int, title: str) -> str:
    others = max(fallen - 1, 0)
    if others == 0:
        return (
            f"Hey {title}, sazan gibi atladın! Yalnız değilsin — bugün bu yeme ilk "
            "düşen sen oldun, sürü yolda."
        )
    return (
        f"Hey {title}, sazan gibi atladın! Yalnız değilsin, bugün bu soruya "
        f"{others} kişi daha düştü."
    )


def leaderboard_entries(db: Session, challenge_id: int, limit: int = TOP_N) -> list[dict]:
    rows = db.scalars(
        select(ChallengeLeaderboard)
        .where(ChallengeLeaderboard.challenge_id == challenge_id)
        .where(ChallengeLeaderboard.is_correct.is_(True))
        .where(ChallengeLeaderboard.eligible.is_(True))
        .order_by(
            ChallengeLeaderboard.time_spent_ms.asc(),
            ChallengeLeaderboard.completed_at.asc(),
        )
    ).all()
    rows = anti_cheat.collapse_eligible(list(rows))[:limit]
    out = []
    for index, row in enumerate(rows, start=1):
        meta = rank_title(index)
        out.append(
            {
                "rank": index,
                "user_id": row.user_id,
                "display_name": _display_name(db, row.user_id),
                "time_spent_ms": row.time_spent_ms,
                "title": meta["title"],
                "emoji": meta["emoji"],
                "badge": meta["badge"],
            }
        )
    return out


def rank_for(entries: list[dict], user_id: str) -> int | None:
    for item in entries:
        if item["user_id"] == user_id:
            return int(item["rank"])
    if not entries:
        return None
    return None


def clamp_ms(value: int) -> int:
    try:
        ms = int(value)
    except (TypeError, ValueError):
        ms = anti_cheat.MIN_READING_MS
    return max(0, min(10 * 60 * 1000, ms))


def begin_hunt(
    db: Session,
    *,
    user_id: str,
    challenge_id: int | None = None,
    device_id: str = "",
    ip_hash: str = "",
) -> dict:
    challenge = (
        db.get(DailyChallenge, challenge_id) if challenge_id else ensure_today(db, user_id=user_id)
    )
    if challenge is None:
        raise KeyError("Bugünün sazan avı bulunamadı.")
    if challenge.date != today_istanbul():
        challenge = ensure_today(db, user_id=user_id)
    attempt = get_attempt(db, user_id, challenge.id)
    if attempt:
        return {
            "challenge_id": challenge.id,
            "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
            "already_attempted": True,
        }
    session = anti_cheat.start_session(
        db,
        user_id=user_id,
        challenge_id=challenge.id,
        device_id=anti_cheat.normalize_device_id(device_id),
        ip_hash=ip_hash,
    )
    return {
        "challenge_id": challenge.id,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "already_attempted": False,
    }


def submit(
    db: Session,
    *,
    user_id: str,
    chosen: str,
    challenge_id: int | None = None,
    device_id: str = "",
    ip_hash: str = "",
    identity_hash: str = "",
) -> dict:
    challenge = (
        db.get(DailyChallenge, challenge_id) if challenge_id else ensure_today(db, user_id=user_id)
    )
    if challenge is None:
        raise KeyError("Bugünün sazan avı bulunamadı.")
    if challenge.date != today_istanbul():
        raise KeyError("Bu avın süresi doldu. Bugünün yemini çek.")

    existing = get_attempt(db, user_id, challenge.id)
    if existing:
        payload = pack_result(db, challenge, existing, already=True)
        payload.update(award_hunt(db, user_id, correct=existing.is_correct, already=True))
        return payload

    session = anti_cheat.get_session(db, user_id, challenge.id)
    if session is None or session.started_at is None:
        raise ValueError("Önce avı başlat.")

    finished = anti_cheat.utcnow()
    spent = clamp_ms(anti_cheat.elapsed_ms(session.started_at, finished))
    options = parse_options(challenge.options)
    too_fast = anti_cheat.is_cheated(spent, challenge.question_text, options)

    device = anti_cheat.normalize_device_id(device_id) or session.device_id
    ip_value = ip_hash or session.ip_hash
    ident = anti_cheat.normalize_identity(identity_hash)
    if ident:
        user = get_or_create_user(db, user_id)
        if not user.identity_hash:
            user.identity_hash = ident

    anti_cheat.remember_sighting(
        db, user_id=user_id, device_id=device, ip_hash=ip_value
    )

    letter = (chosen or "").strip().upper()[:1]
    correct = letter == (challenge.correct_answer or "").strip().upper()[:1]
    cheated = bool(too_fast)
    eligible = bool(correct and not cheated)

    row = ChallengeLeaderboard(
        user_id=user_id,
        challenge_id=challenge.id,
        time_spent_ms=spent,
        is_correct=correct,
        is_suspicious=cheated,
        is_cheated=cheated,
        eligible=eligible,
        started_at=session.started_at,
        finished_at=finished,
        device_id=device,
        ip_hash=ip_value,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = get_attempt(db, user_id, challenge.id)
        if existing:
            payload = pack_result(db, challenge, existing, already=True)
            payload.update(award_hunt(db, user_id, correct=existing.is_correct, already=True))
            return payload
        raise
    db.refresh(row)
    if not correct:
        _stash_hunt_trap(db, user_id, challenge, letter)
    payload = pack_result(db, challenge, row, already=False)
    payload.update(
        award_hunt(db, user_id, correct=eligible, already=False)
    )
    return payload


def _stash_hunt_trap(db: Session, user_id: str, challenge: DailyChallenge, chosen: str) -> None:
    from types import SimpleNamespace

    from app.services.subjects import parse_premises, parse_steps
    from app.services.traps import save_wrong_trap

    try:
        save_wrong_trap(
            db,
            SimpleNamespace(
                user_id=user_id,
                question_id=f"hunt:{challenge.id}",
                question_text=challenge.question_text,
                options=parse_options(challenge.options),
                chosen=chosen,
                correct=challenge.correct_answer,
                explanation=challenge.trap_explanation,
                trap_explanation=challenge.trap_explanation,
                teacher_persona=None,
                topic=getattr(challenge, "fen_branch", "") or "Sazan Avı",
                time_spent_seconds=0,
                subject_type=getattr(challenge, "subject_type", "") or "sozel",
                shortcut_tactic=getattr(challenge, "shortcut_tactic", "") or "",
                step_by_step_solution=parse_steps(getattr(challenge, "steps_json", None)),
                premises=parse_premises(getattr(challenge, "premises_json", None)),
                misconception_tag=getattr(challenge, "misconception_tag", "") or "",
                fen_branch=getattr(challenge, "fen_branch", "") or "",
                is_yks_fen_question=bool(getattr(challenge, "is_yks_fen", False)),
            ),
        )
    except Exception:
        pass


def pack_result(
    db: Session,
    challenge: DailyChallenge,
    attempt: ChallengeLeaderboard,
    *,
    already: bool,
) -> dict:
    fallen = wrong_count(db, challenge.id)
    eligible = bool(getattr(attempt, "eligible", False))
    cheated = bool(getattr(attempt, "is_cheated", False) or getattr(attempt, "is_suspicious", False))
    board = leaderboard_entries(db, challenge.id) if eligible else []
    rank = (
        rank_for(leaderboard_entries(db, challenge.id, limit=10_000), attempt.user_id)
        if eligible
        else None
    )
    warning = None
    if cheated:
        warning = (
            "İnsan okuma hızının altında. is_cheated=True — "
            "liderlik ve ödül dışı."
        )
    return {
        "challenge_id": challenge.id,
        "is_correct": bool(attempt.is_correct),
        "already_attempted": already,
        "chosen": "",
        "time_spent_ms": attempt.time_spent_ms,
        "trap_explanation": challenge.trap_explanation if not attempt.is_correct else "",
        "wrong_count": fallen,
        "wrong_message": None if attempt.is_correct else wrong_message(fallen, address_for(db, attempt.user_id)),
        "rank": rank,
        "leaderboard": board,
        "is_suspicious": cheated,
        "is_cheated": cheated,
        "eligible": eligible,
        "suspicious_reason": warning,
        "chosen": getattr(attempt, "chosen", "") or "",
        **coaching_fields(challenge, reveal=True),
    }
