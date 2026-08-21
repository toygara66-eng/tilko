"""Hoca üslubu klonlama — yalnızca metin; ses/audio yok."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TeacherPersona(BaseModel):
    catchphrases: list[str] = Field(default_factory=list)
    tone: str = "öğretici, net"


PERSONA_INJECTION_RULE = (
    "Çeldirici açıklamasını KESİNLİKLE videodaki hocanın tespit edilen ses tonu "
    "ve favori kelimeleriyle yaz. Bir robot gibi değil, sanki o hoca öğrencinin "
    "defterine kırmızı kalemle not düşüyormuş gibi samimi ve otoriter bir metin üret. "
    "Ses veya audio yok; sadece yazılı dönüt."
)


def parse_persona(raw: object) -> TeacherPersona:
    if isinstance(raw, TeacherPersona):
        return raw
    if not isinstance(raw, dict):
        return TeacherPersona()
    phrases = [
        str(item).strip()
        for item in (raw.get("catchphrases") or [])
        if str(item).strip()
    ]
    tone = str(raw.get("tone") or "").strip() or "öğretici, net"
    return TeacherPersona(catchphrases=phrases[:12], tone=tone[:120])


def merge_personas(items: list[object]) -> TeacherPersona:
    phrases: list[str] = []
    seen: set[str] = set()
    tones: list[str] = []
    for item in items:
        persona = parse_persona(item)
        for phrase in persona.catchphrases:
            key = phrase.lower()
            if key in seen:
                continue
            seen.add(key)
            phrases.append(phrase)
        if persona.tone and persona.tone not in tones:
            tones.append(persona.tone)
    return TeacherPersona(
        catchphrases=phrases[:12],
        tone=tones[0] if tones else "öğretici, net",
    )


def persona_system_block(persona: TeacherPersona | dict | None) -> str:
    parsed = parse_persona(persona or {})
    phrases = ", ".join(parsed.catchphrases) or "doğal, samimi hitaplar"
    return (
        "ZORUNLU KURAL — Hoca kişiliği (Persona Matching):\n"
        f"- Ton: {parsed.tone}\n"
        f"- Favori kelimeler / hitaplar: {phrases}\n"
        f"- {PERSONA_INJECTION_RULE}\n"
        "- Öğrenciye senli hitap et. Ezber cümle ve 'bu kavram önemlidir' kalıbı yasak."
    )


def style_trap_explanation(
    *,
    persona: TeacherPersona | dict | None,
    question_text: str,
    chosen: str,
    correct: str,
    explanation: str,
    trap_explanation: str = "",
    exam_target: str | None = None,
) -> str:
    """Yanlış cevap için kırmızı kalem notu — hocanın üslubuyla."""
    from app.services.llm import _chat
    from app.services.exams import label_for, prompt_block

    parsed = parse_persona(persona or {})
    seed = (trap_explanation or explanation or "").strip()
    try:
        answer = _chat(
            (
                "Sen videodaki hocanın üslubunu klonlayan bir yazı öğretmenisin. "
                "Ses/audio yok. Sadece kısa yazılı dönüt.\n\n"
                + prompt_block(exam_target)
                + "\n"
                + persona_system_block(parsed)
                + "\nÇıktı SADECE geçerli JSON: {\"trap_explanation\": \"...\"}."
            ),
            (
                f"Hedef sınav: {label_for(exam_target)}\n"
                f"Soru: {question_text}\n"
                f"Öğrenci şıkkı: {chosen or '?'}\n"
                f"Doğru şık: {correct or '?'}\n"
                f"Ham açıklama: {seed or 'yok'}\n\n"
                "Öğrencinin defterine 2-4 cümlelik kırmızı kalem notu yaz. "
                "Hocanın hitaplarını (varsa) doğal kullan. JSON: "
                '{"trap_explanation": "..."}'
            ),
            temperature=0.55,
            task="trap_explanation",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Hoca notu üretilemedi, ham metin kullanılacak: %s", exc)
        return seed
    styled = str(answer.get("trap_explanation") or answer.get("text") or "").strip()
    return styled or seed


def craft_shortcut_tactic(
    *,
    question_text: str,
    chosen: str,
    correct: str,
    explanation: str,
    exam_target: str | None = None,
    steps: list[str] | None = None,
) -> str:
    """Sayısal yanlışta pratik çözüm taktiği (kısa yol)."""
    from app.services.exams import prompt_block
    from app.services.llm import complete_json

    seed_steps = "\n".join(f"- {line}" for line in (steps or [])[:6])
    try:
        answer = complete_json(
            "Sen sayısal mantık koçusun. Öğrenciye 1-2 cümlelik pratik kısa yol yaz. "
            "Ezber slogan yok. Çıktı SADECE geçerli JSON.",
            f"""{prompt_block(exam_target)}
Soru: {question_text}
Öğrenci şıkkı: {chosen}
Doğru şık: {correct}
Açıklama: {explanation}
Adımlar:
{seed_steps or "(yok)"}

Çıktı: {{"shortcut_tactic": "sınavda 20 saniyede kullanılacak pratik kısa yol"}}
""",
            task="shortcut_tactic",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Pratik taktik üretilemedi: %s", exc)
        return ""
    return str(answer.get("shortcut_tactic") or answer.get("text") or "").strip()
