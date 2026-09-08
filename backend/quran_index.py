"""
quran_index.py — Repli de detection de reference coranique.

Quand Gemini renvoie `is_quran = true` mais `quran_ref = null`, on cherche le
segment arabe dans un index local du texte coranique (data/quran_index.json,
texte sans diacritiques, ~715 Kio) et on renvoie "sourate:verset" si on le
retrouve. 100 % hors-ligne, aucun appel reseau a l'execution.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

_INDEX_PATH = Path(__file__).resolve().parent / "data" / "quran_index.json"

# Harakat, petites lettres sur/sous, signes coraniques, tatwil (kashida).
_DIAC = re.compile(
    "[ؐ-ًؚ-ٰٟۖ-ۜ۟-ۨ"
    "۪-ۭ࣓-ࣿـ]"
)
# Ne garder que les lettres arabes de base U+0621..U+064A.
_NOT_LETTER = re.compile("[^ء-ي]")

_refs: list[str] = []
_norm: list[str] = []
_loaded = False


def normalize(s: str) -> str:
    """Retire harakat / tatwil, unifie alif / ya / ta-marbuta, garde les lettres seules."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = _DIAC.sub("", s)
    s = (
        s.replace("آ", "ا")  # alif madda   -> alif
        .replace("أ", "ا")   # alif hamza a. -> alif
        .replace("إ", "ا")   # alif hamza b. -> alif
        .replace("ٱ", "ا")   # alif wasla    -> alif
        .replace("ى", "ي")   # alif maqsura  -> ya
        .replace("ئ", "ي")   # ya hamza      -> ya
        .replace("ة", "ه")   # ta marbuta    -> ha
        .replace("ؤ", "و")   # waw hamza     -> waw
    )
    return _NOT_LETTER.sub("", s)


def _load() -> bool:
    global _loaded, _refs, _norm
    if _loaded:
        return bool(_refs)
    _loaded = True
    try:
        data = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
        _refs = data["refs"]
        _norm = data["norm"]
        if len(_refs) != len(_norm) or not _refs:
            _refs, _norm = [], []
    except (OSError, ValueError, KeyError) as exc:
        print(f"[quran_index] index indisponible: {exc!r}")
        _refs, _norm = [], []
    return bool(_refs)


def available() -> bool:
    return _load()


def _consecutive_range(hits: list[int]) -> str | None:
    if not hits:
        return None
    if len(hits) == 1:
        return _refs[hits[0]]
    first_s, first_a = _refs[hits[0]].split(":")
    last_s, last_a = _refs[hits[-1]].split(":")
    if first_s == last_s and hits[-1] - hits[0] == len(hits) - 1:
        return f"{first_s}:{first_a}-{last_a}"
    return _refs[hits[0]]


def find_ref(arabic_text: str, min_len: int = 8) -> str | None:
    """Cherche `arabic_text` dans le Coran. Renvoie 'S:A', 'S:A1-A2' ou None.

    Confiance :
      - segment court (< 20 lettres) : il doit couvrir >= 55 % du verset trouve
        (evite de matcher un fragment minuscule au milieu d'un long verset) ;
      - segment tres court (< min_len) : rejete.
    """
    if not _load():
        return None
    seg = normalize(arabic_text)
    if len(seg) < min_len:
        return None

    # 1) Le segment est une portion d'un verset -> plus court verset qui le contient.
    best_i, best_len = -1, 10 ** 9
    for i, ver in enumerate(_norm):
        if len(ver) >= len(seg) and seg in ver and len(ver) < best_len:
            best_i, best_len = i, len(ver)
    if best_i >= 0:
        if len(seg) >= 20 or len(seg) / best_len >= 0.55:
            return _refs[best_i]

    # 2) Un ou plusieurs versets entiers sont contenus dans le segment.
    hits = [i for i, ver in enumerate(_norm) if len(ver) >= min_len and ver in seg]
    if hits:
        return _consecutive_range(hits)

    return None
