# Sentinel-X — dashboard de supervision

Interface web de supervision du boîtier Sentinel-X : état temps réel de chaque capteur, caméra accessible uniquement pendant une détection, alertes avec acquittement, journaux et audit, panel d'administration (redémarrages, services, comptes, badges, paramètres de détection).

Stack : React 18, TypeScript, Vite 8, React Router 7 (HashRouter), Recharts, lucide-react. Polices Barlow embarquées (fonctionne sans Internet sur le réseau dédié). Node 22 ou 24 requis.

## Démarrage rapide

```bash
npm install
cp .env.example .env      # VITE_API_MODE=mock par défaut
npm run dev               # http://localhost:5173
```

En mode **mock**, le boîtier, le backend et ses règles sont simulés dans le navigateur : intrusions, dérives de température, badges refusés, sabotage, scoring, escalade d'alertes, droits par rôle. Comptes : `admin`, `operateur`, `lecteur`, mot de passe `demo`.

En mode **live** (`VITE_API_MODE=live`), le dashboard appelle le vrai backend via `/api` et `/ws/live`. En développement, `vite.config.ts` proxifie ces chemins vers `VITE_BACKEND_URL` (par défaut `https://192.168.50.10`) et réécrit l'en-tête `Origin` pour passer la vérification anti-CSRF du backend. Le simulateur n'est pas inclus dans un build live.

| Commande | Résultat |
| --- | --- |
| `npm run dev` | Serveur de développement avec rechargement à chaud |
| `npm run typecheck` | Vérification TypeScript |
| `npm test` | Tests unitaires (Vitest) |
| `npm run lint` | ESLint |
| `npm run build` | Build de production dans `dist/` |
| `npm run build:single` | Un seul fichier `dist/index.html` autonome (démo hors-ligne) |

## Rôles

| Rôle | Peut |
| --- | --- |
| Lecteur | Voir l'état, les capteurs, l'historique, les alertes, la caméra pendant une détection |
| Opérateur | + armer/désarmer, acquitter les alertes, tester le buzzer, consulter les journaux |
| Administrateur | + redémarrages, services, comptes, badges, paramètres de détection, audit, accès caméra forcé (motif obligatoire, journalisé) |

## Structure

```
src/
├── types.ts            # contrat de données partagé avec le backend
├── api/
│   ├── client.ts       # interface Api
│   ├── live.ts         # implémentation REST + WebSocket
│   ├── mock.ts         # simulateur complet (mode démo)
│   └── mockScene.ts    # image de caméra simulée
├── store.tsx           # authentification, temps réel, notifications
├── components/         # Layout (barre latérale + bandeau d'état), composants partagés
└── pages/              # Vue d'ensemble, Caméra, Historique, Alertes, Journaux, Administration
```

## Contrat API attendu du backend

Authentification par cookie de session HttpOnly + Secure + SameSite=Strict posé par `/api/auth/login`. Les erreurs renvoient un JSON `{"detail": "message lisible"}` (format par défaut de FastAPI), affiché tel quel à l'utilisateur. Les types exacts sont dans `src/types.ts`.

Un **401** sur n'importe quelle route protégée renvoie le dashboard à l'écran de connexion (session expirée). Les autres refus doivent utiliser 403 (droits insuffisants, mot de passe actuel incorrect).

| Méthode | Route | Corps / paramètres | Réponse | Rôle minimum |
| --- | --- | --- | --- | --- |
| POST | `/api/auth/login` | `{username, password}` | `User` + cookie | public |
| POST | `/api/auth/logout` | — | 204 | connecté |
| GET | `/api/auth/me` | — | `User` ou 401 | connecté |
| POST | `/api/auth/password` | `{current, password}` (≥ 12 caractères) | `User` (avec `mustChangePassword: false`) | connecté |
| GET | `/api/state` | — | `SystemState` | lecteur |
| GET | `/api/measurements` | `?sensor=temperature\|humidity\|distance&range=1h\|6h\|24h\|7d` | `Point[]`, **sous-échantillonné à ~500 points maximum** (ex. `time_bucket` TimescaleDB) | lecteur |
| WS | `/ws/live` | — | messages `LiveMessage` | lecteur |
| GET | `/api/alerts` | — | `Alert[]` | lecteur |
| POST | `/api/alerts/{id}/ack` | `{comment}` | `Alert` | opérateur |
| GET | `/api/logs` | `?source=…&level=…&q=…` (répétables) | `LogEntry[]` | opérateur |
| GET | `/api/audit` | — | `AuditEntry[]` | admin |
| POST | `/api/devices/box01/arm` · `/disarm` | — | 204 | opérateur |
| POST | `/api/devices/box01/buzzer` | `{on}` | 204 | opérateur |
| GET | `/api/stream` | — | flux MJPEG annoté | lecteur |
| POST | `/api/camera/override` | `{reason}` (≥ 10 caractères) | 204 | admin |
| POST | `/api/system/restart` | `{target: box\|camera\|vision\|anomaly\|mosquitto\|backend\|all}` — `all` est orchestré par le backend (ordre, reprise sur erreur) | 204 | admin |
| GET | `/api/system/services` | — | `ServiceHealth[]` | admin |
| GET · POST | `/api/users` | `{username, role, password}` — crée le compte avec `mustChangePassword: true` | `User[]` · `User` | admin |
| PATCH · DELETE | `/api/users/{id}` | `{role?, active?}` — refuser (409) qu'un admin se retire ses propres droits | `User` · 204 | admin |
| POST | `/api/users/{id}/password` | `{password}` — remet `mustChangePassword: true` | 204 | admin |
| GET · POST | `/api/badges` | `{uid, owner}` | `Badge[]` · `Badge` | admin |
| PATCH · DELETE | `/api/badges/{id}` | `{active?, owner?}` | `Badge` · 204 | admin |
| GET · PUT | `/api/settings` | `Settings` | `Settings` | admin |

Messages WebSocket : `{"type":"state","data":SystemState}` à chaque changement d'état (ou au moins toutes les 2 s), `{"type":"alert","data":Alert}` à la création, à l'escalade ou à l'acquittement d'une alerte (même `id` = mise à jour), `{"type":"log","data":LogEntry}` (à n'envoyer qu'aux opérateurs et administrateurs : la page Journaux se recharge sur ce signal).

Le WebSocket doit être **fermé avec le code `4401`** si le cookie est absent ou expiré (le dashboard renvoie alors à l'écran de connexion au lieu de boucler). Après chaque reconnexion, le dashboard recharge `/api/state` et `/api/alerts`.

Tant que `user.mustChangePassword` est vrai, le dashboard n'affiche que l'écran de changement de mot de passe ; le backend doit de son côté refuser (403) toutes les autres routes pour ce compte.

## Règles de sécurité à appliquer côté backend

Le dashboard masque les actions non autorisées, mais **ce n'est pas une protection** : chaque règle doit être vérifiée par le backend.

- **Caméra** : `/api/stream` renvoie 403 tant que `camera.detectionActive` est faux et qu'aucun accès forcé n'est en cours. Sinon, n'importe qui peut ouvrir l'URL directement.
- **Rôles** vérifiés sur chaque route, y compris le WebSocket (cookie vérifié à l'ouverture).
- **Redémarrages** : ne pas monter `/var/run/docker.sock` dans le backend (équivalent root sur l'hôte). Passer par un petit service superviseur qui n'accepte qu'une liste fermée de cibles, ou publier une commande MQTT `reboot` sur `sentinel/box01/cmd` pour le boîtier.
- **Audit** : journaliser connexions (succès et échecs), armement, acquittement, redémarrage, accès caméra forcé avec motif, changements de comptes, badges et paramètres.
- **Mots de passe** : hash Argon2, 12 caractères minimum, limitation des tentatives.
- **CSRF** : cookie `SameSite=Strict` et vérification de l'en-tête `Origin` sur les requêtes POST/PUT/PATCH/DELETE.

## Déploiement dans le docker-compose

Remplacer le service `frontend` par :

```yaml
  frontend:
    build: ./frontend        # ce dossier
    restart: unless-stopped
```

Et router dans le `Caddyfile` (port du backend à adapter) :

```
192.168.50.10, sentinel.lan {
    tls /certs/broker.crt /certs/broker.key
    handle /api/* {
        reverse_proxy backend:8000
    }
    handle /ws/* {
        reverse_proxy backend:8000
    }
    handle {
        reverse_proxy frontend:80
    }
}
```

`nginx.conf` applique une Content-Security-Policy stricte (aucune ressource externe) et les en-têtes de sécurité usuels, définis dans `security-headers.conf` et inclus dans **chaque** `location` (nginx n'hérite pas des `add_header` du bloc `server` dès qu'un `location` en déclare). Vérification : `curl -sI https://sentinel.lan/ | grep -i content-security`.

L'export CSV des journaux neutralise les cellules commençant par `= + - @` (injection de formules dans Excel).

`npm audit` signale encore `braces` via `vite-plugin-singlefile` : aucune version corrigée n'existe, la dépendance ne sert qu'au build de démo `build:single` et ne traite aucune donnée externe.
