"""
main.py — Backend FastAPI + WebSocket pour la traduction en direct du prêche (khutbah).

Lancement :
    cd backend
    pip install -r requirements.txt
    cp .env.example .env        # puis renseigner GEMINI_API_KEY
    python main.py              # ou : uvicorn main:app --host 0.0.0.0 --port 8000

Vues servies :
    GET /                       -> frontend PWA (un seul fichier ../frontend/index.html)
    GET /?s=CODE                -> auditeur pré-rempli
Endpoints REST :
    POST /api/session           -> crée une session { code, broadcaster_token, join_url }
    GET  /api/session/{code}    -> état d'une session
    GET  /api/session/{code}/qr.png  -> QR code (image PNG) vers la page auditeur
    GET  /api/languages         -> langues supportées
    GET  /healthz
WebSocket :
    /ws/broadcast/{code}?token=...   -> diffuseur (un seul par session)
    /ws/listen/{code}?lang=fr        -> auditeur (des centaines possibles)
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import secrets
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

import translator

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

FRONTEND_DIR = (Path(__file__).resolve().parent.parent / "frontend")
INDEX_HTML = FRONTEND_DIR / "index.html"

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
DEFAULT_TARGET_LANGS = [
    x.strip() for x in os.getenv("DEFAULT_TARGET_LANGS", "").split(",") if x.strip()
]
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "40"))
MAX_LISTENERS = int(os.getenv("MAX_LISTENERS", "1500"))
MAX_AUDIO_BYTES = int(os.getenv("MAX_AUDIO_BYTES", "2000000"))
ALLOW_NO_API_KEY = os.getenv("ALLOW_NO_API_KEY", "1") == "1"
SESSION_TTL = 60 * 60 * 12  # 12 h sans activité -> purge

# Langues proposées par l'interface. `ar` = flux original sans traduction.
SUPPORTED_LANGUAGES: dict[str, str] = {
    "ar": "العربية (original)",
    "fr": "Français",
    "en": "English",
    "nl": "Nederlands",
    "darija": "Darija — الدارجة",
    "tr": "Türkçe",
    "ur": "اردو",
    "es": "Español",
    "de": "Deutsch",
    "wo": "Wolof",
    "bn": "বাংলা",
    "ha": "Hausa",
}

# --------------------------------------------------------------------------- #
# Modèle de session (Room)
# --------------------------------------------------------------------------- #


def _gen_code(n: int = 6) -> str:
    # Sans caractères ambigus (0/O, 1/I).
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(n))


class Room:
    def __init__(self, code: str):
        self.code = code
        self.token = secrets.token_urlsafe(18)
        self.created_at = time.time()
        self.last_activity = time.time()
        self.status = "idle"  # idle | live | paused | stopped
        self.broadcaster: WebSocket | None = None
        # lang -> set[WebSocket]
        self.listeners: dict[str, set[WebSocket]] = {}
        self.ws_lang: dict[WebSocket, str] = {}
        self.seq = 0
        self.history: deque[dict] = deque(maxlen=MAX_HISTORY)
        self.audio_source_level = 0.0
        self._lock = asyncio.Lock()
        # Personnalisation communautaire (renseignée à la création de session).
        self.glossary: str = ""
        self.mosque_name: str = ""
        self.default_langs: list[str] = list(DEFAULT_TARGET_LANGS)

    # --- comptage ------------------------------------------------------------
    @property
    def listener_count(self) -> int:
        return sum(len(s) for s in self.listeners.values())

    def lang_breakdown(self) -> dict[str, int]:
        return {k: len(v) for k, v in self.listeners.items() if v}

    def active_target_langs(self) -> list[str]:
        langs = {l for l in self.listeners if self.listeners[l] and l != "ar"}
        langs.update(self.default_langs)
        langs.discard("ar")
        return sorted(langs)

    def touch(self):
        self.last_activity = time.time()

    # --- envoi -------------------------------------------------------------
    async def send_to(self, ws: WebSocket, payload: dict):
        try:
            await ws.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception:
            await self.drop_listener(ws)

    async def broadcast_lang(self, lang: str, payload: dict):
        for ws in list(self.listeners.get(lang, ())):
            await self.send_to(ws, payload)

    async def broadcast_all(self, payload: dict):
        for lang in list(self.listeners.keys()):
            await self.broadcast_lang(lang, payload)

    async def notify_broadcaster(self, payload: dict):
        if self.broadcaster is not None:
            try:
                await self.broadcaster.send_text(json.dumps(payload, ensure_ascii=False))
            except Exception:
                pass

    async def push_stats(self):
        await self.notify_broadcaster(
            {
                "type": "stats",
                "listeners": self.listener_count,
                "languages": self.lang_breakdown(),
                "status": self.status,
                "seq": self.seq,
            }
        )

    # --- gestion des connexions -----------------------------------------
    async def add_listener(self, ws: WebSocket, lang: str):
        self.listeners.setdefault(lang, set()).add(ws)
        self.ws_lang[ws] = lang
        self.touch()
        await self.push_stats()

    async def change_lang(self, ws: WebSocket, lang: str):
        old = self.ws_lang.get(ws)
        if old == lang:
            return
        if old and old in self.listeners:
            self.listeners[old].discard(ws)
        self.listeners.setdefault(lang, set()).add(ws)
        self.ws_lang[ws] = lang
        self.touch()
        await self.push_stats()

    async def drop_listener(self, ws: WebSocket):
        lang = self.ws_lang.pop(ws, None)
        if lang and lang in self.listeners:
            self.listeners[lang].discard(ws)
            if not self.listeners[lang]:
                self.listeners.pop(lang, None)
        try:
            await ws.close()
        except Exception:
            pass
        await self.push_stats()

    def history_for(self, lang: str, limit: int = 15) -> list[dict]:
        items = list(self.history)[-limit:]
        return [_phrase_payload(rec, lang) for rec in items]

    def history_since(self, lang: str, since_seq: int) -> list[dict]:
        """Phrases manquées depuis `since_seq` (reprise de séquence à la reconnexion)."""
        return [
            _phrase_payload(rec, lang)
            for rec in list(self.history)
            if rec["seq"] > since_seq
        ]

    def find_record(self, seq: int) -> dict | None:
        for rec in self.history:
            if rec["seq"] == seq:
                return rec
        return None


def _phrase_payload(rec: dict, lang: str) -> dict:
    """Projette un enregistrement d'historique pour une langue donnée."""
    if lang == "ar":
        text = rec["arabic"]
    else:
        text = rec["translations"].get(lang, "")
    return {
        "type": "phrase",
        "seq": rec["seq"],
        "ts": rec["ts"],
        "lang": lang,
        "text": text,
        "arabic": rec["arabic"],
        "is_quran": rec["is_quran"],
        "quran_ref": rec["quran_ref"],
        "is_hadith": rec.get("is_hadith", False),
        "degraded": rec.get("degraded", False),
        "corrected": rec.get("corrected", False),
    }


# --------------------------------------------------------------------------- #
# Gestionnaire global des sessions
# --------------------------------------------------------------------------- #

ROOMS: dict[str, Room] = {}


def get_room(code: str) -> Room | None:
    return ROOMS.get(code.upper())


def create_room() -> Room:
    for _ in range(20):
        code = _gen_code()
        if code not in ROOMS:
            room = Room(code)
            ROOMS[code] = room
            return room
    raise RuntimeError("Impossible de générer un code de session unique")


async def _janitor():
    """Purge périodique des sessions inactives."""
    while True:
        await asyncio.sleep(300)
        now = time.time()
        for code, room in list(ROOMS.items()):
            if room.broadcaster is None and room.listener_count == 0 and (
                now - room.last_activity > SESSION_TTL
            ):
                ROOMS.pop(code, None)


# --------------------------------------------------------------------------- #
# Pipeline de traduction d'un segment final
# --------------------------------------------------------------------------- #


async def process_final_segment(room: Room, arabic_text: str, *, manual: bool = False):
    arabic_text = (arabic_text or "").strip()
    if not arabic_text:
        return
    room.touch()
    room.seq += 1
    seq = room.seq
    ts = int(time.time() * 1000)

    target_langs = room.active_target_langs()
    result = None
    if target_langs and translator.has_api_key():
        try:
            result = await translator.translate_segment(
                arabic_text, target_langs, room.glossary
            )
        except Exception as exc:  # défensif : jamais casser le flux
            print(f"[translate] exception: {exc!r}")
            result = None

    degraded = result is None
    if degraded:
        rec = {
            "seq": seq, "ts": ts, "arabic": arabic_text, "translations": {},
            "is_quran": False, "quran_ref": None, "is_hadith": False,
            "degraded": True, "corrected": False,
        }
    else:
        rec = {
            "seq": seq, "ts": ts,
            "arabic": result.get("arabic") or arabic_text,
            "translations": result.get("translations", {}),
            "is_quran": result.get("is_quran", False),
            "quran_ref": result.get("quran_ref"),
            "is_hadith": result.get("is_hadith", False),
            "degraded": False, "corrected": False,
        }
    room.history.append(rec)
    await _broadcast_record(room, rec, manual=manual)


async def recorrect_segment(room: Room, seq: int, arabic_text: str):
    """Le diffuseur corrige l'arabe d'un segment déjà diffusé : on re-traduit et
    on re-pousse la phrase (les auditeurs remplacent la version affichée)."""
    arabic_text = (arabic_text or "").strip()
    rec = room.find_record(seq)
    if not rec or not arabic_text:
        return
    room.touch()
    target_langs = room.active_target_langs()
    result = None
    if target_langs and translator.has_api_key():
        try:
            result = await translator.translate_segment(
                arabic_text, target_langs, room.glossary, use_cache=False
            )
        except Exception as exc:
            print(f"[recorrect] {exc!r}")
    rec["arabic"] = (result or {}).get("arabic") or arabic_text
    if result:
        rec["translations"] = result.get("translations", {})
        rec["is_quran"] = result.get("is_quran", False)
        rec["quran_ref"] = result.get("quran_ref")
        rec["is_hadith"] = result.get("is_hadith", False)
        rec["degraded"] = False
    rec["corrected"] = True
    rec["ts"] = int(time.time() * 1000)
    await _broadcast_record(room, rec, corrected=True)


async def _broadcast_record(room: Room, rec: dict, *, manual: bool = False,
                            corrected: bool = False):
    for lang in list(room.listeners.keys()):
        payload = _phrase_payload(rec, lang)
        payload["corrected"] = corrected or rec.get("corrected", False)
        await room.broadcast_lang(lang, payload)

    _pref = (room.default_langs[0] if room.default_langs else "fr")
    _preview = rec["translations"].get(_pref) or next(
        (v for v in rec["translations"].values() if v), ""
    )
    await room.notify_broadcaster({
        "type": "monitor",
        "seq": rec["seq"], "ts": rec["ts"],
        "arabic": rec["arabic"],
        "preview": _preview,
        "is_quran": rec["is_quran"],
        "quran_ref": rec["quran_ref"],
        "degraded": rec.get("degraded", False),
        "corrected": corrected,
        "manual": manual,
    })


# --------------------------------------------------------------------------- #
# Application FastAPI
# --------------------------------------------------------------------------- #


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_janitor())
    yield
    task.cancel()
    await translator.aclose()


app = FastAPI(title="Khutbah Live Translation", version="1.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------- REST --------------------------------------- #

from starlette.requests import Request  # noqa: E402


def base_url(request: Request) -> str:
    """URL publique de base (respecte PUBLIC_BASE_URL et les en-têtes de proxy)."""
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") \
        or f"{request.url.hostname}:{request.url.port or 8000}"
    return f"{proto}://{host}"


@app.get("/healthz")
async def healthz():
    return {
        "ok": True,
        "rooms": len(ROOMS),
        "gemini": translator.has_api_key(),
        "model": translator.MODEL,
    }


@app.get("/api/languages")
async def api_languages():
    return {"languages": [{"code": c, "name": n} for c, n in SUPPORTED_LANGUAGES.items()]}


# Rate limiting mémoire : créations de session par IP (fenêtre glissante).
_RL_WINDOW = 60.0
_RL_MAX = 12
_rl_hits: dict[str, deque] = {}


def _rate_ok(ip: str) -> bool:
    now = time.time()
    dq = _rl_hits.setdefault(ip, deque())
    while dq and now - dq[0] > _RL_WINDOW:
        dq.popleft()
    if len(dq) >= _RL_MAX:
        return False
    dq.append(now)
    return True


@app.post("/api/session")
async def api_create_session(request: Request):
    if not translator.has_api_key() and not ALLOW_NO_API_KEY:
        raise HTTPException(503, "GEMINI_API_KEY non configurée")
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
          or (request.client.host if request.client else "?"))
    if not _rate_ok(ip):
        raise HTTPException(429, "Trop de sessions créées, réessayez dans une minute")

    body = {}
    try:
        raw = await request.body()
        if raw:
            body = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        body = {}

    room = create_room()
    room.glossary = str(body.get("glossary") or "").strip()[:4000]
    room.mosque_name = str(body.get("mosque_name") or "").strip()[:120]
    langs = body.get("target_langs") or []
    if isinstance(langs, list):
        room.default_langs = [
            l for l in langs if l in SUPPORTED_LANGUAGES and l != "ar"
        ] or list(DEFAULT_TARGET_LANGS)

    return {
        "code": room.code,
        "broadcaster_token": room.token,
        "created_at": room.created_at,
        "join_url": f"{base_url(request)}/?s={room.code}",
        "gemini": translator.has_api_key(),
        "mosque_name": room.mosque_name,
        "target_langs": room.default_langs,
    }


@app.get("/api/session/{code}")
async def api_get_session(code: str):
    room = get_room(code)
    if not room:
        raise HTTPException(404, "Session introuvable ou terminée")
    return {
        "code": room.code,
        "status": room.status,
        "listeners": room.listener_count,
        "languages": room.lang_breakdown(),
        "seq": room.seq,
        "has_broadcaster": room.broadcaster is not None,
        "mosque_name": room.mosque_name,
    }


@app.get("/api/session/{code}/qr.png")
async def api_session_qr(code: str, request: Request):
    room = get_room(code)
    if not room:
        raise HTTPException(404, "Session introuvable")
    import qrcode

    join_url = f"{base_url(request)}/?s={room.code}"
    img = qrcode.make(join_url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


# ----------------------------- Frontend / PWA ---------------------------- #

_ASSETS_DIR = (FRONTEND_DIR / "assets").resolve()
_ASSET_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".svg": "image/svg+xml", ".avif": "image/avif",
    ".woff2": "font/woff2", ".css": "text/css", ".txt": "text/plain",
}


@app.get("/assets/{name}")
async def assets(name: str):
    p = (_ASSETS_DIR / name).resolve()
    if _ASSETS_DIR not in p.parents or not p.is_file():
        raise HTTPException(404, "Ressource introuvable")
    media = _ASSET_TYPES.get(p.suffix.lower(), "application/octet-stream")
    return FileResponse(p, media_type=media,
                        headers={"Cache-Control": "public, max-age=604800"})


@app.get("/")
async def index():
    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML, media_type="text/html")
    return JSONResponse({"error": "frontend/index.html introuvable"}, status_code=500)


@app.get("/manifest.webmanifest")
async def manifest():
    data = {
        "name": "Traduction du prêche",
        "short_name": "Khutbah",
        "description": "Traduction en direct du prêche (khutbah) sur votre téléphone.",
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "display_override": ["standalone", "window-controls-overlay", "minimal-ui"],
        "orientation": "portrait",
        "categories": ["utilities", "education"],
        "background_color": "#080e1a",
        "theme_color": "#1a6b4a",
        "lang": "fr",
        "dir": "auto",
        "icons": [
            {"src": "./api/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "./api/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
    }
    return JSONResponse(data, media_type="application/manifest+json")


@app.get("/sw.js")
async def service_worker():
    sw = FRONTEND_DIR / "sw.js"
    if sw.exists():
        return FileResponse(sw, media_type="application/javascript",
                            headers={"Cache-Control": "no-cache"})
    return Response("", media_type="application/javascript")


_ICON_CACHE: dict[int, bytes] = {}


def _make_icon(size: int) -> bytes:
    if size in _ICON_CACHE:
        return _ICON_CACHE[size]
    from PIL import Image, ImageDraw

    # Palette islamique : fond nuit profond, vert émeraude, croissant doré.
    img = Image.new("RGBA", (size, size), (12, 21, 36, 255))
    d = ImageDraw.Draw(img)
    pad = int(size * 0.14)
    d.rounded_rectangle([pad, pad, size - pad, size - pad],
                        radius=int(size * 0.16), fill=(26, 107, 74, 255))
    # Croissant stylisé (doré).
    cx, cy, r = size * 0.52, size * 0.5, size * 0.24
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(244, 226, 160, 255))
    off = size * 0.09
    d.ellipse([cx - r + off, cy - r, cx + r + off, cy + r], fill=(26, 107, 74, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    _ICON_CACHE[size] = buf.getvalue()
    return _ICON_CACHE[size]


@app.get("/api/icon-{size}.png")
async def api_icon(size: int):
    size = max(48, min(size, 512))
    return Response(_make_icon(size), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


# ----------------------------- WebSocket : diffuseur -------------------- #


@app.websocket("/ws/broadcast/{code}")
async def ws_broadcast(ws: WebSocket, code: str, token: str = Query("")):
    room = get_room(code)
    if not room or token != room.token:
        await ws.close(code=4403)
        return
    await ws.accept()

    # Un seul diffuseur : on remplace l'ancien s'il existe.
    if room.broadcaster is not None:
        try:
            await room.broadcaster.close(code=4409)
        except Exception:
            pass
    room.broadcaster = ws
    room.status = "live" if room.status in ("idle", "stopped") else room.status
    room.touch()
    await ws.send_text(json.dumps({
        "type": "hello", "code": room.code, "status": room.status,
        "listeners": room.listener_count, "languages": room.lang_breakdown(),
        "gemini": translator.has_api_key(),
        "supported_languages": SUPPORTED_LANGUAGES,
        "mosque_name": room.mosque_name,
        "glossary": room.glossary,
        "target_langs": room.default_langs,
    }, ensure_ascii=False))
    await room.broadcast_all({"type": "session", "status": room.status})

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            mtype = msg.get("type")
            room.touch()

            if mtype == "transcript":
                text = (msg.get("text") or "").strip()
                if msg.get("is_final"):
                    if text:
                        asyncio.create_task(
                            process_final_segment(room, text, manual=bool(msg.get("manual")))
                        )
                else:
                    # Intérimaire : arabe live poussé à tous, sans traduction.
                    await room.broadcast_all({"type": "interim", "arabic": text})

            elif mtype == "audio":
                b64 = msg.get("data") or ""
                mime = msg.get("mime") or "audio/webm"
                import base64
                try:
                    audio = base64.b64decode(b64)
                except Exception:
                    audio = b""
                if 0 < len(audio) <= MAX_AUDIO_BYTES and translator.has_api_key():
                    asyncio.create_task(_handle_audio_chunk(room, audio, mime))
                elif len(audio) > MAX_AUDIO_BYTES:
                    await ws.send_text(json.dumps({"type": "error",
                                                   "message": "chunk audio trop volumineux"}))

            elif mtype == "correct":
                try:
                    cseq = int(msg.get("seq"))
                except (TypeError, ValueError):
                    cseq = 0
                ctext = (msg.get("arabic") or msg.get("text") or "").strip()
                if cseq and ctext:
                    asyncio.create_task(recorrect_segment(room, cseq, ctext))

            elif mtype == "config":
                # Mise à jour à chaud du glossaire / des langues par défaut.
                if "glossary" in msg:
                    room.glossary = str(msg.get("glossary") or "").strip()[:4000]
                langs = msg.get("target_langs")
                if isinstance(langs, list):
                    room.default_langs = [
                        l for l in langs if l in SUPPORTED_LANGUAGES and l != "ar"
                    ]
                await ws.send_text(json.dumps({
                    "type": "config_ok", "glossary": room.glossary,
                    "target_langs": room.default_langs,
                }, ensure_ascii=False))

            elif mtype == "control":
                action = msg.get("action")
                if action == "pause":
                    room.status = "paused"
                elif action == "resume":
                    room.status = "live"
                elif action == "stop":
                    room.status = "stopped"
                await room.broadcast_all({"type": "session", "status": room.status})
                await room.push_stats()

            elif mtype == "level":
                try:
                    room.audio_source_level = float(msg.get("value") or 0.0)
                except (TypeError, ValueError):
                    pass

            elif mtype == "ping":
                await ws.send_text(json.dumps({"type": "pong", "t": msg.get("t")}))

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[ws_broadcast] {exc!r}")
    finally:
        if room.broadcaster is ws:
            room.broadcaster = None
            room.status = "paused" if room.status == "live" else room.status
            await room.broadcast_all({"type": "session", "status": room.status,
                                      "broadcaster_gone": True})


async def _handle_audio_chunk(room: Room, audio: bytes, mime: str):
    try:
        text = await translator.transcribe_audio(audio, mime)
    except Exception as exc:
        print(f"[stt] {exc!r}")
        text = None
    if text:
        await room.notify_broadcaster({"type": "stt", "text": text})
        await process_final_segment(room, text)


# ----------------------------- WebSocket : auditeur -------------------- #


@app.websocket("/ws/listen/{code}")
async def ws_listen(ws: WebSocket, code: str, lang: str = Query("fr"),
                    since: int = Query(0)):
    room = get_room(code)
    if not room:
        await ws.close(code=4404)
        return
    if room.listener_count >= MAX_LISTENERS:
        await ws.close(code=4429)
        return
    if lang not in SUPPORTED_LANGUAGES:
        lang = "fr"
    await ws.accept()
    await room.add_listener(ws, lang)

    # Reprise de séquence : si le client se reconnecte avec `since`, on ne renvoie
    # que les phrases manquées ; sinon les dernières (nouvel arrivant).
    if since > 0:
        missed = room.history_since(lang, since)
    else:
        missed = room.history_for(lang)

    await ws.send_text(json.dumps({
        "type": "hello",
        "code": room.code,
        "status": room.status,
        "lang": lang,
        "history": missed,
        "resumed": since > 0,
        "seq": room.seq,
        "mosque_name": room.mosque_name,
        "supported_languages": SUPPORTED_LANGUAGES,
    }, ensure_ascii=False))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            mtype = msg.get("type")

            if mtype == "set_lang":
                new_lang = msg.get("lang")
                if new_lang in SUPPORTED_LANGUAGES:
                    await room.change_lang(ws, new_lang)
                    await ws.send_text(json.dumps({
                        "type": "lang_changed",
                        "lang": new_lang,
                        "history": room.history_for(new_lang),
                    }, ensure_ascii=False))

            elif mtype == "history":
                cur = room.ws_lang.get(ws, lang)
                await ws.send_text(json.dumps({
                    "type": "history",
                    "items": room.history_for(cur, limit=MAX_HISTORY),
                }, ensure_ascii=False))

            elif mtype == "ping":
                await ws.send_text(json.dumps({"type": "pong", "t": msg.get("t")}))

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[ws_listen] {exc!r}")
    finally:
        await room.drop_listener(ws)


# --------------------------------------------------------------------------- #
# Point d'entrée
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    print(f"http://{host}:{port}  (Gemini: {'OK' if translator.has_api_key() else 'ABSENT - degraded mode'})", flush=True)
    uvicorn.run("main:app", host=host, port=port, reload=False, ws_ping_interval=20,
                ws_ping_timeout=20)
