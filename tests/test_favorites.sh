#!/usr/bin/env bash
# Tests des routes des favoris
source "$(dirname "$0")/lib.sh"
login_admin
create_user U
create_user V

check "création du film A" 201 POST /films "$TA" '{"title":"Film A","director":{"last_name":"Test"},"year":2001}'
FILM_A=$(json '["_id"]'); CREATED_FILMS+=("$FILM_A")
check "création du film B" 201 POST /films "$TA" '{"title":"Film B","director":{"last_name":"Test"},"year":2002}'
FILM_B=$(json '["_id"]'); CREATED_FILMS+=("$FILM_B")
FAV="/users/$U_ID/favorites"

section "Droits"
check "liste sans jeton" 401 GET "$FAV" ""
check "liste par un autre utilisateur" 403 GET "$FAV" "$V_TOKEN"
check "liste par l'admin" 403 GET "$FAV" "$TA"
check "ajout chez un autre utilisateur" 403 POST "$FAV" "$V_TOKEN" "{\"film_id\":\"$FILM_A\"}"

section "Ajout"
check "liste vide" 200 GET "$FAV" "$U_TOKEN"
expect "aucun film" "$(titles)" ""
check "ajout du film A" 201 POST "$FAV" "$U_TOKEN" "{\"film_id\":\"$FILM_A\"}"
check "ajout du film A en double" 200 POST "$FAV" "$U_TOKEN" "{\"film_id\":\"$FILM_A\"}"
check "ajout du film B" 201 POST "$FAV" "$U_TOKEN" "{\"film_id\":\"$FILM_B\"}"
expect "ids des favoris" "$(json '["favorites"]')" "['$FILM_A', '$FILM_B']"
check "film inexistant" 404 POST "$FAV" "$U_TOKEN" "{\"film_id\":\"$FAKE_ID\"}"
check "film_id mal formé" 400 POST "$FAV" "$U_TOKEN" '{"film_id":"abc"}'
check "film_id numérique" 400 POST "$FAV" "$U_TOKEN" '{"film_id":123}'
check "film_id manquant" 400 POST "$FAV" "$U_TOKEN" '{}'
check "liste des favoris" 200 GET "$FAV" "$U_TOKEN"
expect "films dans l'ordre d'ajout" "$(titles)" "Film A,Film B"
check "favoris dans le compte" 200 GET "/users/$U_ID" "$U_TOKEN"
expect "favorites du compte" "$(json '["favorites"]')" "['$FILM_A', '$FILM_B']"

section "Retrait"
check "retrait du film A" 200 DELETE "$FAV/$FILM_A" "$U_TOKEN"
expect "favoris restants" "$(json '["favorites"]')" "['$FILM_B']"
check "retrait d'un film absent" 200 DELETE "$FAV/$FILM_A" "$U_TOKEN"
check "retrait avec id mal formé" 404 DELETE "$FAV/abc" "$U_TOKEN"
check "retrait chez un autre utilisateur" 403 DELETE "$FAV/$FILM_B" "$V_TOKEN"

section "Suppression d'un film en favori"
check "ajout du film A chez U" 201 POST "$FAV" "$U_TOKEN" "{\"film_id\":\"$FILM_A\"}"
check "ajout du film A chez V" 201 POST "/users/$V_ID/favorites" "$V_TOKEN" "{\"film_id\":\"$FILM_A\"}"
check "suppression du film A" 200 DELETE "/films/$FILM_A" "$TA"
check "favoris de U" 200 GET "$FAV" "$U_TOKEN"
expect "film A retiré chez U" "$(titles)" "Film B"
check "favoris de V" 200 GET "/users/$V_ID/favorites" "$V_TOKEN"
expect "film A retiré chez V" "$(titles)" ""

summary
