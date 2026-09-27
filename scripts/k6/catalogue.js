// Test k6 du catalogue de Dilane Shop.
//
// But : produire un trafic de lecture réaliste pour observer les quatre
// signaux d'or dans Grafana (latence, trafic, erreurs, saturation), et, si la
// latence réelle le permet, voir la règle « Latence p95 élevée » se
// déclencher. Voir docs/observabilite.md, section « Test de charge k6 ».
//
// Uniquement des GET, sur trois routes publiques du catalogue, dans l'ordre
// d'une visite :
//   /                                  page d'accueil (liste paginée)
//   /api/produits/?item-name=<terme>   recherche de produits (JSON)
//   /<id>                              fiche du premier produit trouvé
// Aucun checkout, paiement, création de compte ni écriture.
//
// Variables d'environnement (k6 run -e NOM=valeur) :
//   CIBLE                   obligatoire. https://dilane-shop.store, ou une
//                           adresse locale explicite : http(s)://localhost,
//                           127.0.0.1 ou [::1] (port facultatif), ou
//                           https://dilane-shop.local (cluster kind).
//   MODE                    smoke (défaut) ou charge.
//   VUS                     utilisateurs virtuels du mode charge : 6 par
//                           défaut, 8 au plus. Au-delà, le test refuse de
//                           démarrer.
//   AUTORISER_CHARGE_PROD   doit valoir exactement « oui » pour lancer le
//                           mode charge sur la production.
//   TERME_RECHERCHE         terme cherché, « Casque » par défaut. 1 à 64
//                           caractères ; il doit trouver au moins un produit,
//                           sinon le test échoue.
//
// Exemples :
//   k6 run -e CIBLE=https://dilane-shop.store scripts/k6/catalogue.js
//   k6 run -e CIBLE=https://dilane-shop.store -e MODE=charge \
//          -e AUTORISER_CHARGE_PROD=oui scripts/k6/catalogue.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';
import { Counter, Rate } from 'k6/metrics';

const PRODUCTION = 'https://dilane-shop.store';
const VUS_DEFAUT = 6;
const VUS_PLAFOND = 8;
// Pause après chaque requête, en secondes.
const PAUSE = 0.5;
// Mode smoke : 1 utilisateur, 5 itérations de 3 requêtes, soit 15 requêtes
// quand le parcours réussit.
const ITERATIONS_SMOKE = 5;
const TERME_DEFAUT = 'Casque';
const TERME_LONGUEUR_MAX = 64;
const SCENARIO = 'catalogue';

// ---------------------------------------------------------------------------
// Garde-fous, évalués avant tout envoi : une erreur ici arrête k6 sans
// qu'aucune requête ne soit partie.
// ---------------------------------------------------------------------------

function refuser(message) {
  throw new Error(`Test refusé : ${message}`);
}

// Adresses autorisées, comparées à l'origine complète (schéma, hôte, port),
// sans chemin : « https://dilane-shop.store.exemple.com » ou
// « https://dilane-shop.store@autre-site » ne passent pas.
const ORIGINES_LOCALES = [
  /^https?:\/\/localhost(:\d{1,5})?$/,
  /^https?:\/\/127\.0\.0\.1(:\d{1,5})?$/,
  /^https?:\/\/\[::1\](:\d{1,5})?$/,
  /^https:\/\/dilane-shop\.local$/,
];

function lireCible() {
  const brute = (__ENV.CIBLE || '').trim().replace(/\/+$/, '');
  if (!brute) {
    refuser(`CIBLE est obligatoire, par exemple -e CIBLE=${PRODUCTION} ou -e CIBLE=http://localhost:8000.`);
  }
  if (brute === PRODUCTION) {
    return { origine: brute, production: true };
  }
  if (ORIGINES_LOCALES.some((motif) => motif.test(brute))) {
    return { origine: brute, production: false };
  }
  refuser(`CIBLE « ${brute} » n'est ni ${PRODUCTION} ni une adresse locale explicite (localhost, 127.0.0.1, [::1], dilane-shop.local).`);
}

function lireMode() {
  const mode = (__ENV.MODE || 'smoke').trim().toLowerCase();
  if (mode !== 'smoke' && mode !== 'charge') {
    refuser(`MODE « ${mode} » inconnu : smoke ou charge.`);
  }
  return mode;
}

function lireVus() {
  const brute = (__ENV.VUS || String(VUS_DEFAUT)).trim();
  if (!/^\d+$/.test(brute)) {
    refuser(`VUS « ${brute} » n'est pas un entier.`);
  }
  const vus = parseInt(brute, 10);
  if (vus < 1 || vus > VUS_PLAFOND) {
    refuser(`VUS vaut ${vus} ; il doit être compris entre 1 et ${VUS_PLAFOND}.`);
  }
  return vus;
}

// Terme de recherche. Encodé dans l'URL par encodeURIComponent : espaces,
// accents, « & » ou « # » ne peuvent ni casser la requête ni ajouter de
// paramètre. La longueur est bornée pour garder une requête raisonnable ;
// elle se compte en caractères, pas en octets.
function lireTerme() {
  const terme = (__ENV.TERME_RECHERCHE === undefined ? TERME_DEFAUT : __ENV.TERME_RECHERCHE).trim();
  const longueur = Array.from(terme).length;
  if (longueur < 1 || longueur > TERME_LONGUEUR_MAX) {
    refuser(`TERME_RECHERCHE doit compter de 1 à ${TERME_LONGUEUR_MAX} caractères (${longueur} reçus).`);
  }
  return terme;
}

const { origine: CIBLE, production: EST_PRODUCTION } = lireCible();
const MODE = lireMode();
const VUS = MODE === 'charge' ? lireVus() : 1;
const TERME = lireTerme();
const URL_RECHERCHE = `${CIBLE}/api/produits/?item-name=${encodeURIComponent(TERME)}`;

if (MODE === 'charge' && EST_PRODUCTION && __ENV.AUTORISER_CHARGE_PROD !== 'oui') {
  refuser('le mode charge sur la production exige -e AUTORISER_CHARGE_PROD=oui.');
}

// ---------------------------------------------------------------------------
// Scénarios et seuils.
// ---------------------------------------------------------------------------

const SCENARIOS = {
  smoke: {
    executor: 'per-vu-iterations',
    vus: 1,
    iterations: ITERATIONS_SMOKE,
    maxDuration: '1m',
  },
  charge: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '1m', target: VUS }, // montée
      { duration: '8m', target: VUS }, // palier
      { duration: '1m', target: 0 },   // descente
    ],
    gracefulRampDown: '30s',
  },
};

// Part des réponses en HTTP 200, toutes requêtes confondues.
const reponses200 = new Rate('reponses_http_200');
// Recherches répondues en 200 mais inexploitables : liste vide, JSON
// illisible, ou premier produit sans identifiant entier positif. Ce n'est
// pas une défaillance passagère sous charge mais un terme ou un catalogue
// inadapté : une seule suffit à faire échouer le test.
const recherchesInexploitables = new Counter('recherches_inexploitables');
// Fiches répondues en 200 mais pas en HTML : une seule fait échouer le test.
const fichesNonHtml = new Counter('fiches_non_html');

// abortOnFail : le test s'arrête dès qu'un seuil est franchi, au lieu de
// continuer à charger un site qui souffre. delayAbortEval laisse passer les
// premières secondes, où trop peu de mesures rendent les taux instables.
const ARRET = { abortOnFail: true, delayAbortEval: '10s' };

export const options = {
  scenarios: { [SCENARIO]: SCENARIOS[MODE] },
  thresholds: {
    // Arrêt si 2 % des requêtes échouent (erreur réseau ou statut >= 400).
    http_req_failed: [{ threshold: 'rate<0.02', ...ARRET }],
    // Arrêt si le p95 vu par k6 atteint 5 secondes.
    http_req_duration: [{ threshold: 'p(95)<5000', ...ARRET }],
    // Arrêt si moins de 98 % des réponses sont des HTTP 200.
    reponses_http_200: [{ threshold: 'rate>=0.98', ...ARRET }],
    // Arrêt dès qu'une recherche ne donne aucun produit exploitable.
    recherches_inexploitables: [{ threshold: 'count==0', ...ARRET }],
    // Arrêt dès qu'une fiche répond 200 sans être une page HTML.
    fiches_non_html: [{ threshold: 'count==0', ...ARRET }],
  },
  // Certificat auto-signé du cluster kind uniquement. Jamais pour la
  // production, dont le certificat Let's Encrypt doit être valide.
  insecureSkipTLSVerify: CIBLE === 'https://dilane-shop.local',
  // Identifie ce trafic dans les journaux d'ingress-nginx.
  userAgent: 'dilane-shop-k6-catalogue/1.0',
  // Statistiques de durée affichées dans le résumé de fin de test.
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'max'],
};

// ---------------------------------------------------------------------------
// setup : dernier contrôle, sur les options effectives.
// ---------------------------------------------------------------------------

// Les options de la ligne de commande (--vus, --duration, --iterations,
// --stages) remplacent les scénarios du script et contourneraient le
// plafond de VUS. setup() s'exécute avant le premier utilisateur virtuel :
// le test y est interrompu si les scénarios effectifs ne sont pas ceux
// définis ici.
export function setup() {
  const effectifs = exec.test.options.scenarios || {};
  const noms = Object.keys(effectifs);
  const attendu = SCENARIOS[MODE];
  const scenario = effectifs[SCENARIO];
  const conforme =
    noms.length === 1 &&
    scenario !== undefined &&
    scenario.executor === attendu.executor &&
    (MODE === 'smoke'
      ? scenario.vus === 1 && scenario.iterations === ITERATIONS_SMOKE
      : (scenario.startVUs || 0) === 0 &&
        (scenario.stages || []).length === attendu.stages.length &&
        scenario.stages.every((etape) => etape.target <= VUS_PLAFOND));
  if (!conforme) {
    exec.test.abort(
      'Test refusé : les scénarios ont été modifiés en ligne de commande ' +
        '(--vus, --duration, --iterations ou --stages). Utiliser MODE et VUS.',
    );
  }
  console.log(
    `Cible ${CIBLE} — mode ${MODE} — recherche « ${TERME} »` +
      (MODE === 'charge'
        ? ` — ${VUS} utilisateurs virtuels, 10 minutes`
        : ` — ${ITERATIONS_SMOKE * 3} requêtes attendues`),
  );
}

// ---------------------------------------------------------------------------
// Parcours d'un utilisateur virtuel : accueil, recherche, fiche du premier
// produit trouvé ; une pause après chaque requête.
// ---------------------------------------------------------------------------

function estHtml(reponse) {
  return (reponse.headers['Content-Type'] || '').includes('text/html');
}

// Le tag « name » regroupe les mesures par route dans le résumé, quelle que
// soit l'URL exacte : toutes les fiches sont comptées sous « fiche-produit ».
function lire(url, nom, verifications) {
  const reponse = http.get(url, { tags: { name: nom }, timeout: '15s' });
  reponses200.add(reponse.status === 200);
  check(reponse, verifications);
  sleep(PAUSE);
  return reponse;
}

// Identifiant du premier produit renvoyé par la recherche, ou null si la
// réponse n'en fournit pas d'exploitable.
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
  lire(`${CIBLE}/`, 'accueil', {
    'accueil : HTTP 200': (r) => r.status === 200,
    'accueil : page HTML': estHtml,
  });

  const recherche = lire(URL_RECHERCHE, 'api-produits', {
    'api-produits : HTTP 200': (r) => r.status === 200,
  });
  // Une recherche en erreur HTTP relève des seuils d'erreur ci-dessus, qui
  // tolèrent de rares échecs sous charge ; la fiche est alors sautée.
  if (recherche.status !== 200) {
    return;
  }
  const id = premierIdentifiant(recherche);
  check(id, { 'api-produits : au moins un produit, identifiant valide': (v) => v !== null });
  if (id === null) {
    recherchesInexploitables.add(1);
    return;
  }

  const fiche = lire(`${CIBLE}/${id}`, 'fiche-produit', {
    'fiche-produit : HTTP 200': (r) => r.status === 200,
    'fiche-produit : page HTML': estHtml,
  });
  if (fiche.status === 200 && !estHtml(fiche)) {
    fichesNonHtml.add(1);
  }
}
