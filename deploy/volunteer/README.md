# Déploiement « bénévole » : la mosquée derrière la même porte que le serveur

Cible : **une personne non-technicienne** met la khutbah en ligne en ~10 minutes sur
un mini-PC / Raspberry Pi / vieux portable qui reste allumé dans la mosquée.
Pas de cloud, pas d'abonnement, pas de terminal avancé : un `setup.sh` interactif.

## Ce que ça installe

- L'**application** (`khutbah:latest`, construite depuis le `Dockerfile` racine).
- **Caddy** : reverse-proxy avec HTTPS automatique (Let's Encrypt) et relais WebSocket.
- **Optionnel** : un tunnel Cloudflare pour les cas où la box n'expose pas de port public
  (CGNAT des opérateurs, etc.).

## Prérequis

1. Un ordinateur/Docker : Raspberry Pi 4 (4 Go+) ou n'importe quelle machine Linux/Windows avec Docker.
   - Ubiquity : `curl -fsSL https://get.docker.com | sh`
   - Raspberry Pi OS : `sudo apt install docker.io` puis `sudo systemctl enable --now docker`.
2. Un nom de domaine pointé vers l'IP publique (facultatif pour un test en local).
3. Au moins une clé API (facultatif → mode dégradé, arabe seul) : Gemini, Groq, OpenRouter ou Azure.

## Installation (3 commandes)

```bash
cd deploy/volunteer
chmod +x setup.sh
sudo ./setup.sh
```

Le script vous guide : clés API, domaine, tunnel optionnel, puis construit et lance tout.
À la fin : `https://VOTRE-DOMAINE` (ou `http://IP-LAN:8080` en local) = l'application.

## Mises à jour

```bash
cd deploy/volunteer
sudo git -C ../.. pull        # ou remplacez le dossier par la nouvelle archive du dépôt
sudo docker compose up -d --build
```

## Fiches de dépannage rapide

| Sympôme | Cause probable | Action |
|---|---|---|
| « Ce site est inaccessible » | Ports 80/443 fermés ou DNS non pointé | Ouvrir les ports dans la box ; vérifier `dig` / entrée A |
| « Mixed content / micro bloqué » | Page servie en HTTP alors que le micro exige HTTPS | Pour les tests locaux, rester sur `http://localhost` ; en production, toujours HTTPS (Caddy s'en charge) |
| « Quota Gemini dépassé » | Quota gratuit épuisé | Ajouter une clé Groq/OpenRouter/Azure ; ou plusieurs clés Gemini séparées par des virgules (`GEMINI_API_KEYS`) |
| L'app se coupe après ~15 min d'inactivité | Mode veille du VPS Render (pas le cas ici) | Ici le conteneur tourne en permanence : `docker compose restart` |

## Architecture

```
  Smartphones (auditeurs) --WebSocket/HTTPS--> Caddy (443) --> khutbah:8000 (FastAPI)
  Diffuseur (imam)        --WebSocket/HTTPS--> Caddy (443) --> khutbah:8000
```

## Notes de sécurité

- `deploy/volunteer/.env` contient les clés API → ajoutez-le à `.gitignore` (le script le crée ; ne le committez jamais).
- Le conteneur `khutbah` n'expose pas de port sur l'hôte (seulement Caddy publie 80/443).
- Si vous ajoutez `cloudflared`, seul le tunnel est exposé ; désactivez alors les ports 80/443 publics dans le script.