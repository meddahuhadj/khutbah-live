# Traduction en direct du prêche (khutbah)

Application web temps réel qui **capte la voix de l'imam, la transcrit, la traduit et
diffuse la traduction à chaque fidèle sur son propre téléphone** — en sous-titres et/ou
en synthèse vocale dans ses écouteurs. **Rien n'est diffusé en audio dans la salle.**

- **Backend** : FastAPI + WebSocket (Python) — gestion des sessions, traduction Gemini, relais temps réel.
- **Frontend** : PWA en **un seul fichier HTML** (`frontend/index.html`) — vues Diffuseur et Auditeur, QR code, sélecteur de langue, sous-titres, TTS. Installable, responsive, sans app store.
- **Prompt système spécialisé** : [`SYSTEM_PROMPT.md`](SYSTEM_PROMPT.md) — impose un registre fidèle et sobre pour le contenu religieux (Coran, hadith, terminologie).

### Nouveautés v1.1 (robustesse terrain + personnalisation)

- **Reprise de séquence à la reconnexion** : l'auditeur renvoie son dernier `seq` ; le serveur ne rejoue que les phrases manquées → plus de « trou » après une coupure réseau.
- **Glossaire par session** : à la création, le diffuseur saisit un nom de mosquée, les langues traduites par défaut et un glossaire (noms propres, termes locaux, translittérations imposées) — injecté dans **chaque** appel Gemini et intégré à la clé de cache.
- **Correction en direct** : bouton « ✏️ Corriger ce segment » sur le moniteur diffuseur → l'arabe corrigé est re-traduit et la phrase est **remplacée en place** chez tous les auditeurs (badge ✏️), le cache est mis à jour.
- **Détection iOS / navigateur sans reconnaissance vocale** : le mode « Reconnaissance navigateur » est masqué, bascule automatique sur « Audio → serveur » (ou « Manuel »), message explicite.
- **Mode simple** (personnes âgées / non-lectrices) : un seul très gros sous-titre, aucun réglage visible, bouton de sortie discret.
- **Export de la khutbah** : depuis l'historique auditeur, « Imprimer / PDF » (fenêtre imprimable, sans dépendance) ou « Télécharger .txt » — horodatage, arabe + traduction, références coraniques.
- **Nom de la mosquée** affiché à l'auditeur (écran rejoindre + barre du direct) pour éviter la confusion entre sessions.
- **Rate limiting** : max 12 créations de session par IP et par minute (`429` au-delà).

### Habillage (v1.2)

- **Thème clair / sombre** : suit `prefers-color-scheme` par défaut, bouton ☀️/🌙 dans la barre du haut, choix mémorisé, sans flash au chargement. Palette entièrement en variables CSS.
- **Fond « mosquée »** : photo réelle d'**Al-Masjid an-Nabawi** (Mosquée du Prophète, Médine), servie depuis `frontend/assets/mosque-bg.jpg` (~160 ko, redimensionnée 1920 px, mise en cache par le service worker → chargée une seule fois). Fondue dans la couleur du thème par un voile dégradé (`--photo-scrim`) pour rester lisible ; **fond uni en mode simple**. Image : Wikimedia Commons, *File:MasjidNabawi.jpg* (auteur : Wurzelgnohm), **licence CC0 1.0** (domaine public) — voir `frontend/assets/CREDIT.txt`.
- **Responsive** : typographie fluide (`clamp`), zones tactiles ≥ 44 px, `safe-area` iOS, feuilles en modale centrée sur grand écran, vue diffuseur sur 2 colonnes ≥ 960 px, respect de `prefers-reduced-motion`.

### Style religieux & Coran (v1.3)

- **Palette islamique** : vert émeraude profond + **or** (accents, séparateurs, badges) sur fond nuit bleu-vert (clair : crème & vert, sans flash). Icône PWA et manifeste alignés (croissant doré sur vert).
- **Bismillah** : « بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ » en tête d'application (masqué en mode simple) + **ornements** : motifs géométriques islamiques (SVG inline, 4 % d'opacité), étoiles ✦✦✦, séparateurs ornés ✦ et **۞ Rubʿ al-ḥizb** sur les cartes code/QR et rejoindre.
- **Salutation & rappel** : « As-salâmu ʿalaykum » sur l'accueil + **dhikr** aléatoire (mots du Prophète ﷺ et versets) affiché sous les boutons, traduit dans les 4 langues de l'interface.
- **📖 Lecteur du Coran** (écran d'accueil) : choisissez sourate (114, noms FR/AR), intervalle de versets (plages validées par sourate) et récitateur (Alafasy, Al-Muaiqly, Al-Ghamdi, As-Sudais, Al-Husary) → récitation en continu depuis **everyayah.com** (chargée **à la demande**, jamais au chargement). Boutons Écouter / Arrêter, ligne de statut « Récitation en cours ».
- **🎧 Récitation d'un verset cité** : chaque verset coranique détecté dans le prêche (`is_quran` + référence sûre) affiche : bouton **🎧** qui lance la récitation du verset (re-toucher pour arrêter), bouton **📖** qui ouvre le lecteur déjà réglé sur cette sourate/verset, et — si le réseau le permet — le **texte exact du verset** (alquran.cloud, résultats mis en cache) remplace la transcription du micro pour une lecture claire et fiable.
- **Rappels de piété** : formules d'eulogie rendues selon `SYSTEM_PROMPT.md` (paix et bénédiction sur le Prophète, etc.).

### Accessibilité & confidentialité (v1.4)

- **Contraste élevé** : bouton `◐` dans la barre du haut (et interrupteur dans les réglages), mémorisé, sans flash. Retire la photo de fond, les ornements et les dégradés, épaissit les bordures, aligne le texte secondaire sur la couleur principale. Suit aussi `prefers-contrast: more`. Contrastes du thème clair relevés au niveau **WCAG AA**.
- **Navigation clavier** : lien d'évitement « Aller au contenu », anneau de focus visible homogène (`:focus-visible`), focus déplacé sur le titre à chaque changement d'écran.
- **Boîtes de dialogue** (réglages, historique, Coran, tasbih, confidentialité) : `role="dialog"` + `aria-modal`, focus piégé au `Tab`, **Échap** et clic sur le fond pour fermer, focus rendu au bouton d'origine.
- **Lecteurs d'écran** : `#subs` annoncé en `role="log" aria-live="polite"` ; ligne intermédiaire arabe en `aria-hidden` ; états de connexion en `role="status"` ; libellés ARIA (traduits) sur les boutons icônes et les boutons ▶ / 🎧 / 📖 générés dynamiquement.
- **RGPD** : bandeau de consentement à la première visite (mémorisé), page **🔒 Confidentialité** détaillée en 4 langues (accueil + réglages), et **case d'autorisation obligatoire** côté diffuseur (« j'ai le droit de diffuser la voix de l'imam ») qui conditionne la création de session.
- **Navigation arrière** : bouton **« ‹ Retour »** dans une **barre du haut collante** (reste visible même en faisant défiler un formulaire long) — essentiel en PWA installée sur iOS où il n'y a pas de bouton navigateur. Prise en charge aussi du **bouton retour Android / du geste système** via l'API History : ferme d'abord une feuille ouverte, sinon revient à l'écran précédent (et coupe proprement le WebSocket en quittant le direct). Flèche inversée en interface arabe (RTL).

### Outils opérateur (v1.5)

- **Bibliothèque de phrases** (carte sur l'écran diffuseur en direct) : ~15 formules de khutbah pré-remplies en arabe (basmala, hamdala, salawât, « yâ ayyuhâ lladhîna âmanû », istighfâr de clôture, duʿâ' final…). **Un tap = envoi immédiat** aux fidèles (passe par le même chemin que la saisie manuelle, fonctionne dans tous les modes de captation, même en pause). L'opérateur ajoute / supprime ses propres phrases (mémorisées en local, `localStorage`), et peut rétablir la liste par défaut. Saisie RTL, ajout à la touche Entrée.

### Horloge, Tasbih, date hijri & PWA (v1.6)

- **Horloge temps réel** dans la barre du haut collante : *grande heure + date* dans les 4 langues, **séparateur deux-points clignotant** cadencé sur la seconde, **sans dérive** (recalée sur `Date.now()` chaque seconde, resynchronisée au retour d'onglet). **Responsive** : une seule ligne fluide de 360 à >900 px — date masquée ≤ 600 px, secondes ≤ 420 px, titre du logo ≤ 480 px. Compatible contraste élevé ; fonctionne **hors ligne** (la coquille est en cache PWA).
- **Tasbih 📿** (accueil) : anneau compteur circulaire à dégradé or (progression `conic-gradient` vers 33), cycles **33 ×(Subḥān Allāh, Al-ḥamd li-Llāh, Allāhu akbar) puis 34 × Lā ilāha illā Llāh** avant auto-enchaînement, vibrations sur Android (`navigator.vibrate`), compteur persisté (`localStorage`), boutons −1 / Recommencer, clavier + Échap + clic fond pris en charge.
- **Date hijri** (accueil, sous la salutation) : « 📅 … » via le calendrier islamique natif (`Intl` `islamic-umalqura`), affichée dans la langue de l'interface, masquée élégamment si non prise en charge.
- **Mémoire des versets** : le texte exact des versets coraniques (alquran.cloud) est aussi persisté en `localStorage` (capé à 500 entrées) — les versets déjà vus s'affichent **instantanément** après rechargement, même hors réseau.
- **PWA renforcée** : cache du service worker passé en `v4`, manifeste enrichi (`display_override`, catégories) — l'horloge fait partie de la coquille hors ligne.

### Fiabilité : repli de référence, cause du mode dégradé, tests (v1.7–v1.8)

- **Cause du mode dégradé affichée** : le serveur distingue le type d'échec Gemini (`quota` / `auth` / `server` / `network` / `no_key`) et l'appli l'explique clairement à l'opérateur (toast + moniteur + ligne d'état) au lieu du vague « traduction indisponible ». Ex. quota gratuit épuisé → *« Quota Gemini dépassé… utilisez une autre clé, changez `GEMINI_MODEL` pour `gemini-2.5-flash-lite`, ou activez la facturation. »*
- **Reconnaissance vocale : échecs rendus visibles** — ligne d'état côté diffuseur (`Écoute active` / `Voix captée` / erreurs typées : réseau, langue non supportée, démarrage impossible), chien de garde 9 s qui conseille « Audio → serveur » / « Manuel », et le VU-mètre ne bloque plus le démarrage.
- **Contexte non sécurisé détecté** : si l'appli est ouverte sur `http://192.168.x.x` (pas HTTPS), le micro est bloqué par le navigateur → les modes micro sont désactivés, message explicite (« diffusez depuis `http://localhost:8000` ou via un lien HTTPS »).
- **Lien de partage utilisable** : quand l'imam est sur `localhost`, le serveur réécrit `join_url` **et le QR** avec son **IP LAN** (`socket`), pour que les téléphones du même Wi-Fi puissent rejoindre.
- **Repli de référence coranique** : quand Gemini renvoie `is_quran=true` mais `quran_ref=null`, le backend cherche le segment dans un **index local du texte coranique** (`backend/data/quran_index.json`, ~711 Kio, sans diacritiques ; **100 % hors-ligne**). Gère les citations partielles et les plages `S:A1-A2` ; la référence retrouvée est marquée « ≈ » (à vérifier). Rebuild : `python scripts/build_quran_index.py`.
- **Bibliothèque de phrases** (diffuseur) : ~15 formules de khutbah pré-remplies, envoi en un tap, ajout/suppression persistés localement.
- **Suite de tests `pytest`** : `backend/tests/` (44 tests, Gemini mocké — aucun appel réseau). `pip install -r requirements-dev.txt && pytest`.

### Ordre strict des segments & durcissement mémoire (v1.9)

- **Ordre garanti par `seq`** : chaque room a désormais un **worker asynchrone unique** qui traite les segments finaux **en série** (file `asyncio.Queue`). Avant, chaque segment partait en `create_task` et la diffusion suivait le `await` de traduction — si la traduction de N+1 revenait avant celle de N, l'auditeur recevait 4 après 5 et l'historique s'empilait dans le désordre. Le worker consomme aussi le chemin **audio → serveur** (STT sérialisée) → ordre garanti de bout en bout. Test dédié : traduction du segment 1 volontairement lente, segment 2 instantané → l'auditeur reçoit quand même 1 puis 2.
- **Backlog borné** : si la parole dépasse la vitesse de traduction, la file est plafonnée (`SEG_QUEUE_MAX`, défaut 24) et **sacrifie le plus ancien segment en attente** pour rester proche du direct (`segments_dropped` dans `/healthz`).
- **Anti-DoS mémoire** : plafond global `MAX_ROOMS` (défaut 300, sinon `503`), purge des sessions **créées mais jamais démarrées** après `IDLE_ROOM_TTL` (défaut 20 min), janitor toutes les 2 min. Les workers de room sont annulés à la purge et à l'arrêt du serveur.
- **`/healthz` enrichi** : `rooms`, `rooms_live`, `listeners`, `segments_total`, `segments_dropped`, `gemini_last_error`.
- **Garde-fou prompt** : un test vérifie que `SYSTEM_PROMPT.md` est bien chargé (≠ prompt court de secours).

> ⚠️ **Sécurité** : ne jamais mettre `backend/.env` (clés API) dans une archive ou un commit — il est déjà dans `.gitignore`. Pour partager le projet : `zip -r projet.zip . -x '*/.venv/*' '*/.git/*' '*.env' 'backend/data/quran_raw.json'`.

### Chaîne de repli multi-fournisseurs (v2.0)

Pour ne plus jamais tomber en mode dégradé sur un simple quota gratuit épuisé, la traduction et la transcription essaient **plusieurs fournisseurs dans l'ordre** — seuls ceux dont la clé est présente sont tentés, le premier qui répond gagne.

- **Traduction** (`TRANSLATE_PROVIDERS`, défaut `gemini,groq,openrouter,azure`) :
  - **`gemini`** — meilleure fidélité religieuse. **Rotation de clés** : `GEMINI_API_KEYS="k1,k2,k3"` (projets Google Cloud distincts → quotas cumulés) ; bascule automatique sur la clé suivante en cas de `429`. Modèle `GEMINI_MODEL` (défaut `gemini-2.5-flash-lite`, quota gratuit plus large que `flash`).
  - **`groq`** (`GROQ_API_KEY`) — Llama 3.3 70B, gratuit, très rapide, ~14 400 req/j.
  - **`openrouter`** (`OPENROUTER_API_KEY`) — une clé, plusieurs modèles dont des `:free` (`OPENROUTER_MODEL`).
  - **`azure`** (`AZURE_TRANSLATOR_KEY` + `AZURE_TRANSLATOR_REGION`) — **2 M caractères/mois gratuits**, ultra-fiable. Traduction pure : pas de détection Coran (mais l'index local ci-dessus prend le relais).
- **Transcription audio** (`STT_PROVIDERS`, défaut `groq,gemini`) : **Groq Whisper large-v3** (gratuit, excellent en arabe/darija) puis Gemini.
- Si **tous** échouent → mode dégradé (arabe diffusé), avec la cause réelle affichée (`quota` / `auth` / `no_provider`…). `/healthz` expose `translate_providers`, `translate_last_provider`, `translate_last_error` ; le moniteur diffuseur affiche `↻ groq` quand un repli a servi.
- Voir `backend/.env.example` pour toutes les variables. **48 tests** (`backend/tests/`).

**Hébergement gratuit sans mise en veille** (vs Render Free qui s'endort après 15 min) : Fly.io, Koyeb, Oracle Cloud Always Free (VM permanente + Caddy), ou PC de la mosquée + Cloudflare Tunnel.

---

## 1. Architecture

```
                    (1) transcription arabe                 (4) fan-out par langue
  ┌──────────────┐     texte, WebSocket    ┌───────────────────────┐   texte, WebSocket   ┌──────────────┐
  │  DIFFUSEUR   │ ──────────────────────▶ │   BACKEND FastAPI     │ ───────────────────▶ │  AUDITEUR ×N  │
  │ imam / opér. │                         │                       │                      │  (fidèle)     │
  │              │   (repli) audio, WS     │  Room (1 = 1 prêche)   │                      │              │
  │ micro ─▶ STT │ ──────────────────────▶ │   ├ listeners par lang │                      │ sous-titres  │
  │  navigateur  │                         │   ├ historique (N)     │                      │   + TTS      │
  │  ou Gemini   │                         │   └ séquence           │                      │ (navigateur) │
  │  ou saisie   │                         │                       │                      │              │
  └──────────────┘                         │   (3) Gemini API      │                      └──────────────┘
                                           │   1 appel / phrase →  │
                                           │   toutes les langues  │
                                           │   + détection Coran   │
                                           └───────────────────────┘
                                             (2) réception segment final
```

**Une `Room` = un prêche.** Elle contient : le WebSocket du diffuseur (un seul, protégé par
un token), les WebSockets des auditeurs **indexés par langue**, un numéro de séquence, et un
historique borné des dernières phrases (`MAX_HISTORY`).

### Pipeline temps réel

| # | Étape | Où | Détail |
|---|-------|-----|--------|
| 1 | **Captation + STT** | Diffuseur (navigateur) | `SpeechRecognition` (Web Speech API, `ar-*`) produit des résultats *intermédiaires* (~300 ms) et *finaux*. Le texte arabe part en WebSocket — **pas d'audio**, bande passante minimale. Replis : audio en tranches de 4 s → Gemini STT ; ou saisie manuelle. |
| 2 | **Relais** | Backend | Le segment *final* arrive ; le backend l'horodate et lui donne un numéro de séquence. |
| 3 | **Traduction** | Backend → Gemini | **Un seul appel** `generateContent` par phrase, avec le prompt système religieux, renvoyant un JSON structuré `{arabic, is_quran, quran_ref, is_hadith, translations:[{lang,text}…]}` pour **toutes les langues actives à la fois**. Coût et latence en **O(phrases)**, jamais en O(auditeurs). Cache mémoire pour les formules répétées. |
| 4 | **Diffusion** | Backend → Auditeurs | Fan-out WebSocket : chaque auditeur ne reçoit **que sa langue**. Le texte arabe *intermédiaire* est poussé en parallèle comme ligne « live » sous le dernier sous-titre. |
| 5 | **Restitution** | Auditeur (navigateur) | Sous-titre défilant (avec l'arabe original en option, encadré spécifique pour le Coran + référence) et/ou `speechSynthesis` dans la langue choisie. La file TTS **saute le retard** pour rester proche du direct. |

### Gestion de la latence

- **STT navigateur** plutôt qu'audio→serveur : supprime l'aller-retour audio (upload + transcodage + STT) ; ~300–500 ms au lieu de 2–4 s.
- **Traduction sur segment final court** (une proposition), pas sur toute la phrase : Gemini Flash répond en ~0,4–0,9 s pour un texte court.
- **Batch multi-langues** : une seule latence Gemini quel que soit le nombre de langues.
- **Intermédiaires diffusés** : le fidèle *voit* l'arabe avancer même avant la traduction — la latence perçue chute.
- **Fan-out asynchrone** non bloquant ; un auditeur lent est simplement retiré, il ne ralentit pas les autres.
- **Total observé** : ~1–2 s derrière le direct, acceptable pour la lecture. Le Tjson côté auditeur peut sauter des phrases pour se recaler.

### Passage à l'échelle (centaines d'auditeurs)

- **Diffusion un-vers-plusieurs, texte seul.** Une phrase ≈ 150–350 octets. 500 auditeurs × 300 o × ~6 phrases/min ≈ **~5 ko/s** en sortie pour toute la mosquée. Négligeable.
- **Coût Gemini indépendant du nombre d'auditeurs** : 1 appel par phrase, ~1 000 phrases pour un prêche de 30 min réparties sur ~5 langues.
- **Connexions WebSocket** : un worker Uvicorn (asyncio) tient sans peine plusieurs centaines de connexions oisives.
- **Au-delà d'un worker / d'une instance** : passer les `Room` sur **Redis Pub/Sub** (ou NATS). Le diffuseur publie le segment sur un canal `room:<code>` ; chaque worker abonné ré-émet vers ses auditeurs locaux. Le code isole déjà la diffusion dans `Room.broadcast_lang()` / `process_final_segment()` — un seul point à brancher. Sessions à sortir de la mémoire vers Redis avec TTL.
- **Mode dégradé réseau** : si Gemini est injoignable, le backend diffuse quand même l'arabe (`degraded:true`) ; l'appli reste utile pour les arabophones et l'historique.

### Confidentialité

Pas de compte, pas de collecte. L'audio **n'est jamais stocké** (chemin STT navigateur : l'audio ne quitte même pas l'appareil du diffuseur ; chemin audio→serveur : les tranches sont transcrites en vol, pas écrites sur disque). L'historique est **en mémoire** et purgé avec la session.

---

## 2. Choix technologiques — comparaison et recommandation

| Besoin | Options | Retenu | Pourquoi |
|--------|---------|--------|----------|
| **STT arabe streaming** | (a) Web Speech API du navigateur · (b) Gemini (audio inline par tranches) · (c) Gemini **Live API** (audio continu, transcrit + traduit en un flux) · (d) STT dédié (Google Speech-to-Text streaming, Deepgram…) | **(a) par défaut**, **(b) en repli**, (c)/(d) documentés | (a) : latence minimale, **zéro bande passante audio** (crucial en mosquée), gratuit, aucune clé. Limite : surtout Chrome/Edge, sessions à relancer périodiquement (géré). (b) : marche partout où il y a un micro, mais +2–4 s et upload audio. (c) **Gemini Live** : le plus élégant sur le papier (1 flux audio → texte traduit), à tester en priorité **si (a) ne suffit pas** ; coûteux en connexions/bande passante et en quota. (d) : qualité de streaming supérieure mais clé + coût + intégration lourde. |
| **Traduction** | Google **Gemini API** (`gemini-2.5-flash` / `-pro`) · autre LLM · API de traduction classique | **Gemini `2.5-flash`** avec le prompt système spécialisé | Bon compromis latence/qualité/prix, sortie **JSON structurée** (`responseSchema`), suit un prompt de registre exigeant, gère la détection de citation coranique et la translittération. `-pro` disponible via `GEMINI_MODEL` pour plus de fidélité (plus lent). Une API de traduction classique ne tiendrait pas la terminologie islamique ni la glose. |
| **TTS côté auditeur** | `speechSynthesis` du navigateur · TTS cloud | **`speechSynthesis` par défaut** | Gratuit, sur l'appareil, aucune bande passante, aucune donnée envoyée. Qualité et voix variables selon l'OS ; un TTS cloud (option future) donnerait une voix homogène au prix d'un flux audio par auditeur — contraire à la contrainte réseau. |
| **Transport temps réel** | WebSocket · SSE · WebRTC | **WebSocket** | Bidirectionnel (contrôle + télémétrie diffuseur), fan-out simple, natif FastAPI/Starlette, traverse bien les proxys. WebRTC serait surdimensionné pour du texte. |
| **Frontend** | PWA un fichier · SPA (React…) · natif | **PWA HTML/CSS/JS un seul fichier** | « Rejoindre en < 10 s », aucune installation, installable, hors-ligne pour la coquille, aucun CDN externe (réseau mosquée + vie privée). |

---

## 3. Installation

### Prérequis
- Python 3.10+
- Une **clé API Google Gemini** : <https://aistudio.google.com/apikey> (un niveau gratuit existe).

### Étapes

```bash
cd backend
python -m venv .venv
# Windows :  .venv\Scripts\activate
# macOS/Linux : source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # Windows : copy .env.example .env
# éditez .env et renseignez GEMINI_API_KEY
```

### Configuration (`backend/.env`)

| Variable | Défaut | Rôle |
|----------|--------|------|
| `GEMINI_API_KEY` | *(vide)* | **Clé Gemini.** Vide → mode dégradé (arabe diffusé, pas de traduction) si `ALLOW_NO_API_KEY=1`. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Modèle de traduction / STT de repli. `gemini-2.5-pro` = plus fidèle, plus lent. |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Écoute du serveur. |
| `PUBLIC_BASE_URL` | *(déduit)* | URL publique (pour les QR codes) si derrière un proxy / nom de domaine. Ex. `https://khutbah.ma-mosquee.org`. |
| `DEFAULT_TARGET_LANGS` | *(vide)* | Langues traduites même sans auditeur (préchauffage / aperçu diffuseur), ex. `fr,en,nl`. |
| `MAX_HISTORY` | `40` | Phrases conservées par session. |
| `MAX_LISTENERS` | `1500` | Plafond d'auditeurs par session. |
| `MAX_AUDIO_BYTES` | `2000000` | Taille max d'une tranche audio (chemin de repli). |
| `ALLOW_NO_API_KEY` | `1` | `1` = autorise le démarrage sans clé (mode dégradé / test). |

Les **langues cibles proposées** sont dans `backend/main.py` → `SUPPORTED_LANGUAGES` (ajustez selon votre communauté).

---

## 4. Lancement

```bash
cd backend
python main.py
# ou :  uvicorn main:app --host 0.0.0.0 --port 8000
```

Ouvrez **http://localhost:8000** (ou l'IP du poste sur le réseau de la mosquée).

> ⚠️ **HTTPS obligatoire hors `localhost`.** Le micro (`getUserMedia`), la reconnaissance vocale
> et l'installation PWA exigent un **contexte sécurisé**. En LAN, mettez un reverse-proxy TLS
> (Caddy en 3 lignes, Nginx, ou un tunnel type Cloudflare Tunnel / ngrok pour un test).

### Utilisation

**Diffuseur** (imam ou opérateur, téléphone/tablette/PC branché à la sono en entrée) :
1. « Je diffuse » → **Créer la session**.
2. Projetez / affichez le **code** et le **QR code**.
3. Choisissez le mode (Reconnaissance navigateur recommandée), la langue parlée, puis **Démarrer**.
4. Suivez le niveau sonore, le nombre d'auditeurs par langue, le moniteur du dernier segment. Pause / Arrêter à volonté.

**Auditeur** (fidèle) :
1. **Scanne le QR** (ou saisit le code) — aucune installation, aucun compte.
2. Choisit **sa langue** et le mode : sous-titres, voix, ou les deux.
3. Écoute dans ses écouteurs / lit l'écran. Options : taille du texte, vitesse de voix, **historique** pour rattraper une phrase manquée.

### Mode test minimal (recommandé d'abord)

Pour valider la chaîne temps réel avant d'enrichir :
1. Lancez le serveur **sans `GEMINI_API_KEY`** (`ALLOW_NO_API_KEY=1`).
2. Diffuseur en mode **Manuel**, un auditeur en langue **`ar`**, sous-titres seuls.
3. Envoyez quelques phrases : elles doivent apparaître chez l'auditeur en < 1 s, l'historique et la reconnexion doivent fonctionner.
4. Ajoutez ensuite la clé Gemini, puis les langues et le TTS.

---

## 5. Déploiement

### Option A — une seule machine (petite mosquée)
`python main.py` derrière **Caddy** (HTTPS automatique) :

```
khutbah.ma-mosquee.org {
    reverse_proxy 127.0.0.1:8000
}
```
`PUBLIC_BASE_URL=https://khutbah.ma-mosquee.org` dans `.env`.

### Option B — conteneur (recommandé)

Un `Dockerfile` prêt à l'emploi est fourni à la racine : une seule image
Python 3.12-slim qui copie `backend/`, `frontend/` et `SYSTEM_PROMPT.md`,
puis lance `python main.py` (le port lu dans `$PORT` — fourni par la
plateforme — défaut 8000).

```bash
cd "sermon Imam"
docker build -t khutbah .
docker run -p 8000:8000 -e GEMINI_API_KEY="..." khutbah
```

> À l'origine, ce README suggérait `uvicorn backend.main:app` — cette forme
> casse l'import de `translator` (module racine). Le `Dockerfile` évite le
> piège en lançant `main.py` depuis `backend/`.

### Option C — plateforme PaaS persistante (Render, Railway, Fly.io, VPS)

Cette app est un **processus long** (WebSockets + rooms en mémoire) : elle
doit tourner sur **une seule instance persistante**, pas en serverless.

1. **Render** (le plus simple) : un `render.yaml` est fourni — « New →
   Blueprint → connecter le dépôt » puis renseigner `GEMINI_API_KEY` (secret)
   dans le dashboard. Plan *Free* (gratuit, s'endort après 15 min
   d'inactivité ; pour un direct garanti sans aucune mise en veille,
   passez au plan *Starter*), sonde `/healthz`.
2. **Railway / Fly.io** : pusher le dépôt, le `Dockerfile` est détecté
   automatiquement, `PORT` est injecté, ajouter `GEMINI_API_KEY` comme
   variable d'environnement.
3. **VPS + Caddy** : cf. Option A — `docker run -p 8000:8000 khutbah` + un
   `reverse_proxy` avec `proxy_read_timeout` long pour les WebSockets.
4. Vérifier : `GET /healthz` → `{"ok":true,...,"gemini":true}` puis faire
   un aller-retour diffuseur → auditeur (un auditeur en `ar`).

> **Et Vercel ?** Depuis 2026, Vercel gère les WebSockets Python/FastAPI,
> mais sur **serverless** : connexion coupée à **5 min** (Hobby, 800 s Pro),
> **pas de fan-out inter-instances**, et l'état en mémoire s'évapore au
> cold start. Inadapté à un direct de 20-60 min — réserver Vercel à un
> éventuel statique du PWA pointant vers le backend persistant
> (`PUBLIC_BASE_URL`). La multi-instance, elle, est couverte par l'Option D.

### Option D — plusieurs instances / forte charge
1. Plusieurs workers Uvicorn/Gunicorn **derrière un load-balancer avec *sticky sessions*** (une connexion WebSocket doit rester sur le même worker).
2. Brancher `Room` sur **Redis Pub/Sub** : publier chaque segment sur `room:<code>`, chaque worker ré-émet vers ses auditeurs locaux. Points d'accroche : `create_room` / `get_room` (état → Redis avec TTL) et `process_final_segment` (publish au lieu de fan-out direct).
3. Terminaison TLS + `proxy_read_timeout` long pour les WebSockets.
4. Surveiller le **quota Gemini** ; le cache mémoire réduit déjà les appels sur les formules répétées.

---

## 6. Livrables — où est quoi

| Livrable attendu | Fichier |
|---|---|
| Backend FastAPI + WebSocket (sessions, relais, endpoints) | [`backend/main.py`](backend/main.py) |
| Pont API Gemini (traduction batch + STT de repli, cache, tolérance aux pannes) | [`backend/translator.py`](backend/translator.py) |
| Frontend PWA en un seul fichier (Diffuseur, Auditeur, QR, langues, sous-titres, TTS) | [`frontend/index.html`](frontend/index.html) |
| Service worker (coquille hors-ligne) + manifeste (servi par le backend) | [`frontend/sw.js`](frontend/sw.js) |
| Prompt système de traduction spécialisé (contenu religieux) | [`SYSTEM_PROMPT.md`](SYSTEM_PROMPT.md) |
| Installation / configuration / lancement / déploiement / architecture / latence / échelle | ce fichier |

### Endpoints

| Méthode | Route | Rôle |
|---|---|---|
| `GET` | `/` | PWA (fichier unique) ; `/?s=CODE` pré-remplit l'écran auditeur |
| `POST` | `/api/session` | Crée une session → `{code, broadcaster_token, join_url}` |
| `GET` | `/api/session/{code}` | État d'une session |
| `GET` | `/api/session/{code}/qr.png` | QR code (PNG) vers la page auditeur |
| `GET` | `/api/languages` | Langues cibles supportées |
| `GET` | `/healthz` | Sonde (état, clé Gemini, modèle) |
| `WS` | `/ws/broadcast/{code}?token=…` | Diffuseur (un seul par session) |
| `WS` | `/ws/listen/{code}?lang=fr` | Auditeur (des centaines) |

### Protocole WebSocket (résumé)

**Diffuseur → serveur** : `{type:"transcript", text, is_final, manual?}` · `{type:"audio", mime, data(base64)}` · `{type:"control", action:"pause|resume|stop"}` · `{type:"correct", seq, arabic}` · `{type:"config", glossary?, target_langs?}` · `{type:"level", value}` · `{type:"ping"}`
**Serveur → diffuseur** : `{type:"hello", …, mosque_name, glossary, target_langs}` · `{type:"stats", listeners, languages}` · `{type:"monitor", seq, arabic, preview, is_quran, quran_ref, degraded, corrected}` · `{type:"stt", text}` · `{type:"config_ok", …}`
**Auditeur → serveur** : `{type:"set_lang", lang}` · `{type:"history"}` · `{type:"ping"}` — la reprise se fait via le query param `?since=<seq>` à la (re)connexion
**Serveur → auditeur** : `{type:"hello", status, history[], resumed, mosque_name}` · `{type:"phrase", seq, ts, lang, text, arabic, is_quran, quran_ref, is_hadith, degraded, corrected}` · `{type:"interim", arabic}` · `{type:"session", status}` · `{type:"lang_changed", lang, history[]}` · `{type:"history", items[]}`

---

## 7. Limites connues / pistes

- **Web Speech API** : surtout Chrome/Edge desktop et Android ; iOS Safari n'en a pas. Détecté automatiquement côté diffuseur → bascule sur « Audio → serveur » ou « Manuel ».
- Le **chemin audio→serveur** segmente en tranches fixes de 4 s (pas de VAD) : découpe parfois une phrase. Convient au dépannage ; pour un usage soutenu, préférer la reconnaissance navigateur ou brancher Gemini Live.
- **Détection des versets** : dépend du modèle ; `quran_ref` peut être `null` (jamais inventée). Afficher l'arabe original à côté (option activée par défaut) reste le garde-fou.
- **TTS navigateur** : voix absente pour certaines langues selon l'appareil → repli automatique sur une voix proche, sinon sous-titres.
- Sessions et historique **en mémoire** : un redémarrage backend termine les sessions en cours (voir Redis pour la persistance).
