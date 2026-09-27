# shellcheck shell=bash
# Fonctions communes aux scripts de capacité. À sourcer, pas à exécuter.
#
# Accès au cluster de capacité, à choisir explicitement :
#   CAPACITE_SSH=capacite          kubectl exécuté sur le VPS de capacité par
#                                  SSH (alias de ~/.ssh/config), comme la
#                                  production est pilotée ;
#   CAPACITE_KUBECTL_LOCAL=oui     kubectl local, contexte courant.
# Sans l'une ou l'autre, les scripts refusent de deviner.

# shellcheck disable=SC2034  # utilisées par les scripts qui sourcent ce fichier
DOMAINE_CAPACITE=capacite.dilane-shop.store
# shellcheck disable=SC2034
DOMAINE_PRODUCTION=dilane-shop.store

refuser() { echo "REFUS : $*" >&2; exit 1; }

verifier_acces() {
  if [[ -n ${CAPACITE_SSH:-} && ${CAPACITE_KUBECTL_LOCAL:-} == oui ]]; then
    refuser "choisir CAPACITE_SSH ou CAPACITE_KUBECTL_LOCAL=oui, pas les deux."
  fi
  [[ -n ${CAPACITE_SSH:-} || ${CAPACITE_KUBECTL_LOCAL:-} == oui ]] ||
    refuser "désigner le cluster de capacité : CAPACITE_SSH=<alias SSH du VPS de capacité> ou CAPACITE_KUBECTL_LOCAL=oui."
}

# kubectl sur le cluster de capacité. Par SSH, chaque argument est protégé
# par printf %q : le shell distant le reçoit intact (espaces, accolades et
# guillemets des expressions jsonpath compris).
k() {
  if [[ -n ${CAPACITE_SSH:-} ]]; then
    # shellcheck disable=SC2029  # développement local voulu, arguments protégés
    ssh "$CAPACITE_SSH" "kubectl $(printf '%q ' "$@")"
  else
    kubectl "$@"
  fi
}

description_acces() {
  if [[ -n ${CAPACITE_SSH:-} ]]; then echo "ssh $CAPACITE_SSH kubectl"; else echo "kubectl local ($(kubectl config current-context 2>/dev/null || echo 'contexte inconnu'))"; fi
}

# Première adresse IPv4 d'un nom, avec l'outil disponible sur le poste.
resoudre() {
  local ip=""
  if command -v getent >/dev/null; then
    ip=$(getent ahostsv4 "$1" 2>/dev/null | awk 'NR==1 {print $1}')
  fi
  if [[ -z $ip ]] && command -v dig >/dev/null; then
    ip=$(dig +short A "$1" | grep -E '^[0-9.]+$' | head -1)
  fi
  if [[ -z $ip ]] && command -v python3 >/dev/null; then
    ip=$(python3 -c 'import socket, sys; print(socket.gethostbyname(sys.argv[1]))' "$1" 2>/dev/null || true)
  fi
  echo "$ip"
}
