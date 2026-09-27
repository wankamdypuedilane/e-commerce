#!/usr/bin/env bash
# Garde-fou : vérifie que kubectl vise bien l'environnement de capacité, et
# jamais la production. Voir docs/test-capacite.md.
#
# Usage, depuis la racine du dépôt :
#   CAPACITE_SSH=capacite scripts/capacite/verifier-cluster.sh avant-deploiement
#   CAPACITE_SSH=capacite scripts/capacite/verifier-cluster.sh avant-campagne
# (ou CAPACITE_KUBECTL_LOCAL=oui à la place de CAPACITE_SSH, voir commun.sh).
#
# avant-deploiement : l'espace de noms dilane-shop est absent, ou porte
#   l'étiquette dilane-shop.store/environnement=capacite ; aucun Ingress du
#   cluster ne sert dilane-shop.store.
# avant-campagne : en plus, l'Ingress sert capacite.dilane-shop.store, deux
#   pods Django sont prêts, et le nom capacite.dilane-shop.store ne résout
#   pas vers l'adresse de la production.
set -euo pipefail

# shellcheck source=scripts/capacite/commun.sh
source "$(dirname "$0")/commun.sh"
ETIQUETTE='dilane-shop\.store/environnement'
ok() { echo "  ok  $*"; }

MODE=${1:-}
[[ $MODE == avant-deploiement || $MODE == avant-campagne ]] ||
  refuser "mode attendu : avant-deploiement ou avant-campagne."
verifier_acces

echo "Vérification du cluster ($MODE), via : $(description_acces)"

# Sans accès au cluster, « espace de noms absent » ne voudrait rien dire.
noeuds=$(k get nodes -o name 2>/dev/null) || refuser "cluster injoignable par $(description_acces)."
ok "cluster joignable ($(wc -l <<<"$noeuds" | tr -d ' ') nœud(s))"

# L'espace de noms de production n'a pas l'étiquette de capacité.
if k get namespace dilane-shop >/dev/null 2>&1; then
  env=$(k get namespace dilane-shop -o "jsonpath={.metadata.labels.$ETIQUETTE}")
  [[ $env == capacite ]] ||
    refuser "l'espace de noms dilane-shop existe sans l'étiquette environnement=capacite : ce cluster peut être la production."
  ok "espace de noms dilane-shop étiqueté environnement=capacite"
elif [[ $MODE == avant-campagne ]]; then
  refuser "l'espace de noms dilane-shop n'existe pas : l'environnement n'est pas déployé."
else
  ok "espace de noms dilane-shop absent (cluster neuf)"
fi

# Aucun Ingress ne sert le domaine de production.
hotes=$(k get ingress -A -o jsonpath='{range .items[*]}{range .spec.rules[*]}{.host}{"\n"}{end}{end}')
if grep -qx "$DOMAINE_PRODUCTION" <<<"$hotes"; then
  refuser "un Ingress de ce cluster sert $DOMAINE_PRODUCTION : c'est la production."
fi
ok "aucun Ingress ne sert $DOMAINE_PRODUCTION"

[[ $MODE == avant-deploiement ]] && { echo "Cluster de capacité confirmé pour le déploiement."; exit 0; }

hote=$(k get ingress dilane-shop -n dilane-shop -o jsonpath='{.spec.rules[0].host}')
[[ $hote == "$DOMAINE_CAPACITE" ]] || refuser "l'Ingress dilane-shop sert « $hote », pas $DOMAINE_CAPACITE."
ok "l'Ingress sert $DOMAINE_CAPACITE"

prets=$(k get pods -n dilane-shop -l app.kubernetes.io/name=django \
  -o jsonpath='{range .items[*]}{.status.containerStatuses[0].ready}{"\n"}{end}' | grep -c '^true$' || true)
[[ $prets -eq 2 ]] || refuser "$prets pod(s) Django prêt(s) sur 2 attendus."
ok "2 pods Django prêts"

ip_capacite=$(resoudre "$DOMAINE_CAPACITE")
ip_production=$(resoudre "$DOMAINE_PRODUCTION")
[[ -n $ip_capacite ]] || refuser "$DOMAINE_CAPACITE ne résout vers aucune adresse."
[[ -n $ip_production ]] || refuser "$DOMAINE_PRODUCTION ne résout pas : impossible de vérifier que les deux adresses diffèrent."
[[ $ip_capacite != "$ip_production" ]] ||
  refuser "$DOMAINE_CAPACITE résout vers $ip_capacite, l'adresse de la production."
ok "$DOMAINE_CAPACITE → $ip_capacite, distinct de la production ($ip_production)"

echo "Cluster de capacité confirmé pour la campagne."
