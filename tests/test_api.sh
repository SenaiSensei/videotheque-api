#!/usr/bin/env bash
# Tests des routes films et favoris de l'API
# Usage : ADMIN_EMAIL=... ADMIN_PASSWORD=... ./tests/test_api.sh

API=${API:-http://127.0.0.1:5001}
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@example.org}
if [ -z "$ADMIN_PASSWORD" ]; then
  read -rsp "Mot de passe admin : " ADMIN_PASSWORD; echo
fi

PASS=0; FAIL=0
BODY=$(mktemp); trap 'rm -f "$BODY"' EXIT

# call METHODE CHEMIN JETON [JSON] : enregistre le corps dans $BODY et renvoie le code HTTP
call() {
  local method=$1 path=$2 token=$3 data=$4
  local args=(-s -o "$BODY" -w '%{http_code}' -X "$method" "$API$path")
  [ -n "$token" ] && args+=(-H "Authorization: Bearer $token")
  [ -n "$data" ] && args+=(-H 'Content-Type: application/json' -d "$data")
  curl "${args[@]}"
}

# check NOM CODE_ATTENDU METHODE CHEMIN JETON [JSON]
check() {
  local name=$1 expected=$2; shift 2
  local code; code=$(call "$@")
  if [ "$code" = "$expected" ]; then
    PASS=$((PASS + 1)); printf '  OK    %-45s %s\n' "$name" "$code"
  else
    FAIL=$((FAIL + 1)); printf '  ECHEC %-45s %s (attendu %s)\n' "$name" "$code" "$expected"
    printf '        %s\n' "$(cat "$BODY")"
  fi
}

# json CHEMIN_PYTHON : extrait une valeur du dernier corps reçu, ex. json '["token"]'
json() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))$1)" "$BODY"; }

titles() { json '["films"]' | python3 -c "import ast,sys; print([f['title'] for f in ast.literal_eval(sys.stdin.read())])"; }

echo "== Préparation"
check "connexion admin" 200 POST /login "" "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}"
TA=$(json '["token"]') || { echo "Connexion admin impossible, arrêt."; exit 1; }

SUFFIX=$(date +%s)
check "inscription utilisateur de test" 201 POST /users "" \
  "{\"email\":\"test$SUFFIX@example.org\",\"username\":\"test$SUFFIX\",\"password\":\"testpass123\"}"
TU=$(json '["token"]'); USER_ID=$(json '["user"]["_id"]')

FILM_JSON='{
  "title": "Alien", "description": "Huis clos spatial.",
  "director": {"last_name": "Scott", "first_name": "Ridley"},
  "actors": [{"last_name": "Weaver", "first_name": "Sigourney"}, {"last_name": "Hurt", "first_name": "John"}],
  "genres": ["Science-fiction", "Horreur"], "year": 1979,
  "supports": [{"type": "dvd", "location": "Étagère B2"}, {"type": "digital", "location": "/films/alien.mkv"}]
}'

echo "== Films : droits et validation"
check "liste sans jeton" 401 GET /films ""
check "liste avec jeton invalide" 401 GET /films "abc.def.ghi"
check "ajout par un utilisateur" 403 POST /films "$TU" "$FILM_JSON"
check "ajout sans corps JSON" 400 POST /films "$TA" "pas du json"
check "ajout avec year en texte" 400 POST /films "$TA" '{"title":"X","director":{"last_name":"Y"},"year":"1979"}'
check "ajout avec support inconnu" 400 POST /films "$TA" '{"title":"X","director":{"last_name":"Y"},"year":1979,"supports":[{"type":"vhs","location":"A"}]}'
check "ajout sans réalisateur" 400 POST /films "$TA" '{"title":"X","year":1979}'

echo "== Films : CRUD"
check "ajout par l'admin" 201 POST /films "$TA" "$FILM_JSON"
FILM=$(json '["_id"]')
check "liste complète" 200 GET /films "$TU"
check "fiche du film" 200 GET "/films/$FILM" "$TU"
check "fiche avec id mal formé" 404 GET /films/abc "$TU"
check "fiche inexistante" 404 GET /films/ffffffffffffffffffffffff "$TU"
check "modification par un utilisateur" 403 PUT "/films/$FILM" "$TU" "$FILM_JSON"
check "modification par l'admin" 200 PUT "/films/$FILM" "$TA" "${FILM_JSON/1979/1980}"
echo "        année après modification : $(json '["year"]')"
check "modification inexistante" 404 PUT /films/ffffffffffffffffffffffff "$TA" "$FILM_JSON"

echo "== Films : recherche"
for q in "title=ali" "director=ridley" "actor=weaver" "actor=hurt&year=1980" \
         "genre=horreur" "genre=hor" "support=digital" "title=.*" "year=1980&title=pulp"; do
  check "recherche ?$q" 200 GET "/films?$q" "$TU"
  echo "        résultats : $(titles)"
done
check "recherche year=abc" 400 GET "/films?year=abc" "$TU"
check "recherche support=vhs" 400 GET "/films?support=vhs" "$TU"

echo "== Favoris"
check "liste vide" 200 GET "/users/$USER_ID/favorites" "$TU"
check "ajout du film" 201 POST "/users/$USER_ID/favorites" "$TU" "{\"film_id\":\"$FILM\"}"
check "ajout en double" 200 POST "/users/$USER_ID/favorites" "$TU" "{\"film_id\":\"$FILM\"}"
echo "        favoris : $(json '["favorites"]')"
check "ajout d'un film inexistant" 404 POST "/users/$USER_ID/favorites" "$TU" '{"film_id":"ffffffffffffffffffffffff"}'
check "ajout avec film_id invalide" 400 POST "/users/$USER_ID/favorites" "$TU" '{"film_id":123}'
check "favoris d'un autre compte" 403 GET "/users/$USER_ID/favorites" "$TA"
check "liste des favoris" 200 GET "/users/$USER_ID/favorites" "$TU"
echo "        films : $(titles)"
check "retrait du film" 200 DELETE "/users/$USER_ID/favorites/$FILM" "$TU"
check "retrait avec id mal formé" 404 DELETE "/users/$USER_ID/favorites/abc" "$TU"
check "nouvel ajout avant suppression" 201 POST "/users/$USER_ID/favorites" "$TU" "{\"film_id\":\"$FILM\"}"

echo "== Suppression d'un film et nettoyage des favoris"
check "suppression par un utilisateur" 403 DELETE "/films/$FILM" "$TU"
check "suppression par l'admin" 200 DELETE "/films/$FILM" "$TA"
check "suppression en double" 404 DELETE "/films/$FILM" "$TA"
check "favoris après suppression" 200 GET "/users/$USER_ID" "$TU"
echo "        favoris : $(json '["favorites"]')"

echo "== Nettoyage"
check "suppression de l'utilisateur de test" 200 DELETE "/users/$USER_ID" "$TU"

echo
echo "Résultat : $PASS réussis, $FAIL échoués"
[ "$FAIL" -eq 0 ]