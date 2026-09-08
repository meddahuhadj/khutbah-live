"""Tests unitaires de translator.py : parsing, cache, dernière erreur — httpx mocké."""
import json

import pytest

import translator


class _Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text or json.dumps(payload or {})

    def json(self):
        return self._payload


def _gemini_ok(obj):
    return _Resp(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}}]})


def _client_returning(resp):
    """AsyncClient factice dont .post() renvoie toujours `resp`."""
    class _C:
        async def post(self, *a, **k):
            return resp
    return _C()


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setattr(translator, "API_KEY", "test-key")
    translator._cache.clear()
    translator._last_error = ""


async def test_translate_parses_and_maps_languages(monkeypatch):
    payload = {"arabic": "نص", "is_quran": True, "quran_ref": "2:255",
               "translations": [{"lang": "fr", "text": "texte"},
                                {"lang": "en", "text": "text"}]}

    class C:
        async def post(self, *a, **k):
            return _gemini_ok(payload)

    monkeypatch.setattr(translator, "_http", lambda: C())
    r = await translator.translate_segment("نص عربي", ["fr", "en"])
    assert r["translations"] == {"fr": "texte", "en": "text"}
    assert r["is_quran"] is True and r["quran_ref"] == "2:255"
    assert translator.last_error() == ""


async def test_missing_language_filled_empty(monkeypatch):
    payload = {"arabic": "x", "is_quran": False,
               "translations": [{"lang": "fr", "text": "ok"}]}
    monkeypatch.setattr(translator, "_http", lambda: _client_returning(_gemini_ok(payload)))
    r = await translator.translate_segment("x", ["fr", "de"])
    assert r["translations"]["fr"] == "ok"
    assert r["translations"]["de"] == ""


async def test_cache_hit_avoids_second_call(monkeypatch):
    n = {"c": 0}
    payload = {"arabic": "x", "is_quran": False,
               "translations": [{"lang": "fr", "text": "ok"}]}

    class C:
        async def post(self, *a, **k):
            n["c"] += 1
            return _gemini_ok(payload)

    monkeypatch.setattr(translator, "_http", lambda: C())
    await translator.translate_segment("phrase répétée", ["fr"])
    await translator.translate_segment("phrase répétée", ["fr"])
    assert n["c"] == 1
    # use_cache=False force un nouvel appel
    await translator.translate_segment("phrase répétée", ["fr"], use_cache=False)
    assert n["c"] == 2


async def test_429_sets_quota_error(monkeypatch):
    class C:
        async def post(self, *a, **k):
            return _Resp(429, {}, text="quota exceeded")

    monkeypatch.setattr(translator, "_http", lambda: C())
    monkeypatch.setattr(translator, "MAX_RETRIES", 0)
    r = await translator.translate_segment("x", ["fr"])
    assert r is None
    assert translator.last_error() == "quota"


async def test_403_sets_auth_error(monkeypatch):
    monkeypatch.setattr(translator, "MAX_RETRIES", 0)
    monkeypatch.setattr(translator, "_http", lambda: _client_returning(_Resp(403, {}, "denied")))
    assert await translator.translate_segment("x", ["fr"]) is None
    assert translator.last_error() == "auth"


async def test_no_target_langs_returns_none():
    assert await translator.translate_segment("نص", ["ar"]) is None
    assert await translator.translate_segment("", ["fr"]) is None


def test_system_prompt_is_the_real_one_not_the_fallback():
    """Garde-fou : si SYSTEM_PROMPT.md n'est pas trouvé, on tomberait sur le
    prompt court de secours — ce qui dégraderait silencieusement la qualité."""
    assert translator.SYSTEM_PROMPT != translator._FALLBACK_PROMPT
    assert len(translator.SYSTEM_PROMPT) > 800
    low = translator.SYSTEM_PROMPT.lower()
    assert "is_quran" in low and "quran_ref" in low
