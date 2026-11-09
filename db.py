import json
import os
import threading

from pymongo import ASCENDING, MongoClient
from werkzeug.security import generate_password_hash

client = MongoClient(os.environ["MONGO_URI"], serverSelectionTimeoutMS=3000)
db = client.get_default_database()

films = db["films"]
users = db["users"]

# Une seule écriture à la fois dans le processus api
write_lock = threading.Lock()


def init_db():
    """Crée les index et remplit une base vide à partir du fichier de départ."""
    users.create_index([("email", ASCENDING)], unique=True)
    users.create_index([("username", ASCENDING)], unique=True)
    films.create_index([("title", ASCENDING)])

    if films.count_documents({}) or users.count_documents({}):
        return

    seed_file = os.environ.get("SEED_FILE")
    if not seed_file or not os.path.exists(seed_file):
        print("init_db : aucun fichier de départ, base laissée vide")
        return

    with open(seed_file, encoding="utf-8") as f:
        seed = json.load(f)

    seed_films = [{k: v for k, v in film.items() if k != "_id"} for film in seed.get("films", [])]
    if seed_films:
        films.insert_many(seed_films)

    seed_users = []
    for user in seed.get("users", []):
        password_hash = user.get("password_hash") or generate_password_hash(user["password"])
        seed_users.append({
            "email": user["email"].strip().lower(),
            "username": user["username"].strip(),
            "password_hash": password_hash,
            "roles": user.get("roles", ["user"]),
            "favorites": [],
        })
    if seed_users:
        users.insert_many(seed_users)

    print(f"init_db : {len(seed_films)} films et {len(seed_users)} comptes importés")