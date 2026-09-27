# Test de capacité — environnement `capacite.dilane-shop.store`

Mesurer jusqu'où le site tient, **sans jamais charger la production**. Le test tourne sur un environnement séparé, comparable à la production, monté pour la campagne puis détruit.

Ce document prépare la campagne ; rien n'est encore commandé ni déployé. Les commandes suivent les conventions de [deploiement-production.md](deploiement-production.md) : **PORTABLE** désigne le poste qui détient la clé age, **CAPACITÉ** un shell sur le VPS de capacité, **GÉNÉRATEUR** la machine qui envoie la charge.

## Principe

| | Production | Capacité |
| --- | --- | --- |
| Machine | VPS OVH, 4 Go, sans swap | **VPS distinct**, même offre, même nombre de vCPU, sans swap |
| Domaine | `dilane-shop.store` | `capacite.dilane-shop.store` |
| Surcouche | `k8s/overlays/production` | `k8s/overlays/capacite` |
| Image, replicas, ressources | — | **identiques** (vérifié par `comparer_production.py`) |
| Prometheus et Grafana | alertes par courriel | mêmes limites mémoire, **sans SMTP** |
| Secrets | production | **propres** : aucune clé Stripe ni Brevo |
| Données | réelles | **uniquement** `fixtures/demo-catalogue.json` : 5 catégories, 25 produits, aucun compte, aucune commande |
| Paiement, courriels | actifs | **inactifs** (voir ci-dessous) |

Le script de mesure n'est **pas** `scripts/k6/catalogue.js`, qui protège la production par un plafond de 8 utilisateurs virtuels et ne peut donc pas trouver de limite. C'est [scripts/k6/capacite.js](../scripts/k6/capacite.js), qui ne connaît qu'une cible, `https://capacite.dilane-shop.store`.

### Pourquoi une surcouche dédiée

La surcouche de production ne s'applique pas telle quelle : elle porte le domaine `dilane-shop.store`, son certificat et les alertes Grafana par courriel. [k8s/overlays/capacite](../k8s/overlays/capacite/) part de `k8s/base`, reprend la pile d'observabilité de la production et n'en retire que le SMTP.

### Paiement et courriels inactifs

Trois barrières indépendantes :

1. **Pas d'identifiants.** Le Secret de capacité ne contient que `DJANGO_SECRET_KEY` et `DB_PASSWORD`. Sans `STRIPE_SECRET_KEY` ni `STRIPE_PUBLIC_KEY`, Django considère Stripe comme non configuré (`stripe_is_configured()`) et n'ouvre aucune session de paiement. Sans identifiants Brevo, aucun envoi ne peut s'authentifier.
2. **Pas de sortie réseau.** L'image de production envoie ses courriels par le SMTP de Brevo (`EMAIL_BACKEND` est fixé dans `settings.py`, sans variable pour le changer). La NetworkPolicy [reseau-sortie.yaml](../k8s/overlays/capacite/reseau-sortie.yaml) limite la sortie des pods de `dilane-shop` au DNS et à PostgreSQL : ni SMTP ni API Stripe ne sont joignables.
3. **Routes fermées.** [routes-fermees.yaml](../k8s/overlays/capacite/routes-fermees.yaml) fait répondre **503** à l'Ingress, avant Django, sur `/checkout`, `/paiement`, `/confirmation`, `/webhooks`, `/inscription`, `/connexion`, `/profil`, `/mot-de-passe-oublie`, `/reinitialisation` et `/admin`.

Grafana n'a pas de serveur SMTP ([patch-grafana-sans-smtp.yaml](../k8s/overlays/capacite/patch-grafana-sans-smtp.yaml)). Ses règles d'alerte restent évaluées, pour lire leur état pendant la campagne ; le point de contact courriel échoue alors, ce qui est voulu.

La sauvegarde quotidienne est suspendue : rien à sauvegarder, et un `pg_dump` à 3 h fausserait une mesure.

## Contenu du dépôt

| Fichier | Rôle |
| --- | --- |
| `k8s/overlays/capacite/` | surcouche Kubernetes de l'environnement |
| `k8s/overlays/capacite/secrets.sops.yaml` | Secret `dilane-shop-secrets` de capacité, chiffré : deux valeurs aléatoires propres à cet environnement |
| `k8s/overlays/capacite/grafana-admin.sops.yaml` | compte administrateur Grafana de capacité, chiffré |
| `scripts/capacite/comparer_production.py` | vérifie, sans cluster, que replicas, stratégies, images, ressources et volumes sont ceux de la production |
| `scripts/capacite/verifier-cluster.sh` | garde-fou : refuse d'agir sur un cluster qui pourrait être la production |
| `scripts/capacite/campagne.sh` | enchaîne les paliers, surveille les pods, s'arrête au premier échec |
| `scripts/k6/capacite.js` | un palier à débit imposé, en lecture seule |

Les deux Secrets ont été générés aléatoirement et chiffrés directement pour la clé age de [.sops.yaml](../.sops.yaml) : leurs valeurs n'ont jamais été écrites en clair ni affichées. Ils ne servent qu'à cet environnement ; pour les régénérer, voir [Régénérer les Secrets](#régénérer-les-secrets).

## Garde-fous

| Risque | Garde-fou |
| --- | --- |
| Charger la production | `capacite.js` a une cible fixe, sans variable pour la changer ; `CIBLE` est refusée. `verifier-cluster.sh` refuse la campagne si `capacite.dilane-shop.store` résout vers l'adresse de `dilane-shop.store`. |
| Appliquer la surcouche sur le cluster de production | `verifier-cluster.sh avant-deploiement` refuse un cluster dont l'espace de noms `dilane-shop` n'a pas l'étiquette `dilane-shop.store/environnement=capacite`, ou dont un Ingress sert `dilane-shop.store`. Les `ClusterIssuer` de capacité portent des noms distincts de ceux de la production. |
| Lancement accidentel | `CONFIRMER_CAPACITE=oui` exigé par `capacite.js` et `campagne.sh`. |
| Débit et durée sans borne | 50 parcours/s au plus (150 requêtes/s) ; 150 utilisateurs virtuels au plus ; 5 minutes par palier ; 10 paliers au plus, soit 60 minutes. Les options `--vus`, `--duration`, `--iterations` sont refusées. |
| Écriture, paiement, courriel | voir [Paiement et courriels inactifs](#paiement-et-courriels-inactifs) ; le parcours ne fait que des GET. |
| Mesure faussée par un site qui s'effondre | arrêt dès qu'un palier dépasse 1 % d'erreurs, un p95 client d'1 s, ou qu'un pod redémarre. |

## 1. Préparation (actions manuelles)

**Commander le VPS** : même offre OVH que la production (4 Go, même nombre de vCPU), Ubuntu, **sans swap**. Le durcir et installer k3s, ingress-nginx (avec le correctif `hostPort`) et cert-manager en suivant les sections 2 à 4 de [deploiement-production.md](deploiement-production.md), à l'identique.

**Alias SSH** sur le portable, dans `~/.ssh/config`, distinct de celui de la production :

```
Host capacite
    HostName <adresse IPv4 du VPS de capacité>
    User ubuntu
    IdentityFile ~/.ssh/dilane-shop-vps
```

**DNS** : un enregistrement `A` `capacite.dilane-shop.store` → adresse du **VPS de capacité**. Jamais celle de la production.

```bash
# PORTABLE
getent hosts capacite.dilane-shop.store   # adresse du VPS de capacité
getent hosts dilane-shop.store            # adresse de la production : doit différer
```

**Dépôt** sur le VPS de capacité :

```bash
# CAPACITÉ
git clone https://github.com/wankamdypuedilane/e-commerce.git ~/e-commerce
```

**Générateur de charge** : une troisième machine, ni le VPS de capacité ni la production, proche du centre de données OVH, avec Docker ou k6 v2.3.0. Le générateur ne doit pas être le goulot : au moins 2 vCPU libres, et surveiller son CPU pendant la campagne.

## 2. Vérifications avant déploiement

**PORTABLE** — depuis la racine du dépôt, sans contacter aucun cluster :

```bash
kubectl kustomize k8s/overlays/capacite > /dev/null && echo "construction OK"
python3 scripts/capacite/comparer_production.py     # requiert PyYAML
sops --decrypt k8s/overlays/capacite/secrets.sops.yaml > /dev/null && echo "Secret déchiffrable"
```

Attendu : `Identique à la production : 9 objets comparés`.

**PORTABLE** — sur le cluster de capacité, avant d'y appliquer quoi que ce soit :

```bash
CAPACITE_SSH=capacite scripts/capacite/verifier-cluster.sh avant-deploiement
```

## 3. Déploiement

**CAPACITÉ** — espaces de noms, l'un étiqueté comme environnement de capacité :

```bash
cd ~/e-commerce
kubectl apply -f k8s/base/00-namespace.yaml
kubectl label namespace dilane-shop dilane-shop.store/environnement=capacite
kubectl apply -f k8s/overlays/production/observabilite/00-namespace.yaml
```

**PORTABLE** — Secrets de capacité, déchiffrés localement et transmis par SSH :

```bash
sops --decrypt k8s/overlays/capacite/secrets.sops.yaml | ssh capacite "kubectl apply -f -"
sops --decrypt k8s/overlays/capacite/grafana-admin.sops.yaml | ssh capacite "kubectl apply -f -"
```

**CAPACITÉ** — surcouche :

```bash
cd ~/e-commerce
kubectl apply -k k8s/overlays/capacite
kubectl wait -n dilane-shop --for=condition=ready pod -l app.kubernetes.io/name=postgres --timeout=300s
kubectl wait -n dilane-shop --for=condition=complete job/django-migrate --timeout=300s
kubectl rollout status -n dilane-shop deploy/django --timeout=300s
kubectl rollout status -n observabilite deploy/prometheus --timeout=300s
kubectl rollout status -n observabilite deploy/grafana --timeout=300s
```

Le Job de migration applique les migrations puis charge `fixtures/demo-catalogue.json`. S'il a échoué parce que PostgreSQL n'était pas prêt (voir la même remarque dans le guide de production) : `kubectl delete job django-migrate -n dilane-shop` puis réappliquer la surcouche.

## 4. Vérifications après déploiement

**CAPACITÉ** — certificat, données, sortie réseau, Grafana :

```bash
kubectl get certificate -n dilane-shop capacite-tls          # READY True

# Uniquement le catalogue de démonstration : 5 / 25 / 0 / 0 / 0
kubectl exec -n dilane-shop deploy/django -- python manage.py shell -c "
from django.contrib.auth import get_user_model
from shop.models import Category, Product, Commande, OrderItem
print('catégories', Category.objects.count(), 'produits', Product.objects.count(),
      'commandes', Commande.objects.count(), 'lignes', OrderItem.objects.count(),
      'comptes', get_user_model().objects.count())"

# Sortie bloquée : les deux connexions doivent échouer (délai dépassé)
kubectl exec -n dilane-shop deploy/django -- python -c "
import socket
for hote, port in [('smtp-relay.brevo.com', 587), ('api.stripe.com', 443)]:
    try:
        socket.create_connection((hote, port), timeout=5); print('OUVERT', hote)
    except OSError as e:
        print('bloqué', hote, type(e).__name__)"

# Grafana sans SMTP : seule GF_SMTP_ENABLED=false doit apparaître
kubectl exec -n observabilite deploy/grafana -- env | grep '^GF_SMTP'
```

**PORTABLE** — routes, une requête chacune :

```bash
for chemin in / "/api/produits/?item-name=Casque" /3 /checkout /paiement/succes/ /admin/ /inscription/; do
  printf '%-32s %s\n' "$chemin" "$(curl -s -o /dev/null -w '%{http_code}' "https://capacite.dilane-shop.store$chemin")"
done
```

Attendu : `200` pour `/`, la recherche et `/3` ; `503` pour les autres.

**PORTABLE** — garde-fou complet, à repasser juste avant la campagne :

```bash
CAPACITE_SSH=capacite scripts/capacite/verifier-cluster.sh avant-campagne
```

## 5. Exécution de la campagne

### Ce qui est mesuré

Chaque parcours enchaîne trois GET, sans pause : l'accueil, la recherche `/api/produits/?item-name=Casque` (qui doit trouver un produit), et la fiche du premier produit trouvé.

Chaque palier impose un **débit** de parcours par seconde pendant **5 minutes** (exécuteur `constant-arrival-rate`). Contrairement à des utilisateurs qui attendent leur réponse, la charge ne baisse pas quand le site ralentit : c'est ce qui fait apparaître une limite. Un palier = une exécution de k6, suivie d'une minute de pause.

Un palier **échoue** si :
- plus de 1 % des requêtes sont en erreur (réseau ou statut ≥ 400) ;
- le p95 vu par k6 dépasse 1 seconde ;
- une recherche ne trouve aucun produit, ou une fiche n'est pas une page HTML ;
- un pod de `dilane-shop` ou d'`observabilite` redémarre, est remplacé ou disparaît, pendant le palier ou la pause qui suit (relevé toutes les 15 s ; k6 est alors interrompu).

k6 arrête le palier dès qu'un de ses seuils est franchi, au plus tôt 30 s après son début.

Un palier est **invalide** si k6 n'a pas pu lancer toutes les itérations demandées (`dropped_iterations`), faute d'utilisateur virtuel libre : le débit demandé n'a pas été produit, et les mesures ne valent pas pour ce débit. Les utilisateurs virtuels sont tous pré-alloués (6 par parcours/s, 150 au plus) ; une itération non lancée signale donc des parcours de plus de 6 s, ou un générateur à court de CPU.

### Lancer

**GÉNÉRATEUR** — depuis la racine du dépôt, avec l'alias SSH `capacite` disponible sur cette machine :

```bash
# Sans k6 installé :
export K6="docker run --rm -i --user $(id -u):$(id -g) -v $PWD:/depot -w /depot grafana/k6:2.3.0"

# Paliers par défaut : 2 4 8 12 16 24 32 40 parcours/s (6 à 120 requêtes/s), 48 min au plus
CONFIRMER_CAPACITE=oui CAPACITE_SSH=capacite scripts/capacite/campagne.sh

# Paliers choisis (entiers croissants, 1 à 50, 10 au plus) :
CONFIRMER_CAPACITE=oui CAPACITE_SSH=capacite scripts/capacite/campagne.sh 20 30 40 50
```

`--user` est nécessaire avec Docker : l'image k6 tourne sous un utilisateur non privilégié, qui doit pouvoir écrire dans `resultats/`.

Résultats dans `resultats/capacite-<date>/` (ignoré par Git) : `resultats.md` (tableau et conclusion), puis par palier `palier-N.env` (valeurs mesurées) et `palier-N.log` (journal de k6).

La campagne se termine par l'une de ces conclusions :

| Conclusion | Sens |
| --- | --- |
| Limite atteinte au palier N | Premier palier en échec. La capacité mesurée est celle du dernier palier réussi. |
| Mesure invalide au palier N | Le générateur n'a pas produit le débit. Vérifier son CPU avant de conclure ; relancer à partir de ce palier. |
| Tous les paliers sont passés : la limite n'a pas encore été trouvée | Le site a tenu le dernier palier. Relancer avec des paliers plus élevés, jusqu'au plafond de 50 parcours/s. |
| Campagne interrompue par une erreur | k6 n'a pas produit de résultat (refus, script) : voir le journal. |

### Observer pendant la campagne

Dans un autre terminal du portable, Grafana par tunnel (compte du Secret `grafana-admin` de capacité, voir [Régénérer les Secrets](#régénérer-les-secrets) pour le lire) :

```bash
ssh -L 3000:127.0.0.1:3000 capacite "kubectl port-forward -n observabilite svc/grafana 3000:3000"
```

Et sur le VPS de capacité, pendant chaque palier :

```bash
# CAPACITÉ
free -m
kubectl top pods -A
kubectl exec -n dilane-shop statefulset/postgres -- psql -U postgres -tAc "select count(*) from pg_stat_activity"
```

## 6. Tableau de résultats

`campagne.sh` remplit les colonnes mesurées par k6 dans `resultats.md`. Les colonnes d'observation se relèvent à la main, au milieu de chaque palier. Recopier le tout ici, ou dans l'issue de la campagne.

Date : ………… — Image : `5df4ad5763edebca35b8175970d6d0f6fcb0abc2` — VPS : ………… (vCPU, mémoire) — Générateur : …………

| Palier (parcours/s) | Requêtes/s demandées | Parcours/s obtenus | Requêtes | p50 k6 (ms) | p95 k6 (ms) | p99 k6 (ms) | Erreurs (%) | Itérations non lancées | p95 Django, Grafana (ms) | Saturation max (requêtes en cours / pod) | CPU nœud (%) | Mémoire libre nœud (Mo) | Connexions PostgreSQL | Redémarrages | Statut |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | 6 | | | | | | | | | | | | | | |
| 4 | 12 | | | | | | | | | | | | | | |
| 8 | 24 | | | | | | | | | | | | | | |
| 12 | 36 | | | | | | | | | | | | | | |
| 16 | 48 | | | | | | | | | | | | | | |
| 24 | 72 | | | | | | | | | | | | | | |
| 32 | 96 | | | | | | | | | | | | | | |
| 40 | 120 | | | | | | | | | | | | | | |

Conclusion : limite atteinte au palier …… / limite non trouvée au-delà de …… parcours/s. Premier symptôme observé : ……

Pour lire l'écart entre p95 k6 et p95 Django, voir [Latence k6 et latence Grafana](observabilite.md#latence-k6-et-latence-grafana--deux-mesures-différentes) : un p95 k6 élevé avec un p95 Django bas signale une attente devant les workers gunicorn, pas une application lente.

## 7. Destruction de l'environnement

Une fois les résultats recopiés :

1. **Résultats** : conserver `resultats/capacite-<date>/` hors du dépôt, ou les recopier dans l'issue.
2. **VPS** : le résilier dans l'espace client OVH (action manuelle). Le cluster, les données de démonstration et les Secrets déployés disparaissent avec lui.
3. **DNS** : supprimer l'enregistrement `A` `capacite.dilane-shop.store`. Vérifier : `getent hosts capacite.dilane-shop.store` ne doit plus rien rendre.
4. **SSH** : retirer l'entrée `Host capacite` de `~/.ssh/config` et la clé d'hôte correspondante de `~/.ssh/known_hosts` (`ssh-keygen -R <adresse>`).
5. **Secrets** : ceux de `k8s/overlays/capacite` ne donnent accès à rien d'autre que cet environnement. Les régénérer avant une nouvelle campagne.

Pour vider l'environnement sans détruire le VPS (nouvelle campagne à partir d'une base neuve) :

```bash
# CAPACITÉ
kubectl delete namespace dilane-shop observabilite
kubectl delete clusterissuer letsencrypt-capacite
kubectl delete priorityclass observabilite-faible-priorite
```

## Régénérer les Secrets

**PORTABLE** — valeurs aléatoires chiffrées directement, jamais affichées ni écrites en clair :

```bash
D=k8s/overlays/capacite
{ printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: dilane-shop-secrets\n  namespace: dilane-shop\ntype: Opaque\nstringData:\n'
  printf '  DJANGO_SECRET_KEY: "%s"\n' "$(openssl rand -hex 32)"
  printf '  DB_PASSWORD: "%s"\n' "$(openssl rand -hex 24)"
} | sops --encrypt --filename-override $D/secrets.sops.yaml --input-type yaml --output-type yaml /dev/stdin > $D/secrets.sops.yaml

{ printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: grafana-admin\n  namespace: observabilite\ntype: Opaque\nstringData:\n'
  printf '  admin-user: "admin"\n'
  printf '  admin-password: "%s"\n' "$(openssl rand -hex 24)"
} | sops --encrypt --filename-override $D/grafana-admin.sops.yaml --input-type yaml --output-type yaml /dev/stdin > $D/grafana-admin.sops.yaml
```

`DB_PASSWORD` n'est lu par PostgreSQL qu'à l'initialisation d'un volume vide : le changer sur un environnement déjà déployé impose de vider l'environnement (section 7).

Lire le mot de passe Grafana, pour se connecter :

```bash
sops --decrypt --extract '["stringData"]["admin-password"]' k8s/overlays/capacite/grafana-admin.sops.yaml
```

## Limites

- **Comparable n'est pas identique.** Même offre de VPS ne garantit pas les mêmes performances (voisinage, génération de processeur). La base ne contient que 25 produits, et aucun trafic réel ne s'ajoute à celui du test.
- **Parcours unique.** Accueil, recherche, fiche : ni pagination, ni catégories, ni fichiers statiques. Les images viennent d'Unsplash et ne chargent pas le serveur.
- **Le client ne voit pas tout.** Le p95 est celui de k6 ; il inclut le réseau entre le générateur et le VPS. Le relever aussi dans Grafana (p95 Django).
- **Redémarrages** relevés toutes les 15 s : un pod qui redémarre et revient entre deux relevés est quand même détecté (compteur de redémarrages), mais jusqu'à 15 s après.
- **Limite haute de l'outil** : 50 parcours/s (150 requêtes/s). Si le site les tient, la limite est au-delà et ce script ne la trouvera pas sans relever son plafond, ce qui demande une nouvelle revue.
