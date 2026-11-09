from flask import Blueprint, g, jsonify, request

from auth import owner_required
from db import films, users, write_lock
from utils import ApiError, get_json_body, serialize, to_object_id

bp = Blueprint("favorites", __name__)


def favorites_response(user_id, status=200):
    user = users.find_one({"_id": user_id}, {"favorites": 1})
    return jsonify({"favorites": serialize(user["favorites"])}), status


@bp.get("/users/<user_id>/favorites")
@owner_required
def list_favorites(user_id):
    ids = g.user["favorites"]
    found = {f["_id"]: f for f in films.find({"_id": {"$in": ids}})}
    # Ordre d'ajout conservé, et favoris orphelins ignorés
    return jsonify({"films": serialize([found[i] for i in ids if i in found])})


@bp.post("/users/<user_id>/favorites")
@owner_required
def add_favorite(user_id):
    film_id = to_object_id(get_json_body(request).get("film_id"))
    with write_lock:
        if films.find_one({"_id": film_id}, {"_id": 1}) is None:
            raise ApiError(404, "film_not_found", "Film introuvable")
        result = users.update_one({"_id": g.user["_id"]}, {"$addToSet": {"favorites": film_id}})
    return favorites_response(g.user["_id"], 201 if result.modified_count else 200)


@bp.delete("/users/<user_id>/favorites/<film_id>")
@owner_required
def remove_favorite(user_id, film_id):
    oid = to_object_id(film_id, "film_not_found")
    with write_lock:
        users.update_one({"_id": g.user["_id"]}, {"$pull": {"favorites": oid}})
    return favorites_response(g.user["_id"])