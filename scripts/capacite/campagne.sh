#!/usr/bin/env bash
# Campagne de capacité : enchaîne les paliers de scripts/k6/capacite.js,
# un k6 par palier, et s'arrête au premier palier en échec ou invalide.
# Voir docs/test-capacite.md.
#
# Usage, depuis la racine du dépôt, sur le poste qui génère la charge :
#   CONFIRMER_CAPACITE=oui CAPACITE_SSH=capacite \
#     scripts/capacite/campagne.sh [palier ...]
#
# Paliers : parcours par seconde (3 requêtes par parcours), entiers
# strictement croissants, de 1 à 50, 10 au plus. Par défaut :
#   2 4 8 12 16 24 32 40
# Chaque palier dure 5 minutes, suivi d'1 minute de pause : 8 paliers
# durent au plus 48 minutes, 10 paliers au plus 60.
#
# Variables :
#   CONFIRMER_CAPACITE=oui  obligatoire.
#   CAPACITE_SSH / CAPACITE_KUBECTL_LOCAL   accès au cluster (commun.sh).
#   K6                      commande k6, « k6 » par défaut. Avec Docker :
#                           K6="docker run --rm -i --user $(id -u):$(id -g) -v $PWD:/depot -w /depot grafana/k6:2.3.0"
#                           (--user : k6 doit pouvoir écrire dans resultats/).
#   TERME_RECHERCHE         transmis à k6 (« Casque » par défaut).
#
# Un palier échoue si k6 franchit un seuil (plus de 1 % d'erreurs, p95
# client au-delà d'1 s, recherche sans produit, fiche non HTML) ou si un
# pod de dilane-shop ou d'observabilite redémarre, est remplacé ou
# disparaît pendant le palier : k6 est alors interrompu. Un palier est
# invalide si k6 n'a pas pu lancer toutes les itérations demandées : le
# débit visé n'a pas été produit.
set -uo pipefail

cd "$(dirname "$0")/../.." || exit 1
# shellcheck source=scripts/capacite/commun.sh
source scripts/capacite/commun.sh

PALIER_PLAFOND=50
PALIERS_MAX=10
PAUSE_ENTRE_PALIERS=60
INTERVALLE_SURVEILLANCE=15

[[ ${CONFIRMER_CAPACITE:-} == oui ]] ||
  refuser "cette campagne charge $DOMAINE_CAPACITE ; confirmer par CONFIRMER_CAPACITE=oui."
verifier_acces

# --- Paliers --------------------------------------------------------------
if [[ $# -eq 0 ]]; then set -- 2 4 8 12 16 24 32 40; fi
[[ $# -le $PALIERS_MAX ]] || refuser "$# paliers demandés ; $PALIERS_MAX au plus."
precedent=0
for p in "$@"; do
  [[ $p =~ ^[0-9]+$ ]] || refuser "palier « $p » : entier attendu."
  (( p >= 1 && p <= PALIER_PLAFOND )) || refuser "palier $p hors de 1 à $PALIER_PLAFOND."
  (( p > precedent )) || refuser "paliers strictement croissants attendus ($p après $precedent)."
  precedent=$p
done
PALIERS=("$@")

# --- Garde-fou cluster ----------------------------------------------------
scripts/capacite/verifier-cluster.sh avant-campagne || exit 1

K6=${K6:-k6}
# shellcheck disable=SC2206  # découpage voulu : K6 est une commande
K6_CMD=($K6)

horodatage=$(date +%Y%m%d-%H%M%S)
DOSSIER="resultats/capacite-$horodatage"
mkdir -p "$DOSSIER"
TABLEAU="$DOSSIER/resultats.md"

# État des pods surveillés : nom et compteurs de redémarrage de chaque
# conteneur, hors pods terminés (Job de migration). Toute différence entre
# deux relevés signale un redémarrage, un remplacement ou une disparition.
etat_pods() {
  local ns sortie
  for ns in dilane-shop observabilite; do
    sortie=$(k get pods -n "$ns" --field-selector=status.phase!=Succeeded \
      -o 'jsonpath={range .items[*]}{.metadata.name}{"="}{range .status.containerStatuses[*]}{.restartCount}{","}{end}{"\n"}{end}') || return 1
    # shellcheck disable=SC2001  # préfixe sur chaque ligne
    sed "s|^|$ns/|" <<<"$sortie"
  done | grep -v '/$' | sort
}

ecart_pods() { diff <(echo "$1") <(echo "$2") | grep -E '^[<>]' | tr '\n' ' '; }

# Lit le fichier « CLE=valeur » écrit par handleSummary, sans l'exécuter.
declare -A R
lire_resultat() {
  R=()
  local cle val
  while IFS='=' read -r cle val; do
    [[ $cle =~ ^[A-Z0-9_]+$ ]] && R[$cle]=$val
  done <"$1"
}

{
  echo "# Campagne de capacité — $horodatage"
  echo
  echo "Cible : https://$DOMAINE_CAPACITE — paliers de 5 min, 3 requêtes par parcours."
  echo
  echo "| Palier (parcours/s) | Requêtes/s demandées | Parcours/s obtenus | Requêtes | p50 (ms) | p95 (ms) | p99 (ms) | Erreurs (%) | Itérations non lancées | VUs actifs max / disponibles | Pods | Statut |"
  echo "|---|---|---|---|---|---|---|---|---|---|---|---|"
} >"$TABLEAU"

dernier_reussi=""
verdict=""
for p in "${PALIERS[@]}"; do
  echo
  echo "=== Palier $p parcours/s ($((p * 3)) requêtes/s demandées), 5 minutes ==="
  avant=$(etat_pods) || refuser "relevé des pods impossible avant le palier $p."
  fichier="$DOSSIER/palier-$p.env"
  journal="$DOSSIER/palier-$p.log"
  args=(run --quiet -e CONFIRMER_CAPACITE=oui -e "PALIER=$p" -e "FICHIER_RESULTAT=$fichier")
  [[ -n ${TERME_RECHERCHE:-} ]] && args+=(-e "TERME_RECHERCHE=$TERME_RECHERCHE")
  "${K6_CMD[@]}" "${args[@]}" scripts/k6/capacite.js >"$journal" 2>&1 &
  pid=$!

  # Surveillance des pods pendant le palier ; k6 est interrompu (SIGINT, qui
  # le laisse écrire son résultat) au premier écart.
  pods="stables"
  while kill -0 "$pid" 2>/dev/null; do
    for _ in $(seq "$INTERVALLE_SURVEILLANCE"); do
      sleep 1
      kill -0 "$pid" 2>/dev/null || break
    done
    kill -0 "$pid" 2>/dev/null || break
    if ! maintenant=$(etat_pods); then
      pods="relevé impossible"
      kill -INT "$pid"
      break
    fi
    if [[ $maintenant != "$avant" ]]; then
      pods="changés : $(ecart_pods "$avant" "$maintenant")"
      kill -INT "$pid"
      break
    fi
  done
  wait "$pid"
  code=$?
  if [[ $pods == stables ]]; then
    if ! apres=$(etat_pods); then
      pods="relevé impossible"
    elif [[ $apres != "$avant" ]]; then
      pods="changés : $(ecart_pods "$avant" "$apres")"
    fi
  fi

  if [[ ! -s $fichier ]]; then
    echo "k6 n'a produit aucun résultat (code $code). Journal : $journal" >&2
    echo "| $p | $((p * 3)) | — | — | — | — | — | — | — | — | $pods | ERREUR : k6 code $code, sans résultat |" >>"$TABLEAU"
    verdict="erreur"
    break
  fi
  lire_resultat "$fichier"

  motifs=()
  [[ $pods != stables ]] && motifs+=("pods $pods")
  awk -v t="${R[TAUX_ERREUR_PCT]}" 'BEGIN { exit !(t > 1) }' && motifs+=("erreurs ${R[TAUX_ERREUR_PCT]} % > 1 %")
  awk -v t="${R[P95_MS]}" 'BEGIN { exit !(t > 1000) }' && motifs+=("p95 ${R[P95_MS]} ms > 1000 ms")
  (( ${R[RECHERCHES_INEXPLOITABLES]:-0} > 0 )) && motifs+=("${R[RECHERCHES_INEXPLOITABLES]} recherche(s) sans produit")
  (( ${R[FICHES_NON_HTML]:-0} > 0 )) && motifs+=("${R[FICHES_NON_HTML]} fiche(s) non HTML")
  non_lancees=${R[ITERATIONS_NON_LANCEES]:-0}

  if (( ${#motifs[@]} > 0 )); then
    statut="ÉCHEC : $(IFS=';'; echo "${motifs[*]}")"
    (( non_lancees > 0 )) && statut+=" ; $non_lancees itération(s) non lancée(s)"
    verdict="echec"
  elif (( non_lancees > 0 )); then
    statut="INVALIDE : $non_lancees itération(s) non lancée(s), débit demandé non produit"
    verdict="invalide"
  elif [[ $code -ne 0 || ${R[SEUILS_RESPECTES]} != oui || ${R[PALIER_COMPLET]} != oui ]]; then
    statut="ERREUR : k6 code $code, seuils ${R[SEUILS_RESPECTES]}, palier complet ${R[PALIER_COMPLET]}"
    verdict="erreur"
  else
    statut="réussi"
  fi

  ligne="| $p | $((p * 3)) | ${R[DEBIT_OBTENU_PARCOURS_S]} | ${R[REQUETES]} | ${R[P50_MS]} | ${R[P95_MS]} | ${R[P99_MS]} | ${R[TAUX_ERREUR_PCT]} | $non_lancees | ${R[VUS_ACTIFS_MAX]} / ${R[VUS_DISPONIBLES]} | $pods | $statut |"
  echo "$ligne" >>"$TABLEAU"
  echo "$ligne"

  [[ -n $verdict ]] && break
  dernier_reussi=$p

  if [[ $p != "${PALIERS[-1]}" ]]; then
    echo "Pause de $PAUSE_ENTRE_PALIERS s avant le palier suivant."
    sleep "$PAUSE_ENTRE_PALIERS"
    fin_pause=$(etat_pods) || { verdict="erreur"; echo "Relevé des pods impossible pendant la pause." >&2; break; }
    if [[ $fin_pause != "$apres" && $fin_pause != "$avant" ]]; then
      echo "| — | — | — | — | — | — | — | — | — | — | changés pendant la pause : $(ecart_pods "$avant" "$fin_pause") | ÉCHEC : pod redémarré après le palier $p |" >>"$TABLEAU"
      verdict="echec"
      break
    fi
  fi
done

{
  echo
  case $verdict in
    "")
      echo "**Tous les paliers sont passés, jusqu'à ${PALIERS[-1]} parcours/s ($(( ${PALIERS[-1]} * 3 )) requêtes/s) : la limite n'a pas encore été trouvée.** Elle se situe au-delà du dernier palier ; relancer avec des paliers plus élevés (plafond : $PALIER_PLAFOND parcours/s)." ;;
    echec)
      echo "**Limite atteinte au palier $p parcours/s.** Dernier palier réussi : ${dernier_reussi:-aucun}${dernier_reussi:+ parcours/s ($((dernier_reussi * 3)) requêtes/s)}." ;;
    invalide)
      echo "**Mesure invalide au palier $p parcours/s** : k6 n'a pas lancé toutes les itérations demandées. Dernier palier réussi : ${dernier_reussi:-aucun}. Vérifier le générateur (CPU, utilisateurs virtuels) avant de conclure." ;;
    erreur)
      echo "**Campagne interrompue par une erreur au palier $p parcours/s** : voir le journal. Dernier palier réussi : ${dernier_reussi:-aucun}." ;;
  esac
} | tee -a "$TABLEAU"
echo "Résultats : $TABLEAU"
[[ -z $verdict ]]
