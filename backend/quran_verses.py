"""
quran_verses.py -- Corpus canonique de versets (texte + traduction figee).

L'objectif : ne JAMAIS confier la traduction d'un verset coranique a un LLM.
Quand un segment est identifie comme verset (is_quran=true) avec une reference
connue (soit renvoyee par le modele, soit retrouvee via l'index local
`quran_index`), on remplace la traduction du LLM par une traduction **canonique
et figee** releve dans `data/quran_verses.json` -- plus fiable pour le contenu
religieux.

Le fichier JSON est une simple table :
    {
      "meta": { "source": "...", "licensing_note": "..." },
      "verses": {
        "1:1": { "ar": "<texte arabe exact>", "translations": { "fr": "...", "en": "..." } },
        ...
      }
    }

Les references sont au format "S:"A (eg. "2:255", "112:1", plages "112:1-4").
Ne sont remplacees QUE les langues pour lesquelles on dispose d'une traduction
canonique ; les autres langues gardent la traduction du modele.
"""

from __future__ import annotations

import json
from pathlib import Path

_FILE = Path(__file__).resolve().parent / "data" / "quran_verses.json"

_data: dict | None = None
_loaded = False


def load() -> dict:
    """Charge le corpus une seule fois (None silencieux si indisponible)."""
    global _data, _loaded
    if _loaded:
        return _data or {}
    _loaded = True
    try:
        raw = json.loads(_FILE.read_text(encoding="utf-8"))
        _data = raw if isinstance(raw, dict) else {}
    except (OSError, ValueError) as exc:
        print(f"[quran_verses] corpus indisponible: {exc!r}")
        _data = None
    return _data or {}


def available() -> bool:
    return bool(load().get("verses"))


def canonical(ref: str | None) -> dict | None:
    """Retourne {ar, translations} pour une reference 'S:'A' ou None."""
    if not ref:
        return None
    verses = load().get("verses") or {}
    # La reference peut etre une plage "S:A1-A2" : on tente la reference exacte
    # d'abord, puis on retire le suffixe de plage.
    for probe in (ref, ref.split("-")[0]):
        hit = verses.get(probe)
        if hit is not None:
            return hit
    return None


def apply(rec: dict) -> bool:
    """Remplace, en place, les traductions d'un enregistrement de segment par le
    corpus canonique pour les langues couvertes. Retourne True si un remplacement
    a eu lieu (le diffuseur peut alors badger le verset 'fidele')."""
    ref = rec.get("quran_ref")
    if not rec.get("is_quran") or not ref:
        return False
    got = canonical(ref)
    if not got:
        return False
    translated = got.get("translations") or {}
    if not translated:
        return False
    rec.setdefault("translations", {})
    for lang, text in translated.items():
        if text:  # ne jamais ecraser une langue par du vide
            rec["translations"][lang] = text
    if got.get("ar"):
        rec["arabic"] = got["ar"]  # texte arabe exec ait aussi fige
    return True
