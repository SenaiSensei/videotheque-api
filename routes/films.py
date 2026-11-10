import re

from flask import Blueprint, jsonify, request
from pymongo import ASCENDING, ReturnDocument

from auth import admin_required, login_required
from db import films, users, write_lock
from utils import (SUPPORT_TYPES, ApiError, get_json_body, invalid, paginated,
                   pagination_args, serialize, to_object_id, validate_film)

bp = Blueprint("films", __name__)


def film_not_found():
    return ApiError(404, "film_not_found", "Film introuvable")


def contains(value):
    """Recherche partielle, insensible à la casse, avec la saisie échappée."""
    return {"$regex": re.escape(value), "$options": "i"}


def person_filter(field, value):
    """Cherche dans le nom ou le prénom d'une personne (director ou actors)."""
    return {"$or": [
        {f"{field}.last_name": contains(value)},
        {f"{field}.first_name": contains(value)},
    ]}


def build_search_query(args):
    """Construit la requête MongoDB à partir des filtres de l'URL."""
    conditions = []

    title = args.get("title", "").strip()
    if title:
        conditions.append({"title": contains(title)})

    for param, field in (("director", "director"), ("actor", "actors")):
        value = args.get(param, "").strip()
        if value:
            conditions.append(person_filter(field, value))

    genre = args.get("genre", "").strip()
    if genre:
        conditions.append({"genres": {"$regex": f"^{re.escape(genre)}$", "$options": "i"}})

    year = args.get("year", "").strip()
    if year:
        if not year.isdigit():
            raise invalid("year doit être un entier")
        conditions.append({"year": int(year)})

    support = args.get("support", "").strip()
    if support:
        if support not in SUPPORT_TYPES:
            raise invalid(f"support doit valoir {', '.join(SUPPORT_TYPES)}")
        conditions.append({"supports.type": support})

    return {"$and": conditions} if conditions else {}


@bp.get("/films")
@login_required
def list_films():
    query = build_search_query(request.args)
    page, per_page = pagination_args(request.args, default_per_page=24)
    total = films.count_documents(query)
    cursor = (films.find(query).sort("title", ASCENDING)
              .skip((page - 1) * per_page).limit(per_page))
    return jsonify(paginated(serialize(list(cursor)), "films", page, per_page, total))


@bp.get("/films/genres")
@login_required
def list_genres():
    """Liste des genres du catalogue, sans doublon de casse (pour le filtre)."""
    seen = {}
    for genre in films.distinct("genres"):
        seen.setdefault(genre.casefold(), genre)
    return jsonify({"genres": sorted(seen.values(), key=str.casefold)})


@bp.get("/stats")
@admin_required
def stats():
    """Chiffres du tableau de bord, calculés par MongoDB (sans tout rapatrier)."""
    agg = list(users.aggregate([
        {"$group": {"_id": None, "total": {"$sum": {"$size": "$favorites"}}}},
    ]))
    return jsonify({
        "films": films.count_documents({}),
        "users": users.count_documents({}),
        "admins": users.count_documents({"roles": "admin"}),
        "favorites": agg[0]["total"] if agg else 0,
        "supports": {kind: films.count_documents({"supports.type": kind}) for kind in SUPPORT_TYPES},
        "without_support": films.count_documents({"supports": {"$size": 0}}),
    })


@bp.post("/films")
@admin_required
def create_film():
    film = validate_film(get_json_body(request))
    film["_id"] = films.insert_one(film).inserted_id
    return jsonify(serialize(film)), 201


@bp.get("/films/<film_id>")
@login_required
def get_film(film_id):
    film = films.find_one({"_id": to_object_id(film_id, "film_not_found")})
    if film is None:
        raise film_not_found()
    return jsonify(serialize(film))


@bp.put("/films/<film_id>")
@admin_required
def update_film(film_id):
    oid = to_object_id(film_id, "film_not_found")
    data = validate_film(get_json_body(request))
    film = films.find_one_and_update(
        {"_id": oid}, {"$set": data}, return_document=ReturnDocument.AFTER,
    )
    if film is None:
        raise film_not_found()
    return jsonify(serialize(film))


@bp.delete("/films/<film_id>")
@admin_required
def delete_film(film_id):
    oid = to_object_id(film_id, "film_not_found")
    with write_lock:
        if films.delete_one({"_id": oid}).deleted_count == 0:
            raise film_not_found()
        users.update_many({"favorites": oid}, {"$pull": {"favorites": oid}})
    return jsonify({"message": "Film supprimé"})