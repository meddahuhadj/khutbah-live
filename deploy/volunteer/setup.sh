#!/usr/bin/env bash
#
# setup.sh — Déploiement bénévole en ~10 minutes sur un mini-PC / Raspberry Pi.
# Guide pas à pas : nom de domaine, clés API, tunnel éventuel, lancement Docker.
# Aucune connaissance technique requise au-delà de répondre aux questions.
#
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
say()  { echo -e "${GREEN}==>${NC} $*"; }
warn() { echo -e "${YELLOW}ATTENTION :${NC} $*"; }
die()  { echo -e "${RED}ERREUR :${NC} $*"; exit 1; }

command -v docker >/dev/null 2>&1 || die "Docker n'est pas installé. Sur Raspberry Pi/Ubuntu :
  curl -fsSL https://get.docker.com | sh   puis redémarrez, puis relancez ce script."
docker compose version >/dev/null 2>&1 || die "Le plugin 'docker compose' est requis (docker >= 20.10)."

# --------------------------------------------------------------------------
say "Vérification des prérequis réseaux"
# On comptera sur un domaine ou un tunnel ; on ne bloque pas au cas où le
# hostname n'est pas encore pointé (l'utilisateur peut le faire après).
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# 1. Fichier .env (jamais commité, copié du modèle du backend)
# --------------------------------------------------------------------------
if [ ! -f .env ]; then
  say "Création du fichier .env à partir du modèle"
  cp ../../backend/.env.example .env
else
  say "Le fichier .env existe déjà — on garde les valeurs actuelles."
fi

fill_env() {
  # $1 = variable   $2 = libellé
  local var="$1" label="$2"
  if grep -q "^${var}=" .env; then
    local cur; cur=$(sed -n "s/^${var}=//p" .env | head -1)
    [ -z "$cur" ] || { warn "$var déjà renseignée (${cur:0:20}...)."; return; }
  fi
  read -rp "  $label : " val || val=""
  if [ -n "$val" ]; then
    # remplace ou insère la ligne (macOS sed n'a pas -i portable partout, on gère Linux)
    sed -i "s|^${var}=.*|${var}=${val}|" .env 2>/dev/null \
      || sed -i "s|^#\?${var}=.*|${var}=${val}|" .env
  fi
}

say "Configurons les clés d'API (au moins une est requise pour la traduction)."
echo "  - Gemini     : https://aistudio.google.com/apikey (gratuit, ~15$/mois de quota free)"
echo "  - Groq       : https://console.groq.com/keys (gratuit, très rapide, excellent arabe)"
echo "  - OpenRouter : https://openrouter.ai/keys (une clé -> plusieurs modèles)"
echo "  - Azure      : ressource Azure Translator (2 M caractères/mois gratuits)"
echo "  Vous pouvez en laisser vides — le système essaiera les autres."
read -rp "  [Entrée] pour continuer, ou Ctrl+C pour un mode dégradé (arabe seul)."
fill_env GEMINI_API_KEY   "Clé Gemini (recommandée)"
fill_env GROQ_API_KEY     "Clé Groq (recommandée)"
fill_env OPENROUTER_API_KEY "Clé OpenRouter (optionnelle)"
fill_env AZURE_TRANSLATOR_KEY "Clé Azure Translator (optionnelle)"
fill_env AZURE_TRANSLATOR_REGION "Région Azure (ex: westeurope, optionnelle)"
fill_env DEFAULT_TARGET_LANGS "Langues par défaut, séparées par des virgules (ex: fr,en,nl) [vide=aucune]"

# --------------------------------------------------------------------------
# 2. Domaine + Caddyfile
# --------------------------------------------------------------------------
DOMAIN="${DOMAIN:-}"
if [ -z "$DOMAIN" ]; then
  read -rp "  Nom de domaine (ex: khutbah.mon-site.org) [laisser vide pour un test local http://IP-LAN]: " DOMAIN || true
fi
if [ -n "$DOMAIN" ]; then
  sed "s/{{DOMAIN}}/${DOMAIN}/g" Caddyfile.template > Caddyfile
  say "Caddyfile généré pour ${DOMAIN}. Pointez un enregistrement A *vers cette machine*."
  echo "    -> $DOMAIN :80/443 doivent être accessibles depuis Internet (test: curl -v http://$DOMAIN)."
else
  warn "Pas de domaine : on met Caddy en http://localhost:8080 (test local uniquement)."
  cat > Caddyfile <<CG
:8080 {
    encode gzip
    reverse_proxy khutbah:8000
}
CG
  DOMAIN="localhost:8080"
fi

# --------------------------------------------------------------------------
# 3. Tunnel Cloudflare (optionnel, si pas de ports publics)
# --------------------------------------------------------------------------
if [ -z "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]; then
  read -rp "  Utiliser un tunnel Cloudflare ? [N/o] : " -r yn || yn="n"
  if [[ "$yn" =~ ^[OoYy]$ ]]; then
    read -rp "  Token du tunnel : " -r tok || tok=""
    [ -n "$tok" ] && echo "CLOUDFLARE_TUNNEL_TOKEN=$tok" >> .env
  fi
fi

# --------------------------------------------------------------------------
# 4. PUBLIC_BASE_URL = le vrai domaine pour les liens/QR
# --------------------------------------------------------------------------
if [ -n "$DOMAIN" ] && ! grep -q "^PUBLIC_BASE_URL=." .env; then
  if [[ "$DOMAIN" == http* ]]; then
    sed -i "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=${DOMAIN}|" .env
  else
    sed -i "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://${DOMAIN}|" .env
  fi
fi

# --------------------------------------------------------------------------
# 5. Build + lancement
# --------------------------------------------------------------------------
say "Construction de l'image 'khutbah' (première fois : quelques minutes)..."
docker compose build
say "Lancement des services (khutbah + Caddy)..."
docker compose up -d

say "Fait !"
echo
[ -n "$DOMAIN" ] && echo "  URL du direct : https://${DOMAIN}"
[ -z "$DOMAIN" ] && echo "  URL du direct : http://<IP-de-this-machine>:8080"
echo "  Vérifier la santé : $(docker compose ps 2>/dev/null || true)  (ou : docker compose logs)"
printf '%s\n' "  Si le QR/le lien ne fonctionnent pas, vérifiez OPEN ports 80/443 et la pointe DNS."