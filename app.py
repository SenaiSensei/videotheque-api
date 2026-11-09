#!/usr/bin/python3
from flask import Flask, jsonify
from db import db, init_db
from utils import register_error_handlers

app = Flask(__name__)
app.json.ensure_ascii = False
register_error_handlers(app)
init_db()


@app.route("/health")
def health():
    db.command("ping")
    return jsonify({"status": "ok", "collections": db.list_collection_names()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)