#!/usr/bin/env bash
# Tests des routes des comptes : connexion, inscription, profil, rôles, suppression
source "$(dirname "$0")/lib.sh"
login_admin

section "Connexion"
check "admin" 200 POST /login "" "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}"
expect "réponse sans password_hash" "$(json '["user"].get("password_hash", "absent")')" absent
check "email en majuscules" 200 POST /login "" "{\"email\":\"${ADMIN_EMAIL^^}\",\"password\":\"$ADMIN_PASSWORD\"}"
check "mauvais mot de passe" 401 POST /login "" "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"mauvais-mdp\"}"
check "email inconnu" 401 POST /login "" '{"email":"inconnu@example.org","password":"testpass123"}'
check "mot de passe manquant" 400 POST /login "" "{\"email\":\"$ADMIN_EMAIL\"}"
check "email au mauvais format" 400 POST /login "" '{"email":"pas-un-email","password":"testpass123"}'
check "injection NoSQL dans email" 400 POST /login "" '{"email":{"$ne":null},"password":"x"}'
check "corps non JSON" 400 POST /login "" "pas du json"

section "Inscription"
create_user U
ok "inscription valide" 201
check "connexion du nouveau compte" 200 POST /login "" "{\"email\":\"$U_EMAIL\",\"password\":\"$U_PASSWORD\"}"
expect "rôles par défaut" "$(json '["user"]["roles"]')" "['user']"
check "email déjà utilisé" 409 POST /users "" "{\"email\":\"$U_EMAIL\",\"username\":\"autre$RANDOM\",\"password\":\"testpass123\"}"
expect "code d'erreur" "$(json '["code"]')" email_taken
check "email déjà utilisé, autre casse" 409 POST /users "" "{\"email\":\"${U_EMAIL^^}\",\"username\":\"autre$RANDOM\",\"password\":\"testpass123\"}"
check "username déjà utilisé" 409 POST /users "" "{\"email\":\"autre$RANDOM@example.org\",\"username\":\"$U_NAME\",\"password\":\"testpass123\"}"
expect "code d'erreur" "$(json '["code"]')" username_taken
check "email invalide" 400 POST /users "" '{"email":"pas-un-email","username":"valide1","password":"testpass123"}'
check "username trop court" 400 POST /users "" "{\"email\":\"a$RANDOM@example.org\",\"username\":\"ab\",\"password\":\"testpass123\"}"
check "mot de passe trop court" 400 POST /users "" "{\"email\":\"a$RANDOM@example.org\",\"username\":\"valide$RANDOM\",\"password\":\"court\"}"
check "champ manquant" 400 POST /users "" "{\"email\":\"a$RANDOM@example.org\",\"password\":\"testpass123\"}"
check "rôle admin ignoré à l'inscription" 201 POST /users "" "{\"email\":\"r$RANDOM@example.org\",\"username\":\"role$RANDOM\",\"password\":\"testpass123\",\"roles\":[\"user\",\"admin\"]}"
CREATED_USERS+=("$(json '["user"]["_id"]')")
expect "rôles du compte créé" "$(json '["user"]["roles"]')" "['user']"

section "Liste et consultation des comptes"
check "liste par l'admin" 200 GET /users "$TA"
expect "aucun password_hash dans la liste" "$(json '["users"] and any("password_hash" in u for u in json.load(open(sys.argv[1]))["users"])')" False
check "liste par un utilisateur" 403 GET /users "$U_TOKEN"
check "liste sans jeton" 401 GET /users ""
check "consultation de son compte" 200 GET "/users/$U_ID" "$U_TOKEN"
check "consultation d'un autre compte" 403 GET "/users/$ADMIN_ID" "$U_TOKEN"
check "consultation par l'admin" 200 GET "/users/$U_ID" "$TA"
check "id mal formé (admin)" 404 GET /users/abc "$TA"
check "compte inexistant (admin)" 404 GET "/users/$FAKE_ID" "$TA"

section "Modification du profil"
NEW_NAME="${U_NAME}x"
check "changement de username" 200 PUT "/users/$U_ID" "$U_TOKEN" "{\"username\":\"$NEW_NAME\"}"
expect "username modifié" "$(json '["username"]')" "$NEW_NAME"
check "username déjà pris" 409 PUT "/users/$U_ID" "$U_TOKEN" '{"username":"admin"}'
check "username trop court" 400 PUT "/users/$U_ID" "$U_TOKEN" '{"username":"ab"}'
check "email ignoré" 200 PUT "/users/$U_ID" "$U_TOKEN" "{\"username\":\"$NEW_NAME\",\"email\":\"change@example.org\"}"
expect "email inchangé" "$(json '["email"]')" "$U_EMAIL"
check "mot de passe actuel incorrect" 401 PUT "/users/$U_ID" "$U_TOKEN" "{\"username\":\"$NEW_NAME\",\"current_password\":\"faux-mdp1\",\"new_password\":\"nouveaupass1\"}"
check "nouveau mot de passe trop court" 400 PUT "/users/$U_ID" "$U_TOKEN" "{\"username\":\"$NEW_NAME\",\"current_password\":\"$U_PASSWORD\",\"new_password\":\"court\"}"
check "changement de mot de passe" 200 PUT "/users/$U_ID" "$U_TOKEN" "{\"username\":\"$NEW_NAME\",\"current_password\":\"$U_PASSWORD\",\"new_password\":\"nouveaupass1\"}"
check "connexion avec le nouveau mot de passe" 200 POST /login "" "{\"email\":\"$U_EMAIL\",\"password\":\"nouveaupass1\"}"
check "connexion avec l'ancien mot de passe" 401 POST /login "" "{\"email\":\"$U_EMAIL\",\"password\":\"$U_PASSWORD\"}"
check "modification par l'admin d'un autre compte" 403 PUT "/users/$U_ID" "$TA" '{"username":"pirate"}'
check "modification d'un autre compte" 403 PUT "/users/$ADMIN_ID" "$U_TOKEN" '{"username":"pirate"}'

section "Rôles"
check "changement par un utilisateur" 403 PUT "/users/$U_ID/roles" "$U_TOKEN" '{"roles":["user","admin"]}'
check "rôles sans user" 400 PUT "/users/$U_ID/roles" "$TA" '{"roles":["admin"]}'
check "rôle inconnu" 400 PUT "/users/$U_ID/roles" "$TA" '{"roles":["user","root"]}'
check "rôle en double" 400 PUT "/users/$U_ID/roles" "$TA" '{"roles":["user","user"]}'
check "compte inexistant" 404 PUT "/users/$FAKE_ID/roles" "$TA" '{"roles":["user"]}'
check "promotion admin" 200 PUT "/users/$U_ID/roles" "$TA" '{"roles":["user","admin"]}'
expect "rôles après promotion" "$(json '["roles"]')" "['user', 'admin']"
check "l'utilisateur promu accède à la liste" 200 GET /users "$U_TOKEN"
check "rétrogradation" 200 PUT "/users/$U_ID/roles" "$TA" '{"roles":["user"]}'
check "accès retiré immédiatement" 403 GET /users "$U_TOKEN"

section "Dernier administrateur"
call GET /users "$TA" >/dev/null
ADMINS=$(json '["users"] and sum("admin" in u["roles"] for u in json.load(open(sys.argv[1]))["users"])')
if [ "$ADMINS" = 1 ]; then
  check "retrait de son rôle admin" 409 PUT "/users/$ADMIN_ID/roles" "$TA" '{"roles":["user"]}'
  expect "code d'erreur" "$(json '["code"]')" last_admin
  check "suppression de son compte" 409 DELETE "/users/$ADMIN_ID" "$TA"
else
  echo "  IGNORÉ ces tests demandent un seul administrateur ($ADMINS trouvés)"
fi

section "Suppression de compte"
create_user V
check "suppression d'un autre compte" 403 DELETE "/users/$V_ID" "$U_TOKEN"
check "suppression par l'admin" 200 DELETE "/users/$V_ID" "$TA"
check "jeton du compte supprimé" 401 GET /films "$V_TOKEN"
expect "code d'erreur" "$(json '["code"]')" invalid_token
check "suppression en double" 404 DELETE "/users/$V_ID" "$TA"
check "suppression de son propre compte" 200 DELETE "/users/$U_ID" "$U_TOKEN"
check "connexion après suppression" 401 POST /login "" "{\"email\":\"$U_EMAIL\",\"password\":\"nouveaupass1\"}"

summary
