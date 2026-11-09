#!/usr/bin/python3
from flask import Flask, jsonify
from db import db, init_db

from routes.favorites import bp as favorites_bp
from routes.films import bp as films_bp
from routes.users import bp as users_bp
from utils import register_error_handlers

app = Flask(__name__)
app.json.ensure_ascii = False
register_error_handlers(app)

app.register_blueprint(films_bp)
app.register_blueprint(users_bp)
app.register_blueprint(favorites_bp)

init_db()


@app.route("/health")
def health():
    db.command("ping")
    return jsonify({"status": "ok", "collections": db.list_collection_names()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)