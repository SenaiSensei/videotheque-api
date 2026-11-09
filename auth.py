import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import g, request

from db import users
from utils import ApiError, to_object_id

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"
JWT_LIFETIME = timedelta(hours=1)


def create_token(user_id):
    """Crée un jeton signé, valable une heure, pour cet utilisateur."""
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + JWT_LIFETIME}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def invalid_token(message="Jeton absent, invalide ou expiré"):
    return ApiError(401, "invalid_token", message)


def forbidden():
    return ApiError(403, "forbidden", "Droits insuffisants")


def current_user():
    """Lit le jeton, vérifie sa signature et recharge l'utilisateur."""
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme != "Bearer" or not token:
        raise invalid_token()

    try:
        payload = jwt.decode(
            token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "iat", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        raise invalid_token("Jeton expiré")
    except jwt.InvalidTokenError:
        raise invalid_token()

    try:
        user_id = to_object_id(payload["sub"])
    except ApiError:
        raise invalid_token()

    user = users.find_one({"_id": user_id})
    if user is None:
        raise invalid_token("Compte supprimé")
    return user


def is_admin(user):
    return "admin" in user.get("roles", [])


def login_required(view):
    """Utilisateur connecté : g.user contient le document MongoDB."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        g.user = current_user()
        return view(*args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        g.user = current_user()
        if not is_admin(g.user):
            raise forbidden()
        return view(*args, **kwargs)
    return wrapper


def owner_required(view):
    """Seul le propriétaire du compte {user_id} de l'URL est autorisé."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        g.user = current_user()
        if str(g.user["_id"]) != kwargs.get("user_id"):
            raise forbidden()
        return view(*args, **kwargs)
    return wrapper


def owner_or_admin_required(view):
    """Le propriétaire du compte {user_id} de l'URL, ou un administrateur."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        g.user = current_user()
        if str(g.user["_id"]) != kwargs.get("user_id") and not is_admin(g.user):
            raise forbidden()
        return view(*args, **kwargs)
    return wrapper