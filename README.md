# Vidéothèque : tiers données (API REST)

API REST de la vidéothèque, avec la base MongoDB. C'est le tiers d'accès aux données de l'application en trois tiers réalisée pour le TP RT0705.

Le tiers présentation (site web) est dans le dépôt [videotheque-serveur](https://github.com/SenaiSensei/videotheque-serveur).

## Auteur

**Raphael LABESTE** ([@SenaiSensei](https://github.com/SenaiSensei)) : Master 1 Réseaux et Télécommunications parcours DAS, Université de Reims Champagne-Ardenne.
Projet réalisé dans le cadre du module RT0705 « Programmation des applications en réseau ».

## Description du projet

La vidéothèque est un catalogue de films commun à tous les utilisateurs. Chaque utilisateur peut parcourir le catalogue, faire des recherches et gérer ses favoris. Un administrateur gère les films et les comptes.

Cette API est le **seul accès aux données** :

- **Stockage :** les films et les comptes sont des documents JSON, conservés dans MongoDB.
- **Opérations :** l'API expose 17 routes, pour le CRUD des films et des comptes, la recherche, les favoris et la connexion.
- **Pagination :** `GET /films` et `GET /users` renvoient une page de résultats (`page`, `per_page`) avec le total et le nombre de pages, pour ne pas tout transférer d'un coup.
- **Anti-force brute :** après 5 échecs de connexion sur un même email en 5 minutes, l'API renvoie `429` le temps que la fenêtre glisse.
- **Authentification :** à la connexion, l'API émet un **jeton JWT** (HS256, valable une heure). Elle vérifie ce jeton et les droits (utilisateur, propriétaire du compte, administrateur) à chaque requête, même si le site les a déjà contrôlés.
- **Mots de passe :** ils sont hachés avec `werkzeug.security`, et ne sont jamais stockés ni renvoyés en clair.
- **Protection des administrateurs :** le dernier administrateur ne peut être ni supprimé, ni privé de son rôle.
- **Validation :** toutes les données reçues sont vérifiées (types, longueurs, formats, ObjectId). Les recherches sont échappées : une saisie comme `.*` est cherchée telle quelle.
- **Documentation :** une documentation OpenAPI 3.0 interactive (Swagger UI) est servie sur `/docs`.
- **Données de départ :** au premier lancement, la base est remplie avec un catalogue de **235 films** importés de TMDb (titre, résumé, réalisateur, acteurs, genres, affiche) et le compte administrateur initial.

### Routes

| Méthode | Route | Droits |
|---|---|---|
| `POST` | `/login` | public |
| `POST` | `/users` (inscription) | public |
| `GET` | `/users` | administrateur |
| `GET`, `DELETE` | `/users/{id}` | propriétaire ou administrateur |
| `PUT` | `/users/{id}` (profil) | propriétaire |
| `PUT` | `/users/{id}/roles` | administrateur |
| `GET`, `POST` | `/users/{id}/favorites` | propriétaire |
| `DELETE` | `/users/{id}/favorites/{film_id}` | propriétaire |
| `GET` | `/films` (liste, recherche, paginée) | connecté |
| `POST` | `/films` | administrateur |
| `GET` | `/films/genres` | connecté |
| `GET` | `/films/{id}` | connecté |
| `PUT`, `DELETE` | `/films/{id}` | administrateur |
| `GET` | `/stats` | administrateur |
| `GET` | `/docs`, `/openapi.json` | public |

Les erreurs sont toujours au format `{"status": 404, "code": "film_not_found", "message": "..."}`.
La description complète (paramètres, corps, exemples, codes d'erreur) est dans [`docs/openapi.json`](docs/openapi.json).

## Architecture du projet

### Place dans l'application

L'application est déployée sur trois machines. Seul le pare-feu est joignable depuis l'extérieur :

```
Navigateur ──HTTP :80──> Pare-feu ──> Tiers présentation (site Flask)
                         10.11.2.227    10.11.2.225:5000
                             ^                │
                             └──── :5000 ─────┘  HTTP + JSON + jeton JWT
                             │
                             └──> Tiers données (ce dépôt)
                                  10.11.2.226:5000  api ──> mongo
```

- **Pare-feu (nftables) :** il relaie chaque connexion autorisée (DNAT et masquerade) et refuse tout le reste. Sur cette VM, le port 5000 n'est accepté que s'il vient du pare-feu.
- **Conteneur `api` :** il est le seul à joindre `mongo`, par le réseau Docker interne `data-net`.
- **Conteneur `mongo` :** son port 27017 n'est jamais publié, et ses données sont dans le volume `mongo-data`.

### Organisation du dépôt

```
videotheque-api
├── docker-compose.yml     services mongo et api, réseaux data-net (interne) et api-net
├── Dockerfile             image rt0705-api (python:3.14-slim)
├── requirements.txt       flask, pymongo, pyjwt
├── .env.exemple           modèle du fichier .env (secrets, non versionné)
├── app.py                 création de l'application, blueprints, initialisation
├── db.py                  connexion MongoDB, collections, verrou d'écriture, import de départ
├── utils.py               erreurs JSON, conversion des ObjectId, validation des données
├── auth.py                jetons JWT et décorateurs de droits
├── routes
│   ├── films.py           /films et recherche
│   ├── users.py           /login et /users
│   ├── favorites.py       /users/{id}/favorites
│   └── docs.py            /docs (Swagger UI) et /openapi.json
├── docs
│   └── openapi.json       spécification OpenAPI 3.0
├── data
│   └── videotheque.json   films de départ et administrateur initial
├── tools
│   ├── import_tmdb.py     construction ou complément du catalogue depuis TMDb
│   └── fetch_posters.py   ajout des affiches manquantes
└── tests                  tests de l'API en bash et curl (168 vérifications)
```

### Modèle de données

Base `videotheque`, avec deux collections :

```jsonc
// films
{
  "_id": "665f1c2ab3d4e5f6a7b8c9d0",
  "title": "Pulp Fiction",
  "description": "…",
  "director": {"last_name": "Tarantino", "first_name": "Quentin"},
  "actors": [{"last_name": "Travolta", "first_name": "John"}],
  "genres": ["Policier", "Drame"],
  "year": 1994,
  "supports": [{"type": "bluray", "location": "Étagère A3"}],
  "poster_url": "https://image.tmdb.org/t/p/w500/…"
}

// users (password_hash n'est jamais renvoyé par l'API)
{
  "_id": "665f1c2ab3d4e5f6a7b8c9d1",
  "email": "admin@example.org",
  "username": "admin",
  "password_hash": "scrypt:…",
  "roles": ["user", "admin"],
  "favorites": ["665f1c2ab3d4e5f6a7b8c9d0"]
}
```

## Installation du projet

### Prérequis

- Une machine Linux avec **Docker** et **Docker Compose** (testé sur Ubuntu Server 24.04).
- Ton utilisateur dans le groupe `docker` :
  ```bash
  sudo usermod -aG docker $USER   # puis se reconnecter
  ```

### 1. Récupérer le projet

```bash
git clone https://github.com/SenaiSensei/videotheque-api.git
cd videotheque-api
```

### 2. Configurer les secrets

```bash
cp .env.exemple .env
```

Remplace ensuite les valeurs `change-moi` de `.env` :

| Variable | Rôle |
|---|---|
| `MONGO_ROOT_USER` | utilisateur root de MongoDB |
| `MONGO_ROOT_PASSWORD` | mot de passe root de MongoDB (appliqué seulement à la création du volume) |
| `JWT_SECRET` | clé de signature des jetons, par exemple `python3 -c "import secrets; print(secrets.token_hex(32))"` |

Le fichier `.env` n'est pas versionné (`.gitignore`).

### 3. Lancer l'API

```bash
docker compose up -d --build
docker compose logs api       # « init_db : 235 films et 1 comptes importés » au premier lancement
```

L'API écoute sur le port **5000** de la machine. Pour vérifier :

```bash
curl -i http://127.0.0.1:5000/films     # 401 attendu : un jeton est nécessaire
```

Le compte administrateur initial est `admin@example.org`. Son mot de passe n'est pas dans le dépôt : seul son hash est dans `data/videotheque.json`.

### 4. Relier le tiers présentation

Sur la machine du site, dans le `.env` de [videotheque-serveur](https://github.com/SenaiSensei/videotheque-serveur), `API_URL` doit pointer vers cette API :
- en déploiement avec pare-feu : `API_URL=http://10.11.2.227:5000` ;
- sans pare-feu : `API_URL=http://<IP de cette machine>:5000`.

### 5. Documentation Swagger

- Par le pare-feu, depuis le VPN : `http://10.11.2.227:8080/docs`.
- Par un tunnel SSH :
  ```bash
  ssh -N -L 5001:127.0.0.1:5000 <utilisateur>@10.11.2.226
  # puis http://localhost:5001/docs
  ```

Pour l'utiliser : lance `POST /login`, copie le `token` de la réponse, clique sur **Authorize** et colle le jeton.

### 6. Lancer les tests

Les tests se lancent sur la machine de l'API :

```bash
./tests/run_all.sh            # bilan par script
./tests/run_all.sh detail     # chaque vérification
```

Le mot de passe administrateur est demandé une seule fois. Les tests créent leurs propres comptes et films, puis les suppriment.

### Réinitialiser ou remplir la base

```bash
# Repartir de data/videotheque.json (efface toutes les données)
docker compose down -v && docker compose up -d

# Construire le catalogue depuis TMDb (clé gratuite sur themoviedb.org)
docker compose exec -e TMDB_API_KEY=ta_cle api python tools/import_tmdb.py --top 200 --popular 40 --replace --seed --dry-run
docker compose exec -e TMDB_API_KEY=ta_cle api python tools/import_tmdb.py --top 200 --popular 40 --replace --seed
```

`--dry-run` affiche ce qui serait importé, sans rien enregistrer.
`--replace` remplace tous les films et vide les favoris. Les comptes sont conservés.