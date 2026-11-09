#!/usr/bin/env bash
# Lance tous les scripts de test et affiche le bilan global
DIR=$(dirname "$0")
if [ -z "$ADMIN_PASSWORD" ]; then
  read -rsp "Mot de passe admin : " ADMIN_PASSWORD; echo
  export ADMIN_PASSWORD
fi

FAILED=()
for script in test_auth.sh test_users.sh test_films.sh test_favorites.sh; do
  echo
  echo "################ $script"
  bash "$DIR/$script" || FAILED+=("$script")
done

echo
if [ ${#FAILED[@]} -eq 0 ]; then
  echo "Tous les scripts de test ont réussi."
else
  echo "Scripts en échec : ${FAILED[*]}"
  exit 1
fi
