#!/usr/bin/env bash
# Fonctions communes aux scripts de test de l'API.

API=${API:-http://127.0.0.1:5000}
ADMIN_EMAIL=${ADMIN_EMAIL:-admin@example.org}
if [ -z "$ADMIN_PASSWORD" ]; then
  read -rsp "Mot de passe admin : " ADMIN_PASSWORD; echo
  export ADMIN_PASSWORD
fi

PASS=0; FAIL=0
BODY=$(mktemp)
CREATED_USERS=()
CREATED_FILMS=()
FAKE_ID=ffffffffffffffffffffffff
DETAIL=0
[ "$1" = "detail" ] && DETAIL=1

# ok NOM VALEUR : compte un succès et l'affiche en mode detail
ok() {
  PASS=$((PASS + 1))
  if [ "$DETAIL" = 1 ]; then printf '  OK    %-50s %s\n' "$1" "$2"; fi
}

# Supprime les comptes et films de test, même si un test échoue
cleanup() {
  for id in "${CREATED_FILMS[@]}"; do call DELETE "/films/$id" "$TA" >/dev/null; done
  for id in "${CREATED_USERS[@]}"; do call DELETE "/users/$id" "$TA" >/dev/null; done
  rm -f "$BODY"
}
trap cleanup EXIT

section() {
  if [ "$DETAIL" = 1 ]; then echo; echo "== $1"; fi
}

# call METHODE CHEMIN JETON [JSON] : enregistre le corps dans $BODY et affiche le code HTTP
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
    ok "$name" "$code"
  else
    FAIL=$((FAIL + 1)); printf '  ECHEC %-50s %s (attendu %s)\n' "$name" "$code" "$expected"
    printf '        %s\n' "$(tr -d '\n' < "$BODY")"
  fi
}

# expect NOM VALEUR_OBTENUE VALEUR_ATTENDUE : vérifie un contenu de réponse
expect() {
  if [ "$2" = "$3" ]; then
    ok "$1" "$2"
  else
    FAIL=$((FAIL + 1)); printf '  ECHEC %-50s %s (attendu %s)\n' "$1" "$2" "$3"
  fi
}

# json CHEMIN : extrait une valeur du dernier corps reçu, ex. json '["user"]["_id"]'
json() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))$1)" "$BODY" 2>/dev/null; }

# titles : titres des films du dernier corps reçu
titles() {
  python3 -c "import json,sys; print(','.join(f['title'] for f in json.load(open(sys.argv[1]))['films']))" "$BODY" 2>/dev/null
}

# login_admin : remplit TA (jeton) et ADMIN_ID
login_admin() {
  local code
  code=$(call POST /login "" "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}")
  if [ "$code" != 200 ]; then
    echo "Connexion admin impossible ($code) : vérifie ADMIN_EMAIL et ADMIN_PASSWORD."
    exit 1
  fi
  TA=$(json '["token"]'); ADMIN_ID=$(json '["user"]["_id"]')
}

# create_user PREFIXE : crée un compte de test et remplit PREFIXE_ID, _TOKEN, _EMAIL, _NAME, _PASSWORD
create_user() {
  local prefix=$1 suffix="$(date +%s)$RANDOM"
  local name="test$suffix" email="test$suffix@example.org" password="testpass123"
  local code; code=$(call POST /users "" "{\"email\":\"$email\",\"username\":\"$name\",\"password\":\"$password\"}")
  if [ "$code" != 201 ]; then
    echo "Création d'un compte de test impossible ($code)."; cat "$BODY"; exit 1
  fi
  printf -v "${prefix}_ID" '%s' "$(json '["user"]["_id"]')"
  printf -v "${prefix}_TOKEN" '%s' "$(json '["token"]')"
  printf -v "${prefix}_EMAIL" '%s' "$email"
  printf -v "${prefix}_NAME" '%s' "$name"
  printf -v "${prefix}_PASSWORD" '%s' "$password"
  CREATED_USERS+=("$(json '["user"]["_id"]')")
}

# summary : affiche le bilan et renvoie 1 en cas d'échec
summary() {
  echo
  echo "Résultat $(basename "$0") : $PASS réussis, $FAIL échoués"
  [ "$FAIL" -eq 0 ]
}
