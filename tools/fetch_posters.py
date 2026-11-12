"""Récupère une affiche (poster_url) pour chaque film qui n'en a pas.

À lancer dans le conteneur api, depuis le dossier API :
    docker compose exec api python tools/fetch_posters.py --dry-run
    docker compose exec api python tools/fetch_posters.py

Sources :
 - TMDb si la variable TMDB_API_KEY est définie (clé v3 ou jeton v4)
 - sinon Wikipédia (recherche sur fr.wikipedia, image de la page en.wikipedia)
   Wikimédia exige un contact dans le User-Agent : variable WIKI_CONTACT (email ou URL)
     docker compose exec -e WIKI_CONTACT=prenom.nom@etudiant.univ-reims.fr api python tools/fetch_posters.py

Le script met à jour :
 - la base MongoDB (si MONGO_URI est défini), sans toucher aux autres données
 - le fichier de départ data/videotheque.json, pour les prochaines réinitialisations

Options :
 --dry-run : affiche les correspondances sans rien enregistrer
 --force   : remplace aussi les affiches déjà présentes
 --no-db   : ne modifie que le fichier JSON
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_FILE = os.environ.get("SEED_FILE") or os.path.join(BASE_DIR, "data", "videotheque.json")
CONTACT = os.environ.get("WIKI_CONTACT", "").strip()
USER_AGENT = "RT0705-videotheque/1.0 (TP universitaire" + (f"; {CONTACT}" if CONTACT else "") + ") python-urllib"
TIMEOUT = 10
MAX_TRIES = 3
PAUSE = 1.0  # secondes entre deux films


class RateLimited(Exception):
    pass


def get_json(url, params, headers=None):
    full_url = url + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(full_url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    for attempt in range(1, MAX_TRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in (429, 503):
                raise
            body = error.read(300).decode("utf-8", "replace").strip().replace("\n", " ")
            if attempt == MAX_TRIES:
                raise RateLimited(f"HTTP {error.code} : {body}") from None
            retry_after = error.headers.get("Retry-After", "")
            wait = min(int(retry_after), 30) if retry_after.isdigit() else 5 * attempt
            time.sleep(wait)


# ---------- TMDb ----------

def tmdb_poster(film, api_key):
    params = {"query": film["title"], "language": "fr-FR"}
    headers = {}
    if len(api_key) > 40:  # jeton de lecture v4
        headers["Authorization"] = "Bearer " + api_key
    else:  # clé v3
        params["api_key"] = api_key
    if film.get("year"):
        params["year"] = film["year"]

    data = get_json("https://api.themoviedb.org/3/search/movie", params, headers)
    for result in data.get("results", []):
        if result.get("poster_path"):
            label = f"{result.get('title')} ({(result.get('release_date') or '')[:4]})"
            return "https://image.tmdb.org/t/p/w500" + result["poster_path"], label
    return None, None


# ---------- Wikipédia ----------

WIKI_FR = "https://fr.wikipedia.org/w/api.php"
WIKI_EN = "https://en.wikipedia.org/w/api.php"


def wiki_search(api, query):
    data = get_json(api, {
        "action": "query", "format": "json", "formatversion": 2,
        "list": "search", "srsearch": query, "srlimit": 1,
    })
    results = data.get("query", {}).get("search", [])
    return results[0]["title"] if results else None


def wiki_english_title(fr_title):
    data = get_json(WIKI_FR, {
        "action": "query", "format": "json", "formatversion": 2,
        "titles": fr_title, "prop": "langlinks", "lllang": "en", "redirects": 1,
    })
    for page in data.get("query", {}).get("pages", []):
        for link in page.get("langlinks", []):
            return link.get("title")
    return None


def wiki_image(api, title):
    data = get_json(api, {
        "action": "query", "format": "json", "formatversion": 2,
        "titles": title, "prop": "pageimages", "piprop": "thumbnail",
        "pithumbsize": 500, "pilicense": "any", "redirects": 1,
    })
    for page in data.get("query", {}).get("pages", []):
        thumbnail = page.get("thumbnail")
        if thumbnail:
            return thumbnail.get("source")
    return None


def wikipedia_poster(film):
    year = film.get("year") or ""

    # 1. Page française, puis son équivalent anglais (les affiches y sont presque toujours)
    fr_title = wiki_search(WIKI_FR, f"{film['title']} film {year}")
    if fr_title:
        en_title = wiki_english_title(fr_title)
        if en_title:
            url = wiki_image(WIKI_EN, en_title)
            if url:
                return url, f"fr:{fr_title} -> en:{en_title}"

    # 2. Recherche directe sur la version anglaise
    en_title = wiki_search(WIKI_EN, f"{film['title']} {year} film")
    if en_title:
        url = wiki_image(WIKI_EN, en_title)
        if url:
            return url, f"en:{en_title}"

    # 3. Image de la page française, à défaut
    if fr_title:
        url = wiki_image(WIKI_FR, fr_title)
        if url:
            return url, f"fr:{fr_title}"
    return None, None


# ---------- Enregistrement ----------

def open_collection():
    uri = os.environ.get("MONGO_URI")
    if not uri:
        return None
    from pymongo import MongoClient
    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    return client.get_default_database()["films"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-db", action="store_true")
    args = parser.parse_args()

    with open(SEED_FILE, encoding="utf-8") as f:
        seed = json.load(f)
    seed_films = seed.get("films", [])

    collection = None if args.no_db else open_collection()
    if collection is not None:
        films = list(collection.find({}, {"title": 1, "year": 1, "poster_url": 1}))
        print(f"{len(films)} films lus dans MongoDB")
    else:
        films = seed_films
        print(f"{len(films)} films lus dans {SEED_FILE}")

    api_key = os.environ.get("TMDB_API_KEY", "").strip()
    print("Source : " + ("TMDb" if api_key else "Wikipédia") + ("  (simulation)" if args.dry_run else ""))
    print()

    print("User-Agent : " + USER_AGENT)
    print()

    found = {}  # (titre, année) -> url
    missing = []
    limited = 0  # films refusés d'affilée pour excès de requêtes
    for film in films:
        key = (film["title"], film.get("year"))
        if film.get("poster_url") and not args.force:
            print(f"  =  {film['title']} ({film.get('year')}) : déjà renseignée")
            continue
        try:
            url, label = tmdb_poster(film, api_key) if api_key else wikipedia_poster(film)
            limited = 0
        except RateLimited as error:
            url, label = None, f"refusé par le serveur ({error})"
            limited += 1
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            url, label = None, f"erreur : {error}"
        if limited >= 3:
            print(f"  -  {film['title']} ({film.get('year')}) : {label}")
            print()
            print("Arrêt : le serveur refuse toutes les requêtes (HTTP 429).")
            if not api_key:
                print("Ajoute un contact au User-Agent : -e WIKI_CONTACT=ton.email@etudiant.univ-reims.fr")
                print("ou utilise TMDb : -e TMDB_API_KEY=ta_cle")
            print("Les affiches déjà trouvées sont enregistrées ci-dessous.")
            break
        if url:
            found[key] = url
            print(f"  +  {film['title']} ({film.get('year')})  <=  {label}")
            print(f"       {url}")
        else:
            missing.append(film["title"])
            print(f"  -  {film['title']} ({film.get('year')}) : rien trouvé {label or ''}")
        time.sleep(PAUSE)

    print()
    print(f"{len(found)} affiches trouvées, {len(missing)} films sans affiche")
    if args.dry_run or not found:
        return

    if collection is not None:
        updated = 0
        for film in films:
            url = found.get((film["title"], film.get("year")))
            if url:
                updated += collection.update_one({"_id": film["_id"]}, {"$set": {"poster_url": url}}).modified_count
        print(f"MongoDB : {updated} films mis à jour")

    changed = 0
    for film in seed_films:
        url = found.get((film["title"], film.get("year")))
        if url and film.get("poster_url") != url:
            film["poster_url"] = url
            changed += 1
    if changed:
        with open(SEED_FILE, "w", encoding="utf-8") as f:
            json.dump(seed, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print(f"{os.path.relpath(SEED_FILE, BASE_DIR)} : {changed} films mis à jour")


if __name__ == "__main__":
    sys.exit(main())