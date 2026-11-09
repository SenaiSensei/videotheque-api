import re

from flask import Blueprint, jsonify, request
from pymongo import ASCENDING, ReturnDocument

from auth import admin_required, login_required
from db import films, users, write_lock
from utils import (SUPPORT_TYPES, ApiError, get_json_body, invalid, serialize,
                   to_object_id, validate_film)

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
    found = films.find(build_search_query(request.args)).sort("title", ASCENDING)
    return jsonify({"films": serialize(list(found))})


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