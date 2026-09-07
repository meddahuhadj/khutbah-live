#!/usr/bin/env bash
# Lancement rapide (macOS / Linux) : crée le venv si besoin, installe, démarre.
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/python -m pip install -q --upgrade pip
./.venv/bin/python -m pip install -q -r requirements.txt
[ -f .env ] || { cp .env.example .env; echo "-> .env créé : renseignez GEMINI_API_KEY"; }
exec ./.venv/bin/python main.py
