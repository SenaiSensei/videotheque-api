#!/usr/bin/env bash
# Tests du jeton JWT : absence, format, falsification
source "$(dirname "$0")/lib.sh"
login_admin

section "Jeton"
check "sans en-tête Authorization" 401 GET /films ""
check "jeton mal formé" 401 GET /films "abc"
check "jeton à trois parties invalide" 401 GET /films "abc.def.ghi"

TAMPERED="${TA%?}$([ "${TA: -1}" = A ] && echo B || echo A)"
check "signature modifiée" 401 GET /films "$TAMPERED"

NONE_TOKEN=$(python3 - "$ADMIN_ID" <<'P'
import base64, json, sys, time
b64 = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
now = int(time.time())
print(b64({"alg": "none", "typ": "JWT"}) + "." + b64({"sub": sys.argv[1], "iat": now, "exp": now + 3600}) + ".")
P
)
check "jeton non signé (alg none)" 401 GET /films "$NONE_TOKEN"

code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: $TA" "$API/films")
expect "jeton sans le préfixe Bearer" "$code" 401
check "jeton valide" 200 GET /films "$TA"

section "Routes publiques"
check "connexion publique, email inconnu" 401 POST /login "" '{"email":"inconnu@example.org","password":"x"}'
check "inscription publique, corps vide" 400 POST /users "" ""

summary
