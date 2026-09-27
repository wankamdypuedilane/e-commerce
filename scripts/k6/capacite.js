// Test de capacité de Dilane Shop — un palier à débit imposé.
//
// Cible unique et non modifiable : https://capacite.dilane-shop.store,
// l'environnement de capacité (k8s/overlays/capacite). Jamais la production.
// Voir docs/test-capacite.md.
//
// Chaque itération est un parcours en lecture seule, sans pause :
//   GET /                                   accueil
//   GET /api/produits/?item-name=<terme>    recherche, qui doit trouver
//   GET /<id>                               fiche du premier produit trouvé
//
// Débit imposé (constant-arrival-rate) : k6 lance PALIER parcours par
// seconde pendant 5 minutes, que le site réponde vite ou non. Contrairement
// à des utilisateurs virtuels qui attendent leur réponse, la charge ne
// baisse pas quand le site ralentit : c'est ce qui permet de trouver une
// limite. Un palier par exécution de k6 ; la campagne (enchaînement des
// paliers, arrêt au premier échec, surveillance des pods) est menée par
// scripts/capacite/campagne.sh.
//
// Variables (k6 run -e NOM=valeur) :
//   CONFIRMER_CAPACITE   doit valoir exactement « oui ».
//   PALIER               parcours par seconde, entier de 1 à 50 (3 requêtes
//                        par parcours, soit au plus 150 requêtes/s).
//   TERME_RECHERCHE      « Casque » par défaut, 1 à 64 caractères.
//   FICHIER_RESULTAT     facultatif : fichier « CLE=valeur » écrit en fin
//                        de palier, lu par campagne.sh.
import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';
import { Counter } from 'k6/metrics';

const CIBLE = 'https://capacite.dilane-shop.store';
const PALIER_PLAFOND = 50;
const DUREE = '5m';
const DUREE_SECONDES = 300;
// Utilisateurs virtuels disponibles pour tenir le débit : il en faut
// environ la durée d'un parcours (en secondes) fois le débit. 6 par
// parcours/s couvrent des parcours de 6 s, bien au-delà du seuil de p95.
// Plafonnés pour borner la charge du générateur et du site.
const VUS_PAR_PARCOURS_S = 6;
const VUS_PLAFOND = 150;
const TERME_DEFAUT = 'Casque';
const TERME_LONGUEUR_MAX = 64;
const SCENARIO = 'palier';

// ---------------------------------------------------------------------------
// Garde-fous, évalués avant tout envoi.
// ---------------------------------------------------------------------------

function refuser(message) {
  throw new Error(`Test refusé : ${message}`);
}

if (__ENV.CONFIRMER_CAPACITE !== 'oui') {
  refuser(`ce script charge ${CIBLE} ; confirmer par -e CONFIRMER_CAPACITE=oui.`);
}
if (__ENV.CIBLE !== undefined) {
  refuser(`la cible est fixée à ${CIBLE} et ne se change pas ; retirer CIBLE.`);
}

function lirePalier() {
  const brut = (__ENV.PALIER || '').trim();
  if (!/^\d+$/.test(brut)) {
    refuser(`PALIER est obligatoire : un entier de parcours par seconde, de 1 à ${PALIER_PLAFOND}.`);
  }
  const palier = parseInt(brut, 10);
  if (palier < 1 || palier > PALIER_PLAFOND) {
    refuser(`PALIER vaut ${palier} ; il doit être compris entre 1 et ${PALIER_PLAFOND}.`);
  }
  return palier;
}

function lireTerme() {
  const terme = (__ENV.TERME_RECHERCHE === undefined ? TERME_DEFAUT : __ENV.TERME_RECHERCHE).trim();
  const longueur = Array.from(terme).length;
  if (longueur < 1 || longueur > TERME_LONGUEUR_MAX) {
    refuser(`TERME_RECHERCHE doit compter de 1 à ${TERME_LONGUEUR_MAX} caractères (${longueur} reçus).`);
  }
  return terme;
}

const PALIER = lirePalier();
const TERME = lireTerme();
const URL_RECHERCHE = `${CIBLE}/api/produits/?item-name=${encodeURIComponent(TERME)}`;
// Tous pré-alloués : un utilisateur virtuel créé en cours de palier prend
// du temps, et k6 abandonne des itérations pendant ce temps. Ainsi, une
// itération non lancée signale un vrai manque (parcours trop lents), pas
// un démarrage.
const VUS_MAX = Math.min(PALIER * VUS_PAR_PARCOURS_S, VUS_PLAFOND);
const VUS_PREALLOUES = VUS_MAX;

// ---------------------------------------------------------------------------
// Scénario et seuils d'arrêt.
// ---------------------------------------------------------------------------

const SCENARIO_ATTENDU = {
  executor: 'constant-arrival-rate',
  rate: PALIER,
  timeUnit: '1s',
  duration: DUREE,
  preAllocatedVUs: VUS_PREALLOUES,
  maxVUs: VUS_MAX,
};

const recherchesInexploitables = new Counter('recherches_inexploitables');
const fichesNonHtml = new Counter('fiches_non_html');

// Arrêt au plus tôt 30 s après le début du palier : les toutes premières
// mesures, peu nombreuses et prises à froid, rendraient p95 et taux instables.
const ARRET = { abortOnFail: true, delayAbortEval: '30s' };

export const options = {
  scenarios: { [SCENARIO]: SCENARIO_ATTENDU },
  thresholds: {
    // Échec du palier au-delà de 1 % de requêtes en erreur (réseau ou
    // statut >= 400).
    http_req_failed: [{ threshold: 'rate<=0.01', ...ARRET }],
    // Échec du palier au-delà d'un p95 client d'une seconde.
    http_req_duration: [{ threshold: 'p(95)<=1000', ...ARRET }],
    // Itérations que k6 n'a pas pu lancer faute d'utilisateur virtuel
    // libre : le débit demandé n'a pas été produit, la mesure ne vaut pas
    // pour ce débit. Le palier est déclaré invalide.
    dropped_iterations: [{ threshold: 'count==0', ...ARRET }],
    // Parcours incohérents : recherche sans produit exploitable, fiche qui
    // n'est pas une page HTML. Un terme ou un catalogue inadapté fausserait
    // toute la mesure.
    recherches_inexploitables: [{ threshold: 'count==0', ...ARRET }],
    fiches_non_html: [{ threshold: 'count==0', ...ARRET }],
  },
  userAgent: 'dilane-shop-k6-capacite/1.0',
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

// Durée k6 (« 5m », « 5m0s », « 1s », « 1m30s ») en secondes. k6 rend les
// durées de ses options sous forme normalisée (« 5m0s ») : elles ne se
// comparent pas comme des chaînes.
function secondes(duree) {
  const motif = /(\d+(?:\.\d+)?)(ms|h|m|s)/g;
  const unites = { h: 3600, m: 60, s: 1, ms: 0.001 };
  let total = 0;
  let trouve = false;
  let m;
  while ((m = motif.exec(String(duree))) !== null) {
    total += parseFloat(m[1]) * unites[m[2]];
    trouve = true;
  }
  return trouve ? total : NaN;
}

// Les options de ligne de commande (--vus, --duration, --iterations)
// remplaceraient le scénario et ses bornes : le palier est alors refusé
// avant le premier parcours.
export function setup() {
  const effectifs = exec.test.options.scenarios || {};
  const s = effectifs[SCENARIO];
  const conforme =
    Object.keys(effectifs).length === 1 &&
    s !== undefined &&
    s.executor === SCENARIO_ATTENDU.executor &&
    s.rate === SCENARIO_ATTENDU.rate &&
    s.preAllocatedVUs === SCENARIO_ATTENDU.preAllocatedVUs &&
    s.maxVUs === SCENARIO_ATTENDU.maxVUs &&
    secondes(s.timeUnit) === secondes(SCENARIO_ATTENDU.timeUnit) &&
    secondes(s.duration) === secondes(SCENARIO_ATTENDU.duration);
  if (!conforme) {
    exec.test.abort('Test refusé : le scénario a été modifié en ligne de commande. Utiliser PALIER.');
  }
  console.log(
    `${CIBLE} — palier ${PALIER} parcours/s (${PALIER * 3} requêtes/s), ${DUREE}, ` +
      `recherche « ${TERME} », ${VUS_PREALLOUES} à ${VUS_MAX} utilisateurs virtuels`,
  );
}

// ---------------------------------------------------------------------------
// Parcours.
// ---------------------------------------------------------------------------

function estHtml(reponse) {
  return (reponse.headers['Content-Type'] || '').includes('text/html');
}

function lire(url, nom) {
  return http.get(url, { tags: { name: nom }, timeout: '10s' });
}

function premierIdentifiant(reponse) {
  let produits;
  try {
    produits = reponse.json('products');
  } catch (erreur) {
    return null;
  }
  if (!Array.isArray(produits) || produits.length === 0) {
    return null;
  }
  const id = produits[0] && produits[0].id;
  return Number.isInteger(id) && id > 0 ? id : null;
}

export default function () {
  const accueil = lire(`${CIBLE}/`, 'accueil');
  check(accueil, { 'accueil : HTTP 200': (r) => r.status === 200 });

  const recherche = lire(URL_RECHERCHE, 'api-produits');
  check(recherche, { 'api-produits : HTTP 200': (r) => r.status === 200 });
  if (recherche.status !== 200) {
    return; // compté par http_req_failed
  }
  const id = premierIdentifiant(recherche);
  if (!check(id, { 'api-produits : produit trouvé': (v) => v !== null })) {
    recherchesInexploitables.add(1);
    return;
  }

  const fiche = lire(`${CIBLE}/${id}`, 'fiche-produit');
  check(fiche, {
    'fiche-produit : HTTP 200': (r) => r.status === 200,
    'fiche-produit : page HTML': estHtml,
  });
  if (fiche.status === 200 && !estHtml(fiche)) {
    fichesNonHtml.add(1);
  }
}

// ---------------------------------------------------------------------------
// Résultat du palier : résumé lisible, et fichier « CLE=valeur » pour la
// campagne.
// ---------------------------------------------------------------------------

function valeur(data, metrique, stat, defaut) {
  const m = data.metrics[metrique];
  return m && m.values[stat] !== undefined ? m.values[stat] : defaut;
}

function seuilsRespectes(data) {
  return Object.values(data.metrics).every((m) =>
    Object.values(m.thresholds || {}).every((t) => t.ok),
  );
}

export function handleSummary(data) {
  const iterations = valeur(data, 'iterations', 'count', 0);
  const nonLancees = valeur(data, 'dropped_iterations', 'count', 0);
  const requetes = valeur(data, 'http_reqs', 'count', 0);
  const duree = data.state.testRunDurationMs / 1000;
  const resultat = {
    PALIER: PALIER,
    DEBIT_DEMANDE_PARCOURS_S: PALIER,
    DUREE_S: duree.toFixed(0),
    ITERATIONS: iterations,
    ITERATIONS_NON_LANCEES: nonLancees,
    DEBIT_OBTENU_PARCOURS_S: duree > 0 ? (iterations / duree).toFixed(2) : '0',
    REQUETES: requetes,
    DEBIT_REQUETES_S: valeur(data, 'http_reqs', 'rate', 0).toFixed(2),
    P50_MS: valeur(data, 'http_req_duration', 'med', 0).toFixed(1),
    P95_MS: valeur(data, 'http_req_duration', 'p(95)', 0).toFixed(1),
    P99_MS: valeur(data, 'http_req_duration', 'p(99)', 0).toFixed(1),
    TAUX_ERREUR_PCT: (valeur(data, 'http_req_failed', 'rate', 0) * 100).toFixed(2),
    RECHERCHES_INEXPLOITABLES: valeur(data, 'recherches_inexploitables', 'count', 0),
    FICHES_NON_HTML: valeur(data, 'fiches_non_html', 'count', 0),
    // Utilisateurs virtuels simultanément occupés, au plus : proche de
    // VUS_MAX, le générateur arrivait à court.
    VUS_ACTIFS_MAX: valeur(data, 'vus', 'max', 0),
    VUS_DISPONIBLES: VUS_MAX,
    PALIER_COMPLET: duree >= DUREE_SECONDES - 1 ? 'oui' : 'non',
    SEUILS_RESPECTES: seuilsRespectes(data) ? 'oui' : 'non',
  };
  const lignes = Object.entries(resultat).map(([cle, v]) => `${cle}=${v}`);
  const sorties = {
    stdout: `\nRésultat du palier ${PALIER} parcours/s\n  ${lignes.join('\n  ')}\n`,
  };
  if (__ENV.FICHIER_RESULTAT) {
    sorties[__ENV.FICHIER_RESULTAT] = `${lignes.join('\n')}\n`;
  }
  return sorties;
}
