"""
live_translate.py — Traduction vocale en flux continu via Gemini Live API.

Le diffuseur capture le micro dans le navigateur et envoie du **PCM brut 16 kHz
mono (16 bits, little-endian)** au serveur. Le serveur ouvre **une session Gemini
Live par langue cible** (`translationConfig`) et relaie le flux audio. Gemini
renvoie, quasiment en temps réel, le **texte traduit** (output audio
transcription) et la **transcription source** (input transcription).

FOURNISSEUR : Gemini uniquement (modèle dédié ``gemini-3.5-live-translate-preview``).
Chaque session = une langue cible (le modèle ne traduit que vers UNE langue).
Repli automatique : si une session Live échoue à démarrer, le chemin segmenté
existant (STT → traduction germini/…) prend le relais pour cette langue.

Configuration (.env) :
  LIVE_ENABLED     ("1" par défaut)  active le mode Live
  LIVE_MODEL       (défaut gemini-3.5-live-translate-preview)
  LIVE_MAX_LANGS   (défaut 4)   nb max de sessions Live simultanées par room
  LIVE_SETUP_TMO   (défaut 12)  secondes pour attendre setupComplete

API publique :
  - live_enabled()                     -> bool
  - live_model() / live_max_langs()    -> config
  - LiveTranslateSession(api_key, target_lang, on_event, *, model)
      async start()   -> bool   (connexion + setup + attente setupComplete)
      async send_audio(pcm_bytes)
      async stop()
"""

from __future__ import annotations

import asyncio
import json
import os
import time

import websockets

_LIVE_BASE = (
    "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage."
    "v1beta.GenerativeService.BidiGenerateContent"
)
_connect = websockets.connect   # point de branche (mocké dans les tests)

LIVE_ENABLED = os.getenv("LIVE_ENABLED", "1") == "1"
LIVE_MODEL = os.getenv("LIVE_MODEL", "gemini-3.5-live-translate-preview").strip()
LIVE_MAX_LANGS = int(os.getenv("LIVE_MAX_LANGS", "4"))
LIVE_SETUP_TMO = float(os.getenv("LIVE_SETUP_TMO", "12"))
LIVE_CONNECT_RETRIES = int(os.getenv("LIVE_CONNECT_RETRIES", "2"))
LIVE_PING_INTERVAL = 15.0   # heartbeat applicatif (pas de proxy sûr)


class LiveTranslateSession:
    """Une session Live vers Gemini pour UNE langue cible.

    `on_event(event)` est appelé avec des dicts :
      {"type": "ready"}                                  connexion prête (audio accepté)
      {"type": "transcript", "text", "final"}            transcription source (arabe)
      {"type": "translation", "text", "final"}           texte traduit pour target_lang
      {"type": "error", "reason"}                        échec (quota/auth/réseau/…)
      {"type": "closed"}                                 session fermée (retry épuisé)
    """

    def __init__(self, api_key: str, target_lang: str, on_event,
                 *, model: str | None = None):
        self.api_key = api_key
        self.target_lang = target_lang
        self.model = model or LIVE_MODEL
        self._on_event = on_event
        self._ws: object | None = None
        self._ready = asyncio.Event()
        self._closed = False
        self._send_lock = asyncio.Lock()
        self._listen_task: asyncio.Task | None = None
        self.started_at = time.time()

    def _on(self, event: dict) -> None:
        if not self._closed or event["type"] in ("error", "closed"):
            try:
                self._on_event(event)
            except Exception as exc:  # le callback ne doit jamais tuer la boucle
                print(f"[live {self.target_lang}] callback: {exc!r}")

    @property
    def is_active(self) -> bool:
        return not self._closed and self._ws is not None and self._ready.is_set()

    def _url(self) -> str:
        return f"{_LIVE_BASE}?key={self.api_key}"

    def _setup(self) -> dict:
        return {
            "setup": {
                "model": f"models/{self.model}",
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "translationConfig": {
                        "targetLanguageCode": self.target_lang,
                        "echoTargetLanguage": False,
                    },
                },
                "inputAudioTranscription": {},
                "outputAudioTranscription": {},
            }
        }

    async def start(self) -> bool:
        """Connecte, envoie le setup et attend ``setupComplete``. True si prêt."""
        attempt = 0
        while not self._closed and attempt < LIVE_CONNECT_RETRIES + 1:
            attempt += 1
            self._ready.clear()
            try:
                ws = await _connect(
                    self._url(),
                    ping_interval=LIVE_PING_INTERVAL,
                    close_timeout=3,
                    open_timeout=10,
                )
            except Exception as exc:
                print(f"[live {self.target_lang}] connect #{attempt}: {exc!r}")
                await self._backoff(attempt)
                continue

            self._ws = ws
            try:
                await ws.send(json.dumps(self._setup(), ensure_ascii=False))
            except Exception as exc:
                print(f"[live {self.target_lang}] send setup #{attempt}: {exc!r}")
                await self._cleanup()
                await self._backoff(attempt)
                continue

            self._listen_task = asyncio.create_task(self._listen(ws))
            try:
                await asyncio.wait_for(self._ready.wait(), timeout=LIVE_SETUP_TMO)
            except asyncio.TimeoutError:
                print(f"[live {self.target_lang}] setup timeout #{attempt}")
                await self.stop()
                await self._backoff(attempt)
                continue
            self._on({"type": "ready"})
            return True
        self._on({"type": "error", "reason": "live_no_session"})
        return False

    async def _backoff(self, attempt: int) -> None:
        await asyncio.sleep(min(1.5 * attempt, 3.0))

    async def _listen(self, ws) -> None:
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except (ValueError, json.JSONDecodeError):
                    continue
                self._handle_message(msg)
        except Exception as exc:
            print(f"[live {self.target_lang}] listen: {exc!r}")
        finally:
            await self._cleanup()
            self._on({"type": "closed"})

    def _handle_message(self, msg: dict) -> None:
        if "setupComplete" in msg:
            self._ready.set()
            return
        if "serverContent" in msg:
            sc = msg["serverContent"] or {}
            it = sc.get("inputTranscription") or {}
            if it.get("text"):
                self._on({"type": "transcript", "text": it["text"], "final": True})
            ot = sc.get("outputTranscription") or {}
            if ot.get("text"):
                self._on({"type": "translation", "text": ot["text"], "final": True})
            mt = sc.get("modelTurn") or {}
            # modelTurn.text fait souvent doublon avec outputTranscription : ne
            # réémettre que s'il apporte un texte différent.
            for part in mt.get("parts", []) or []:
                if part.get("text") and part["text"] != ot.get("text"):
                    self._on({"type": "translation", "text": part["text"], "final": True})
            return
        if "goAway" in msg:
            reason = (msg.get("goAway") or {}).get("reason", "unknown")
            print(f"[live {self.target_lang}] goAway: {reason}")
            return
        if "error" in msg:
            err = msg["error"]
            reason = (err or {}).get("status") or (err or {}).get("message") or "unknown"
            print(f"[live {self.target_lang}] error: {reason}")
            self._on({"type": "error", "reason": reason})

    async def send_audio(self, pcm_bytes: bytes) -> bool:
        if not self.is_active or not pcm_bytes:
            return False
        payload = {
            "realtimeInput": {
                "audio": {
                    "mimeType": "audio/pcm;rate=16000",
                    "data": _b64(pcm_bytes),
                }
            }
        }
        async with self._send_lock:
            try:
                await self._ws.send(json.dumps(payload, ensure_ascii=False))
            except Exception as exc:
                print(f"[live {self.target_lang}] send audio: {exc!r}")
                return False
        return True

    async def stop(self) -> None:
        await self._cleanup()

    async def _cleanup(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass


def _b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode("ascii")


def live_enabled(has_any_key: bool = True) -> bool:
    return bool(LIVE_ENABLED and has_any_key)


def live_model() -> str:
    return LIVE_MODEL


def live_max_langs() -> int:
    return max(1, LIVE_MAX_LANGS)