import re

from bson import ObjectId
from flask import jsonify
from pymongo.errors import PyMongoError
from werkzeug.exceptions import HTTPException

SUPPORT_TYPES = ("dvd", "bluray", "digital")
ROLES = ("user", "admin")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
OBJECT_ID_RE = re.compile(r"^[0-9a-f]{24}$")


# Erreurs

class ApiError(Exception):
    """Erreur renvoyée au client sous la forme {"code": ..., "message": ...}."""

    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def invalid(message):
    return ApiError(400, "invalid_data", message)


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(err):
        return jsonify({"status": err.status, "code": err.code, "message": err.message}), err.status

    @app.errorhandler(HTTPException)
    def handle_http_error(err):
        codes = {404: "not_found", 405: "method_not_allowed"}
        return jsonify({"status": err.code, "code": codes.get(err.code, "http_error"),
                        "message": err.description}), err.code

    @app.errorhandler(PyMongoError)
    def handle_mongo_error(err):
        app.logger.exception(err)
        return jsonify({"status": 500, "code": "internal_error", "message": "Base de données indisponible"}), 500

    @app.errorhandler(Exception)
    def handle_unexpected_error(err):
        app.logger.exception(err)
        return jsonify({"status": 500, "code": "internal_error", "message": "Erreur interne"}), 500


# Identifiants

def to_object_id(value, not_found_code=None):
    """Convertit un texte en ObjectId.

    Dans une URI, un format invalide renvoie 404 (not_found_code).
    Dans un corps JSON, il renvoie 400 invalid_data.
    """
    if isinstance(value, str) and OBJECT_ID_RE.match(value):
        return ObjectId(value)
    if not_found_code:
        messages = {"film_not_found": "Film introuvable", "user_not_found": "Compte introuvable"}
        raise ApiError(404, not_found_code, messages.get(not_found_code, "Ressource introuvable"))
    raise invalid("Identifiant invalide")


def serialize(value):
    """Convertit récursivement les ObjectId en texte."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, list):
        return [serialize(val) for val in value]
    if isinstance(value, dict):
        return {key: serialize(val) for key, val in value.items()}
    return value


def public_user(user):
    """User public : sans password_hash, ObjectId convertis."""
    return serialize({key: val for key, val in user.items() if key != "password_hash"})

# Pagination

def pagination_args(args, default_per_page=24, max_per_page=100):
    """Lit page et per_page de la requête, avec des bornes sûres."""
    def positive(name, default):
        value = args.get(name, "")
        return int(value) if value.isdigit() and int(value) > 0 else default
    per_page = min(positive("per_page", default_per_page), max_per_page)
    return positive("page", 1), per_page


def paginated(items, key, page, per_page, total):
    """Réponse paginée : les éléments et les informations de page."""
    pages = max(1, -(-total // per_page))  # arrondi au supérieur
    return {key: items, "page": page, "per_page": per_page, "total": total, "pages": pages}


# Lecture du corps JSON

def get_json_body(request):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise invalid("Le corps de la requête doit être un objet JSON")
    return data


def get_str(data, key, required=True, min_len=0, max_len=200):
    value = data.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise invalid(f"Le champ {key} doit être une chaîne")
    value = value.strip()
    if required and not value:
        raise invalid(f"Le champ {key} est obligatoire")
    if not min_len <= len(value) <= max_len:
        raise invalid(f"Le champ {key} doit contenir entre {min_len} et {max_len} caractères")
    return value


# Validation des objets

def validate_email(data):
    email = get_str(data, "email", max_len=254).lower()
    if not EMAIL_RE.match(email):
        raise invalid("Format d'email invalide")
    return email


def validate_username(data):
    return get_str(data, "username", min_len=3, max_len=30)


def validate_password(data, key="password"):
    value = data.get(key)
    if not isinstance(value, str) or not 8 <= len(value) <= 128:
        raise invalid(f"Le champ {key} doit contenir entre 8 et 128 caractères")
    return value


def validate_person(value, field):
    if not isinstance(value, dict):
        raise invalid(f"{field} doit être un objet Person")
    return {
        "last_name": get_str(value, "last_name", max_len=100),
        "first_name": get_str(value, "first_name", required=False, max_len=100) or "",
    }


def validate_film(data):
    """Renvoie un Film propre, sans _id, ou lève invalid_data."""
    URL_RE = re.compile(r"^https?://[^\s<>\"']+$")

    year = data.get("year")
    if not isinstance(year, int) or isinstance(year, bool) or not 1888 <= year <= 2100:
        raise invalid("year doit être un entier entre 1888 et 2100")

    genres = data.get("genres", [])
    if not isinstance(genres, list) or not all(isinstance(g, str) and g.strip() for g in genres):
        raise invalid("genres doit être une liste de chaînes non vides")
    genres = list(dict.fromkeys(g.strip() for g in genres))

    actors = data.get("actors", [])
    if not isinstance(actors, list):
        raise invalid("actors doit être une liste de Person")

    supports = data.get("supports", [])
    if not isinstance(supports, list):
        raise invalid("supports doit être une liste de Support")
    clean_supports = []
    for support in supports:
        if not isinstance(support, dict) or support.get("type") not in SUPPORT_TYPES:
            raise invalid(f"Le type de support doit valoir {', '.join(SUPPORT_TYPES)}")
        clean_supports.append({"type": support["type"], "location": get_str(support, "location", max_len=500)})
    
    poster_url = get_str(data, "poster_url", required=False, max_len=500) or ""
    if poster_url and not URL_RE.match(poster_url):
        raise invalid("poster_url doit être une adresse http:// ou https://")

    return {
        "title": get_str(data, "title"),
        "description": get_str(data, "description", required=False, max_len=2000) or "",
        "director": validate_person(data.get("director"), "director"),
        "actors": [validate_person(a, "actors") for a in actors],
        "genres": genres,
        "year": year,
        "supports": clean_supports,
        "poster_url": poster_url
    }


def validate_roles(data):
    roles = data.get("roles")
    if (not isinstance(roles, list) or "user" not in roles
            or len(roles) != len(set(roles)) or any(role not in ROLES for role in roles)):
        raise invalid('roles doit contenir "user", sans doublon ni valeur inconnue')
    return roles