from flask import Blueprint, g, jsonify, request
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash, generate_password_hash

from auth import (admin_required, create_token, owner_or_admin_required,
                  owner_required)
from db import users, write_lock
from ratelimit import login_limiter
from utils import (ApiError, get_json_body, paginated, pagination_args,
                   public_user, to_object_id, validate_email, validate_password,
                   validate_roles, validate_username)

bp = Blueprint("users", __name__)

# Hash factice : la connexion prend le même temps, que l'email existe ou non
DUMMY_HASH = generate_password_hash("mot-de-passe-factice")


def user_not_found():
    return ApiError(404, "user_not_found", "Compte introuvable")


def duplicate_error(err):
    """Traduit une violation d'index unique en 409 email_taken ou username_taken."""
    key = (err.details or {}).get("keyValue", {})
    if "email" in key or "email" in str(err):
        return ApiError(409, "email_taken", "Email déjà utilisé")
    return ApiError(409, "username_taken", "Nom d'utilisateur déjà utilisé")


def last_admin():
    return ApiError(409, "last_admin", "Opération impossible sur le dernier administrateur")


def is_last_admin(user):
    return "admin" in user["roles"] and users.count_documents({"roles": "admin"}) <= 1


def auth_response(user, status):
    return jsonify({"token": create_token(user["_id"]), "user": public_user(user)}), status


@bp.post("/login")
def login():
    data = get_json_body(request)
    email = validate_email(data)
    password = data.get("password")
    if not isinstance(password, str) or not password:
        raise ApiError(400, "invalid_data", "Le champ password est obligatoire")

    wait = login_limiter.retry_after(email)
    if wait:
        raise ApiError(429, "too_many_attempts",
                       f"Trop de tentatives de connexion. Réessayez dans {wait} secondes.")

    user = users.find_one({"email": email})
    password_ok = check_password_hash(user["password_hash"] if user else DUMMY_HASH, password)
    if not user or not password_ok:
        login_limiter.record_failure(email)
        raise ApiError(401, "invalid_credentials", "Identifiants incorrects")
    login_limiter.reset(email)
    return auth_response(user, 200)


@bp.get("/users")
@admin_required
def list_users():
    page, per_page = pagination_args(request.args, default_per_page=20)
    total = users.count_documents({})
    found = (users.find({}, {"password_hash": 0}).sort("username", ASCENDING)
             .skip((page - 1) * per_page).limit(per_page))
    return jsonify(paginated([public_user(u) for u in found], "users", page, per_page, total))


@bp.post("/users")
def register():
    data = get_json_body(request)
    user = {
        "email": validate_email(data),
        "username": validate_username(data),
        "password_hash": generate_password_hash(validate_password(data)),
        "roles": ["user"],
        "favorites": [],
    }
    try:
        result = users.insert_one(user)
    except DuplicateKeyError as err:
        raise duplicate_error(err)
    user["_id"] = result.inserted_id
    return auth_response(user, 201)


@bp.get("/users/<user_id>")
@owner_or_admin_required
def get_user(user_id):
    user = users.find_one({"_id": to_object_id(user_id, "user_not_found")})
    if user is None:
        raise user_not_found()
    return jsonify(public_user(user))


@bp.put("/users/<user_id>")
@owner_required
def update_user(user_id):
    data = get_json_body(request)
    changes = {"username": validate_username(data)}

    if "current_password" in data or "new_password" in data:
        current = data.get("current_password")
        new = validate_password(data, "new_password")
        if not isinstance(current, str) or not check_password_hash(g.user["password_hash"], current):
            raise ApiError(401, "invalid_password", "Mot de passe actuel incorrect")
        changes["password_hash"] = generate_password_hash(new)

    try:
        user = users.find_one_and_update(
            {"_id": g.user["_id"]}, {"$set": changes},
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError as err:
        raise duplicate_error(err)
    if user is None:
        raise user_not_found()
    return jsonify(public_user(user))


@bp.delete("/users/<user_id>")
@owner_or_admin_required
def delete_user(user_id):
    oid = to_object_id(user_id, "user_not_found")
    with write_lock:
        user = users.find_one({"_id": oid})
        if user is None:
            raise user_not_found()
        if is_last_admin(user):
            raise last_admin()
        users.delete_one({"_id": oid})
    return jsonify({"message": "Compte supprimé"})


@bp.put("/users/<user_id>/roles")
@admin_required
def update_roles(user_id):
    oid = to_object_id(user_id, "user_not_found")
    roles = validate_roles(get_json_body(request))
    with write_lock:
        user = users.find_one({"_id": oid})
        if user is None:
            raise user_not_found()
        if "admin" not in roles and is_last_admin(user):
            raise last_admin()
        user = users.find_one_and_update(
            {"_id": oid}, {"$set": {"roles": roles}},
            return_document=ReturnDocument.AFTER,
        )
    return jsonify(public_user(user))