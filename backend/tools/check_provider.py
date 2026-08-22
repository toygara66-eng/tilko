"""Yapılandırılmış LLM sağlayıcısını küçük bir örnekle sınar.

Uzun bir video analizini beklemeden ayarların doğru olup olmadığını gösterir.

Kullanım (backend klasöründen):
    .\\.venv\\Scripts\\python.exe tools\\check_provider.py
    .\\.venv\\Scripts\\python.exe tools\\check_provider.py --model openai/gpt-oss-120b
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.services.llm import (  # noqa: E402
    FatalLLMError,
    generate_notes,
    generate_questions,
)

MODEL_FIELDS = {
    "openai": "openai_model",
    "gemini": "gemini_model",
    "groq": "groq_model",
    "cerebras": "cerebras_model",
    "nebius": "nebius_model",
    "openrouter": "openrouter_model",
    "huggingface": "hf_model",
    "ollama": "ollama_model",
}

ORNEK_ALTYAZI = (
    "[0] Yasama yetkisi Turkiye Buyuk Millet Meclisine aittir ve devredilemez.\n"
    "[15] Yurutme yetkisi ve gorevi Cumhurbaskani tarafindan kullanilir.\n"
    "[32] Yargi yetkisi bagimsiz ve tarafsiz mahkemelerce kullanilir.\n"
    "[48] Egemenlik kayitsiz sartsiz Milletindir.\n"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="Bu çalıştırma için modeli geçici olarak değiştirir")
    parser.add_argument("--provider", help="nebius | cerebras | groq | openrouter | gemini | huggingface | ollama")
    args = parser.parse_args()

    if args.provider:
        settings.llm_provider = args.provider
    if args.model:
        field = MODEL_FIELDS.get(settings.llm_provider)
        if not field:
            print(f"Bilinmeyen saglayici: {settings.llm_provider}")
            return 1
        setattr(settings, field, args.model)

    print(f"saglayici : {settings.llm_provider}")
    print(f"model     : {settings.active_model}")
    print(f"parca     : {settings.chunk_chars} karakter")
    print(f"soru/cagri: {settings.questions_per_call}\n")

    try:
        start = time.time()
        notes = generate_notes([ORNEK_ALTYAZI], "Anayasa")
        if isinstance(notes, tuple):
            notes, persona = notes
            print(f"persona   : {persona.get('tone')} / {persona.get('catchphrases')}")
        print(f"not sayisi: {len(notes)}  ({time.time() - start:.0f} sn)")
        if not notes:
            print("Model not uretemedi.")
            return 1

        first = notes[0]
        print(f"  baslik : {first.get('title')}")
        print(f"  detay  : {str(first.get('detail'))[:120]}...")
        print(f"  teknik : {str(first.get('mnemonic'))[:120]}")

        start = time.time()
        questions = generate_questions(notes, "Anayasa", 5)
        print(f"\nsoru sayisi: {len(questions)}  ({time.time() - start:.0f} sn)")
        if questions:
            q = questions[0]
            print(f"  soru   : {str(q.get('text'))[:120]}")
            print(f"  siklar : {len(q.get('options') or {})}  dogru: {q.get('correct')}")
        print("\nSaglayici calisiyor.")
        return 0
    except FatalLLMError as exc:
        print(f"\nDURDU: {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"\nHATA: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
