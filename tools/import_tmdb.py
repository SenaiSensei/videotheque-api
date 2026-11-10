"""Construit ou complète le catalogue de la vidéothèque à partir de TMDb.

Pour chaque film : titre, résumé, année, réalisateur, acteurs principaux,
genres et affiche, en français. TMDb ne connaît pas les supports physiques :
le script en invente un ou deux (dvd, bluray, digital) pour avoir des données de test.

Chaque film passe par validate_film (utils.py), comme un POST /films.
Un film déjà présent (même titre et même année) n'est pas ajouté une seconde fois.

À lancer dans le conteneur api, depuis le dossier API.

Construire la base de départ (remplace tous les films, garde les comptes) :
    docker compose exec -e TMDB_API_KEY=ta_cle api python tools/import_tmdb.py --top 100 --popular 40 --replace --seed --dry-run
    docker compose exec -e TMDB_API_KEY=ta_cle api python tools/import_tmdb.py --top 100 --popular 40 --replace --seed

Ajouter des films à la base existante :
    docker compose exec -e TMDB_API_KEY=ta_cle api python tools/import_tmdb.py --search "Dune" --seed

Choix des films (combinables) :
 --top N       : les N films les mieux notés
 --popular N   : les N films les plus populaires du moment
 --search TXT  : le premier résultat d'une recherche par titre (option répétable)
 --id N        : un film par son identifiant TMDb (option répétable)

Autres options :
 --actors N : nombre d'acteurs gardés par film (5 par défaut)
 --seed     : écrit aussi les films dans data/videotheque.json (fichier de départ)
 --replace  : remplace tous les films au lieu d'en ajouter. Dans MongoDB, les anciens films
              sont supprimés et les favoris vidés (ils pointaient vers ces films).
              Dans data/videotheque.json, la liste films est remplacée, users est conservée.
 --no-db    : ne touche pas à MongoDB (seul le fichier est modifié avec --seed)
 --dry-run  : affiche les films sans rien enregistrer
"""

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from utils import ApiError, validate_film  # noqa: E402

SEED_FILE = os.environ.get("SEED_FILE") or os.path.join(BASE_DIR, "data", "videotheque.json")
TMDB_API = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
LANGUAGE = "fr-FR"
TIMEOUT = 10
PAGE_SIZE = 20  # résultats par page dans les listes TMDb

# Noms de genres TMDb -> noms déjà utilisés dans la base
GENRE_NAMES = {
    "Science-Fiction": "Science-fiction",
    "Crime": "Policier",
    "Histoire": "Historique",
    "Musique": "Musical",
    "Familial": "Famille",
    "Mystère": "Mystère",
    "Téléfilm": "Téléfilm",
}

# Particules rattachées au nom de famille : "Guillermo del Toro" -> del Toro
PARTICLES = {"de", "del", "della", "der", "di", "da", "du", "des", "la", "le", "van", "von", "den", "ter", "st."}

SHELVES = ["A", "B", "C", "D", "E"]


class Tmdb:
    def __init__(self, key):
        self.key = key

    def get(self, path, **params):
        headers = {"Accept": "application/json"}
        if len(self.key) > 40:  # jeton de lecture v4
            headers["Authorization"] = "Bearer " + self.key
        else:  # clé v3
            params["api_key"] = self.key
        url = f"{TMDB_API}{path}?{urllib.parse.urlencode(params)}"
        for attempt in range(1, 4):
            try:
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                if error.code == 401:
                    sys.exit("TMDb refuse la clé (401) : vérifie TMDB_API_KEY")
                if error.code != 429 or attempt == 3:
                    raise
                retry_after = error.headers.get("Retry-After", "")
                time.sleep(int(retry_after) if retry_after.isdigit() else 2 * attempt)

    def list_ids(self, path, count):
        ids = []
        page = 1
        while len(ids) < count:
            data = self.get(path, language=LANGUAGE, page=page)
            ids += [movie["id"] for movie in data.get("results", [])]
            if page >= data.get("total_pages", 1):
                break
            page += 1
        return ids[:count]

    def search_id(self, title):
        results = self.get("/search/movie", query=title, language=LANGUAGE).get("results", [])
        return results[0]["id"] if results else None

    def movie(self, movie_id):
        return self.get(f"/movie/{movie_id}", language=LANGUAGE, append_to_response="credits")


def split_name(full_name):
    """'Samuel L. Jackson' -> {first_name: 'Samuel L.', last_name: 'Jackson'}"""
    words = full_name.split()
    if len(words) <= 1:
        return {"first_name": "", "last_name": full_name.strip()}
    start = len(words) - 1
    while start > 1 and words[start - 1].lower() in PARTICLES:
        start -= 1
    return {"first_name": " ".join(words[:start]), "last_name": " ".join(words[start:])}


def fake_supports(movie_id):
    """Un ou deux supports, toujours les mêmes pour un film donné."""
    rng = random.Random(movie_id)
    types = rng.sample(["dvd", "bluray", "digital"], rng.choice([1, 2]))
    supports = []
    for kind in types:
        location = "Serveur NAS" if kind == "digital" else f"Étagère {rng.choice(SHELVES)}{rng.randint(1, 9)}"
        supports.append({"type": kind, "location": location})
    return supports


def to_film(movie, tmdb, actor_count):
    """Convertit un film TMDb en Film de la vidéothèque, ou lève ValueError."""
    year = (movie.get("release_date") or "")[:4]
    if not year.isdigit():
        raise ValueError("pas de date de sortie")

    crew = movie.get("credits", {}).get("crew", [])
    directors = [person["name"] for person in crew if person.get("job") == "Director"]
    if not directors:
        raise ValueError("pas de réalisateur")

    description = (movie.get("overview") or "").strip()
    if not description:  # pas de résumé en français : on prend l'anglais
        description = (tmdb.get(f"/movie/{movie['id']}", language="en-US").get("overview") or "").strip()
    if len(description) > 2000:
        description = description[:1997].rsplit(" ", 1)[0] + "..."

    cast = sorted(movie.get("credits", {}).get("cast", []), key=lambda person: person.get("order", 99))

    film = {
        "title": movie.get("title") or movie.get("original_title"),
        "description": description,
        "year": int(year),
        "director": split_name(directors[0]),
        "actors": [split_name(person["name"]) for person in cast[:actor_count]],
        "genres": [GENRE_NAMES.get(g["name"], g["name"]) for g in movie.get("genres", [])],
        "supports": fake_supports(movie["id"]),
        "poster_url": IMAGE_BASE + movie["poster_path"] if movie.get("poster_path") else "",
    }
    try:
        return validate_film(film)
    except ApiError as error:
        raise ValueError(error.message) from None


def film_key(film):
    return (film["title"].strip().lower(), film.get("year"))


def open_collection():
    uri = os.environ.get("MONGO_URI")
    if not uri:
        return None
    from pymongo import MongoClient
    return MongoClient(uri, serverSelectionTimeoutMS=3000).get_default_database()["films"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--top", type=int, default=0)
    parser.add_argument("--popular", type=int, default=0)
    parser.add_argument("--search", action="append", default=[])
    parser.add_argument("--id", type=int, action="append", default=[])
    parser.add_argument("--actors", type=int, default=5)
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--no-db", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    key = os.environ.get("TMDB_API_KEY", "").strip()
    if not key:
        sys.exit("Variable TMDB_API_KEY absente : docker compose exec -e TMDB_API_KEY=ta_cle api python ...")
    if not (args.top or args.popular or args.search or args.id):
        parser.error("indique au moins --top, --popular, --search ou --id")
    tmdb = Tmdb(key)

    # Identifiants TMDb à importer, sans doublon et dans l'ordre demandé
    ids = list(args.id)
    if args.top:
        ids += tmdb.list_ids("/movie/top_rated", args.top)
    if args.popular:
        ids += tmdb.list_ids("/movie/popular", args.popular)
    for title in args.search:
        movie_id = tmdb.search_id(title)
        if movie_id:
            ids.append(movie_id)
        else:
            print(f"  -  « {title} » : aucun résultat")
    ids = list(dict.fromkeys(ids))

    collection = None if args.no_db else open_collection()
    with open(SEED_FILE, encoding="utf-8") as f:
        seed = json.load(f)
    if args.replace:
        existing = set()
    elif collection is not None:
        existing = {film_key(f) for f in collection.find({}, {"title": 1, "year": 1})}
    else:
        existing = {film_key(f) for f in seed.get("films", [])}

    mode = "remplacement du catalogue" if args.replace else f"{len(existing)} films déjà dans la base"
    print(f"{len(ids)} films à traiter, {mode}" + ("  (simulation)" if args.dry_run else ""))
    print()

    new_films = []
    skipped = 0
    for movie_id in ids:
        try:
            film = to_film(tmdb.movie(movie_id), tmdb, args.actors)
        except (ValueError, urllib.error.URLError, TimeoutError) as error:
            print(f"  -  TMDb {movie_id} : ignoré ({error})")
            continue
        label = f"{film['title']} ({film['year']})"
        if film_key(film) in existing:
            skipped += 1
            print(f"  =  {label} : déjà présent")
            continue
        existing.add(film_key(film))
        new_films.append(film)
        director = f"{film['director']['first_name']} {film['director']['last_name']}".strip()
        print(f"  +  {label} - {director} - {', '.join(film['genres'])}")
        time.sleep(0.05)

    print()
    print(f"{len(new_films)} films à ajouter, {skipped} déjà présents")
    if args.dry_run or not new_films:
        return

    if collection is not None:
        if args.replace:
            removed = collection.delete_many({}).deleted_count
            collection.database["users"].update_many({}, {"$set": {"favorites": []}})
            print(f"MongoDB : {removed} anciens films supprimés, favoris vidés")
        collection.insert_many([dict(film) for film in new_films])  # copie : insert_many ajoute _id
        print(f"MongoDB : {len(new_films)} films ajoutés")
    elif not args.no_db:
        print("MONGO_URI absent : base non modifiée")

    if args.seed:
        if args.replace:
            added = new_films
            seed["films"] = added
        else:
            seed_keys = {film_key(f) for f in seed.get("films", [])}
            added = [f for f in new_films if film_key(f) not in seed_keys]
            seed.setdefault("films", []).extend(added)
        seed.setdefault("users", [])
        with open(SEED_FILE, "w", encoding="utf-8") as f:
            json.dump(seed, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"{os.path.relpath(SEED_FILE, BASE_DIR)} : {len(added)} films écrits")


if __name__ == "__main__":
    sys.exit(main())