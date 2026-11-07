"""Altyazı doğrulama (grounding) ve jeton kaydı için çevrimiçi servis gerektirmeyen testler."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.pop("DATABASE_URL", None)  # boş = yerel SQLite
os.environ.setdefault("DATABASE_PATH", "/tmp/tilko_test.db")

from app.services import llm  # noqa: E402
from app.services.token_usage import _estimate_usd, infer_provider  # noqa: E402

TRANSCRIPT = (
    "Anayasa mahkemesi kararları kesin ve bağlayıcıdır. Anayasa mahkemesi on beş üyeden oluşur. "
    "Üyelerin görev süresi on iki yıldır ve yeniden seçilemezler. Cumhurbaşkanı üyelerin üçünü seçer. "
    "Kanun hükmünde kararnameler yürütme tarafından çıkarılır. Bireysel başvuru hakkı iki bin on iki "
    "yılında anayasal güvenceye kavuşmuştur. Başvuru yolu tükenmeden bireysel başvuru yapılamaz."
)


def _note(title, detail, points=(), quote=""):
    return {"title": title, "detail": detail, "key_points": list(points), "quote": quote}


def test_faithful_note_with_quote_is_kept():
    note = _note(
        "Anayasa Mahkemesi üyeleri",
        "Anayasa mahkemesi on beş üyeden oluşur ve üyelerin görev süresi on iki yıldır.",
        ["On beş üye", "Görev süresi on iki yıl", "Yeniden seçilemezler"],
        quote="Anayasa mahkemesi on beş üyeden oluşur",
    )
    assert llm._ground_notes([note], TRANSCRIPT)


def test_hallucinated_note_on_other_topic_is_dropped():
    note = _note(
        "Osmanlı'da Tanzimat dönemi",
        "Tanzimat fermanı ile birlikte padişahın yetkileri sınırlandırılmış ve eyaletlerde "
        "valilik sistemi yeniden düzenlenmiştir. Islahat fermanı gayrimüslimlere haklar tanımıştır.",
        ["Tanzimat fermanı", "Islahat fermanı", "Eyalet düzeni"],
    )
    assert llm._ground_notes([note], TRANSCRIPT) == []


def test_partially_off_topic_note_is_dropped():
    # Konu kelimeleri ortak ama içeriğin çoğu altyazıda yok.
    note = _note(
        "Anayasa mahkemesi ve idari yargı",
        "Anayasa mahkemesi dışında Danıştay idari davaları görür; Sayıştay kamu harcamalarını "
        "denetler, Yargıtay ise adli yargının en üst mercii olarak temyiz incelemesi yapar.",
        ["Danıştay idari yargı", "Sayıştay denetim", "Yargıtay temyiz", "Uyuşmazlık mahkemesi"],
    )
    assert llm._ground_notes([note], TRANSCRIPT) == []


def test_support_ratio_is_suffix_tolerant():
    stems = llm._stems(llm._content_tokens(TRANSCRIPT))
    common, ratio = llm._support_ratio("Anayasası mahkemesinin üyelerinin görevleri", stems)
    assert common >= 2 and ratio > 0.5


def test_question_grounded_vs_ungrounded():
    good = {
        "text": "Anayasa mahkemesi üyelerinin görev süresi kaç yıldır?",
        "explanation": "Üyelerin görev süresi on iki yıldır ve yeniden seçilemezler.",
        "options": {"A": "6", "B": "12", "C": "9", "D": "4"},
    }
    bad = {
        "text": "Tanzimat fermanı hangi padişah döneminde ilan edilmiştir?",
        "explanation": "Tanzimat fermanı Abdülmecid döneminde Gülhane Hattı Hümayunu ile ilan edildi.",
        "options": {"A": "II. Mahmut", "B": "Abdülmecid", "C": "Abdülaziz", "D": "II. Abdülhamid"},
    }
    kept = llm._ground_questions([good, bad], TRANSCRIPT)
    assert kept == [good]


def test_no_grounded_questions_returns_empty_not_all():
    bad = {
        "text": "Tanzimat fermanı hangi padişah döneminde ilan edilmiştir?",
        "explanation": "Gülhane Hattı Hümayunu Abdülmecid döneminde ilan edildi.",
        "options": {"A": "x", "B": "y"},
    }
    assert llm._ground_questions([bad], TRANSCRIPT) == []


def test_calculation_questions_are_not_dropped():
    fen = {
        "text": "2x + 3 = 11 ise x kaçtır?",
        "explanation": "2x = 8, x = 4",
        "options": {"A": "2", "B": "4"},
        "is_yks_fen_question": True,
    }
    assert llm._ground_questions([fen], TRANSCRIPT) == [fen]


def test_infer_provider_and_price():
    assert infer_provider("gemini-2.5-flash-lite") == "gemini"
    assert infer_provider("llama-3.1-8b-instant") == "groq"
    assert abs(_estimate_usd("gemini-2.5-flash-lite", 1_000_000, 1_000_000) - 0.50) < 1e-9
    assert _estimate_usd("llama-3.1-8b-instant", 10**6, 10**6) == 0.0
