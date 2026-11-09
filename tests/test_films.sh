#!/usr/bin/env bash
# Tests des routes des films : droits, validation, CRUD et recherche
source "$(dirname "$0")/lib.sh"
login_admin
create_user U

FILM_JSON='{
  "title": "Alien", "description": "Huis clos spatial.",
  "director": {"last_name": "Scott", "first_name": "Ridley"},
  "actors": [{"last_name": "Weaver", "first_name": "Sigourney"}, {"last_name": "Hurt", "first_name": "John"}],
  "genres": ["Science-fiction", "Horreur"], "year": 1979,
  "supports": [{"type": "dvd", "location": "Étagère B2"}, {"type": "digital", "location": "/films/alien.mkv"}]
}'

section "Droits"
check "liste sans jeton" 401 GET /films ""
check "liste par un utilisateur" 200 GET /films "$U_TOKEN"
check "ajout par un utilisateur" 403 POST /films "$U_TOKEN" "$FILM_JSON"

section "Validation à l'ajout"
check "corps non JSON" 400 POST /films "$TA" "pas du json"
check "titre manquant" 400 POST /films "$TA" '{"director":{"last_name":"Y"},"year":1979}'
check "titre vide" 400 POST /films "$TA" '{"title":"  ","director":{"last_name":"Y"},"year":1979}'
check "réalisateur manquant" 400 POST /films "$TA" '{"title":"X","year":1979}'
check "réalisateur sans nom" 400 POST /films "$TA" '{"title":"X","director":{"first_name":"Y"},"year":1979}'
check "year en texte" 400 POST /films "$TA" '{"title":"X","director":{"last_name":"Y"},"year":"1979"}'
check "year hors limites" 400 POST /films "$TA" '{"title":"X","director":{"last_name":"Y"},"year":1500}'
check "genres non liste" 400 POST /films "$TA" '{"title":"X","director":{"last_name":"Y"},"year":1979,"genres":"Drame"}'
check "acteur invalide" 400 POST /films "$TA" '{"title":"X","director":{"last_name":"Y"},"year":1979,"actors":["Weaver"]}'
check "support inconnu" 400 POST /films "$TA" '{"title":"X","director":{"last_name":"Y"},"year":1979,"supports":[{"type":"vhs","location":"A"}]}'
check "support sans emplacement" 400 POST /films "$TA" '{"title":"X","director":{"last_name":"Y"},"year":1979,"supports":[{"type":"dvd"}]}'
check "injection NoSQL dans le titre" 400 POST /films "$TA" '{"title":{"$ne":null},"director":{"last_name":"Y"},"year":1979}'

section "CRUD"
check "ajout par l'admin" 201 POST /films "$TA" "$FILM_JSON"
FILM=$(json '["_id"]'); CREATED_FILMS+=("$FILM")
expect "_id renvoyé en texte" "${#FILM}" 24
check "ajout minimal" 201 POST /films "$TA" '{"title":"Film minimal","director":{"last_name":"Anonyme"},"year":2000}'
CREATED_FILMS+=("$(json '["_id"]')")
expect "listes vides par défaut" "$(json '["actors"] + json.load(open(sys.argv[1]))["supports"]')" "[]"
check "fiche du film" 200 GET "/films/$FILM" "$U_TOKEN"
expect "titre de la fiche" "$(json '["title"]')" Alien
check "fiche avec id mal formé" 404 GET /films/abc "$U_TOKEN"
check "fiche inexistante" 404 GET "/films/$FAKE_ID" "$U_TOKEN"
check "modification par un utilisateur" 403 PUT "/films/$FILM" "$U_TOKEN" "$FILM_JSON"
check "modification par l'admin" 200 PUT "/films/$FILM" "$TA" "${FILM_JSON/1979/1980}"
expect "année modifiée" "$(json '["year"]')" 1980
expect "_id inchangé" "$(json '["_id"]')" "$FILM"
check "modification invalide" 400 PUT "/films/$FILM" "$TA" '{"title":"X"}'
check "modification inexistante" 404 PUT "/films/$FAKE_ID" "$TA" "$FILM_JSON"

section "Recherche"
search() {
  local name=$1 query=$2 expected=$3
  check "$name" 200 GET "/films?$query" "$U_TOKEN"
  case ",$(titles)," in
    *",Alien,"*) found=oui ;;
    *) found=non ;;
  esac
  expect "  Alien trouvé ?" "$found" "$expected"
}
search "titre partiel" "title=ali" oui
search "titre en majuscules" "title=ALIEN" oui
search "réalisateur par prénom" "director=ridley" oui
search "réalisateur par nom" "director=scott" oui
search "acteur" "actor=weaver" oui
search "acteur et année" "actor=hurt&year=1980" oui
search "genre exact" "genre=horreur" oui
search "genre partiel" "genre=hor" non
search "support" "support=digital" oui
search "support absent" "support=bluray" non
search "filtres incompatibles" "title=alien&year=1994" non
search "expression régulière échappée" "title=.*" non
search "filtre vide ignoré" "title=&actor=weaver" oui
check "year non numérique" 400 GET "/films?year=abc" "$U_TOKEN"
check "support inconnu" 400 GET "/films?support=vhs" "$U_TOKEN"

section "Suppression"
check "suppression par un utilisateur" 403 DELETE "/films/$FILM" "$U_TOKEN"
check "suppression par l'admin" 200 DELETE "/films/$FILM" "$TA"
check "fiche après suppression" 404 GET "/films/$FILM" "$U_TOKEN"
check "suppression en double" 404 DELETE "/films/$FILM" "$TA"
check "suppression avec id mal formé" 404 DELETE /films/abc "$TA"

summary
