"""Documentation interactive de l'API : spécification OpenAPI et Swagger UI."""
import os

from flask import Blueprint, send_from_directory

bp = Blueprint("docs", __name__)

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
SWAGGER_UI = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14"

PAGE = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>API Vidéothèque · Documentation</title>
  <link rel="stylesheet" href="{SWAGGER_UI}/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="{SWAGGER_UI}/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({{
      url: "/openapi.json",
      dom_id: "#swagger-ui",
      persistAuthorization: true,
      tryItOutEnabled: true,
      displayRequestDuration: true,
      docExpansion: "list",
    }});
  </script>
</body>
</html>"""


@bp.get("/openapi.json")
def openapi():
    return send_from_directory(DOCS_DIR, "openapi.json", mimetype="application/json")


@bp.get("/docs")
def docs():
    return PAGE