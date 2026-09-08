"""
translator.py — Pont vers l'API Google Gemini.

Deux fonctions publiques :
  - translate_segment(arabic_text, target_langs)  -> dict | None
  - transcribe_audio(audio_bytes, mime_type)      -> str  | None

Toutes deux sont asynchrones, tolérantes aux pannes (retour None en cas d'échec →
le backend passe alors en mode dégradé : il diffuse l'arabe sans traduction), et
mutualisent un petit cache en mémoire (l'imam répète souvent les mêmes formules).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import OrderedDict
from pathlib import Path

import httpx

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
_BASE = "https://generativelanguage.googleapis.com/v1beta"

REQUEST_TIMEOUT = 20.0      # secondes
MAX_RETRIES = 1             # 1 tentative + 1 réessai
CACHE_SIZE = 256
CACHE_TTL = 60 * 30         # 30 min

# --------------------------------------------------------------------------- #
# Prompt système spécialisé (chargé depuis SYSTEM_PROMPT.md, repli inline)
# --------------------------------------------------------------------------- #

_FALLBACK_PROMPT = (
    "Tu es un traducteur spécialisé dans le prêche musulman (khutbah). Tu traduis "
    "fidèlement, sobrement et sans interprétation personnelle, segment par segment, "
    "de l'arabe vers les langues cibles demandées. Conserve les termes islamiques "
    "translittérés d'usage (salât, taqwa, sunnah...) avec au besoin une glose courte "
    "entre parenthèses à la première occurrence. « Allah » reste « Allah ». Rends les "
    "formules d'eulogie. Si le segment cite le Coran, mets is_quran=true et donne "
    "quran_ref si tu la reconnais avec certitude, sinon null ; traduis alors au plus "
    "près du texte. Ne complète jamais une phrase coupée. Réponds UNIQUEMENT en JSON "
    "conforme au schéma, une entrée par langue demandée, aucune langue omise."
)


def _load_system_prompt() -> str:
    # SYSTEM_PROMPT.md est à la racine du dépôt (un niveau au-dessus de backend/).
    for candidate in (
        Path(__file__).resolve().parent.parent / "SYSTEM_PROMPT.md",
        Path(__file__).resolve().parent / "SYSTEM_PROMPT.md",
    ):
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        # On ne garde que ce qui suit le premier séparateur horizontal "---".
        marker = "\n---\n"
        idx = text.find(marker)
        body = text[idx + len(marker):] if idx != -1 else text
        body = body.strip()
        if len(body) > 200:
            return body
    return _FALLBACK_PROMPT


SYSTEM_PROMPT = _load_system_prompt()

# --------------------------------------------------------------------------- #
# Schéma de réponse imposé à Gemini (JSON structuré)
# --------------------------------------------------------------------------- #

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "arabic": {"type": "string"},
        "is_quran": {"type": "boolean"},
        "quran_ref": {"type": "string", "nullable": True},
        "is_hadith": {"type": "boolean"},
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "lang": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["lang", "text"],
            },
        },
    },
    "required": ["arabic", "is_quran", "translations"],
}

# --------------------------------------------------------------------------- #
# Cache LRU + TTL très simple
# --------------------------------------------------------------------------- #

_cache: "OrderedDict[str, tuple[float, dict]]" = OrderedDict()


def _cache_get(key: str):
    hit = _cache.get(key)
    if not hit:
        return None
    ts, value = hit
    if time.time() - ts > CACHE_TTL:
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)
    return value


def _cache_put(key: str, value: dict):
    _cache[key] = (time.time(), value)
    _cache.move_to_end(key)
    while len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)


# --------------------------------------------------------------------------- #
# Appels HTTP
# --------------------------------------------------------------------------- #

_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
    return _client


async def aclose():
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def has_api_key() -> bool:
    return bool(API_KEY)


# Dernière raison d'échec Gemini, exposée au backend pour informer l'opérateur.
#   "" = ok/aucune · "no_key" · "quota" (429) · "auth" (401/403) · "server" (5xx)
#   "network" · "bad_response"
_last_error = ""


def last_error() -> str:
    return _last_error


async def _post_generate(payload: dict) -> dict | None:
    global _last_error
    if not API_KEY:
        _last_error = "no_key"
        return None
    url = f"{_BASE}/models/{MODEL}:generateContent"
    params = {"key": API_KEY}
    last_exc = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = await _http().post(url, params=params, json=payload)
            if r.status_code == 200:
                _last_error = ""
                return r.json()
            # 429 / 5xx : on réessaie une fois après une courte pause.
            if r.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                await asyncio.sleep(0.8 * (attempt + 1))
                continue
            _last_error = {401: "auth", 403: "auth", 429: "quota"}.get(
                r.status_code, "server" if r.status_code >= 500 else "bad_response"
            )
            print(f"[gemini] HTTP {r.status_code} ({_last_error}): {r.text[:400]}")
            return None
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:  # noqa: PERF203
            last_exc = exc
            if attempt < MAX_RETRIES:
                await asyncio.sleep(0.6 * (attempt + 1))
                continue
    _last_error = "network"
    print(f"[gemini] échec réseau: {last_exc!r}")
    return None


def _extract_text(resp: dict) -> str | None:
    try:
        parts = resp["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, TypeError):
        return None


# --------------------------------------------------------------------------- #
# Traduction d'un segment
# --------------------------------------------------------------------------- #

async def translate_segment(
    arabic_text: str,
    target_langs: list[str],
    glossary: str = "",
    *,
    use_cache: bool = True,
) -> dict | None:
    """
    Traduit `arabic_text` vers toutes les langues de `target_langs` en un seul appel.

    - `glossary` : notes propres à la mosquée (noms, termes locaux, translittérations
      imposées) injectées dans le prompt. Fait partie de la clé de cache.
    - `use_cache=False` : force un nouvel appel (utilisé pour une correction manuelle).

    Retourne un dict :
      {
        "arabic": str,
        "is_quran": bool,
        "quran_ref": str | None,
        "is_hadith": bool,
        "translations": { "fr": "...", "en": "...", ... }
      }
    ou None en cas d'échec (mode dégradé côté appelant).
    """
    arabic_text = (arabic_text or "").strip()
    glossary = (glossary or "").strip()[:4000]
    langs = [l for l in dict.fromkeys(target_langs) if l and l != "ar"]
    if not arabic_text or not langs:
        return None

    cache_key = arabic_text + "\x1f" + ",".join(sorted(langs)) + "\x1f" + glossary
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    glossary_block = (
        ("GLOSSAIRE DE LA MOSQUÉE (à respecter strictement pour les noms propres, "
         "titres et translittérations) :\n" + glossary + "\n\n") if glossary else ""
    )
    user_msg = (
        glossary_block
        + "Langues cibles (codes) : " + ", ".join(langs) + ".\n"
        "Traduis le segment de khutbah suivant (arabe). Fournis une entrée par langue, "
        "dans cet ordre, sans en omettre aucune.\n\n"
        "SEGMENT :\n" + arabic_text
    )

    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.9,
            "candidateCount": 1,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
            "responseSchema": _RESPONSE_SCHEMA,
        },
        # On laisse Gemini être permissif : contenu religieux cité, pas de blocage.
        "safetySettings": [
            {"category": c, "threshold": "BLOCK_NONE"}
            for c in (
                "HARM_CATEGORY_HARASSMENT",
                "HARM_CATEGORY_HATE_SPEECH",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "HARM_CATEGORY_DANGEROUS_CONTENT",
            )
        ],
    }

    resp = await _post_generate(payload)
    if resp is None:
        return None

    raw = _extract_text(resp)
    if not raw:
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Dernier recours : isoler la première accolade équilibrée.
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1:
            return None
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None

    items = data.get("translations") or []
    tmap: dict[str, str] = {}
    for it in items:
        code = str(it.get("lang", "")).strip()
        txt = str(it.get("text", "")).strip()
        if code:
            tmap[code] = txt
    # Complète les langues manquantes par une chaîne vide (mieux que rien).
    for l in langs:
        tmap.setdefault(l, "")

    result = {
        "arabic": str(data.get("arabic") or arabic_text).strip(),
        "is_quran": bool(data.get("is_quran")),
        "quran_ref": (data.get("quran_ref") or None),
        "is_hadith": bool(data.get("is_hadith")),
        "translations": tmap,
    }
    _cache_put(cache_key, result)
    return result


# --------------------------------------------------------------------------- #
# Transcription audio (chemin de repli, non-Chrome / STT navigateur indisponible)
# --------------------------------------------------------------------------- #

_STT_INSTRUCTION = (
    "Transcris fidèlement cet extrait audio d'un prêche en ARABE. "
    "Rends UNIQUEMENT le texte arabe prononcé, sans traduction, sans ponctuation "
    "superflue, sans commentaire, sans guillemets. Si rien d'intelligible n'est "
    "prononcé, réponds par une chaîne vide."
)


async def transcribe_audio(audio_bytes: bytes, mime_type: str) -> str | None:
    """Transcrit un chunk audio arabe via Gemini. Retourne le texte arabe ou None."""
    if not API_KEY or not audio_bytes:
        return None
    import base64

    b64 = base64.b64encode(audio_bytes).decode("ascii")
    # Gemini accepte les mimes audio/*; on normalise les variantes courantes.
    mt = (mime_type or "audio/webm").split(";")[0].strip() or "audio/webm"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": _STT_INSTRUCTION},
                    {"inlineData": {"mimeType": mt, "data": b64}},
                ],
            }
        ],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 1024},
    }
    resp = await _post_generate(payload)
    if resp is None:
        return None
    text = _extract_text(resp) or ""
    return text.strip()
