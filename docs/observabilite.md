# Observabilité — Prometheus et Grafana (production)

Issue #44. Collecte et visualisation des métriques que Django expose sur `/metrics` depuis #45 : les quatre signaux d'or (latence, trafic, erreurs, saturation).

Les commandes suivent les conventions de [deploiement-production.md](deploiement-production.md) : **SERVEUR** désigne un shell sur le VPS, dans `~/e-commerce` ; **PORTABLE** le poste qui détient la clé age et l'alias SSH `$HOTE_SSH`.

## Périmètre

| Inclus | Exclu, volontairement |
| --- | --- |
| Prometheus, une seule tâche de collecte : les pods Django | kube-prometheus-stack, trop lourd pour le VPS |
| Grafana, source de données et tableau de bord provisionnés | Alertmanager — issue #48 |
| RBAC en lecture seule sur les pods de `dilane-shop` | Surveillance de Kubernetes, des nœuds, de PostgreSQL, de Prometheus lui-même |
| | Tout accès public : ni Ingress, ni NodePort |

La pile ne concerne que la production. Elle vit dans [k8s/overlays/production/observabilite/](../k8s/overlays/production/observabilite/), incluse par la surcouche de production, et **pas dans `k8s/base`** : le cluster kind du poste n'en a pas l'usage. La sortie de `kubectl kustomize k8s/overlays/local` est identique avant et après cet ajout.

## Budget mémoire

VPS de 4 Go, environ 2,2 Go libres, **sans swap** : un dépassement ne ralentit pas, il déclenche le tueur de processus du noyau. Chaque conteneur a donc une limite stricte, et les deux Deployments sont en `strategy: Recreate`, si bien qu'une mise à jour ne fait jamais coexister l'ancien et le nouveau pod.

| Composant | Mesuré | Requête | Limite | Plafond du ramasse-miettes Go |
| --- | --- | --- | --- | --- |
| Prometheus v3.13.3 | 21 à 35 Mi | 64 Mi | 128 Mi | automatique, 90 % de la limite |
| Grafana 12.4.11 | 102 à 104 Mi | 128 Mi | 192 Mi | `GOMEMLIMIT=150MiB` |
| Conteneur d'initialisation (chown) | — | 16 Mi | 32 Mi | — |
| **Total** | **~140 Mi** | **192 Mi** | **320 Mi** | |

Le conteneur d'initialisation de Prometheus s'exécute et se termine avant le démarrage de Prometheus : il ne s'ajoute pas au total.

Mesures faites avec les images épinglées et la configuration de ce dépôt, sous `docker run --read-only --memory`, face à Django 6.1.1 sous gunicorn (3 workers, configuration de production) recevant du trafic, tableau de bord interrogé. Sur le VPS, surveiller la consommation réelle après quelques jours :

```bash
kubectl top pods -n observabilite    # SERVEUR ; metrics-server est livré avec k3s
```

**Priorité.** Les deux pods portent la `PriorityClass` `observabilite-faible-priorite` (valeur -100, contre 0 pour l'application). En cas de manque de mémoire sur le nœud, ou si un déploiement de Django ne trouve plus de place pour son pod supplémentaire, ce sont eux qui cèdent, jamais Django ni PostgreSQL. `preemptionPolicy: Never` les empêche à l'inverse d'évincer un pod de l'application pour démarrer.

## Comment Prometheus atteint `/metrics`

### Découverte par pod, pas par Service

Le Service `django` répartit les requêtes entre les deux replicas : une collecte passant par lui tomberait sur l'un ou l'autre au hasard, et chaque replica n'expose que ses propres compteurs. Prometheus découvre donc les **pods** (`kubernetes_sd_configs`, `role: pod`) :

1. restreint à l'espace de noms `dilane-shop` — un `Role` suffit, pas de `ClusterRole` ;
2. filtré par l'API elle-même sur `app.kubernetes.io/name=django` : ni PostgreSQL, ni le Job de migration, ni les sauvegardes ;
3. gardé seulement si le pod porte `prometheus.io/scrape: "true"`, et s'il est `Running` ;
4. réduit au seul port annoncé par `prometheus.io/port` (règle `keepequal`), ce qui écarte la cible sans port que la découverte crée pour le conteneur d'initialisation `preparer-medias`.

Chaque replica devient une cible distincte, étiquetée par `pod`. Ces règles ont été vérifiées sur un vrai Prometheus v3.13.3, en remplaçant la découverte Kubernetes par des cibles portant les mêmes méta-étiquettes : sur quatre candidates (le conteneur Django, le conteneur d'initialisation, un pod `Pending`, un pod sans annotation), seule la première est retenue, et elle est `up`.

Les annotations sont ajoutées au Deployment par [patch-django-metriques.yaml](../k8s/overlays/production/patch-django-metriques.yaml), dans la surcouche de production : la base partagée avec kind n'est pas modifiée.

### Pourquoi la collecte obtient 200, et non 404

La vue `metrics` ([shop/views.py](../shop/views.py)) répond 404 dès que la requête porte `X-Forwarded-For`, `X-Real-IP` ou `Forwarded`. Ces en-têtes sont posés par ingress-nginx sur **toute** requête qu'il relaie ; un client ne peut pas les effacer. Depuis Internet, `/metrics` passe forcément par l'Ingress, donc répond 404.

La collecte de Prometheus, elle :

- **ne traverse pas l'Ingress.** Elle va du pod Prometheus à l'IP du pod Django, sur le port 8000, par le réseau interne du cluster. Aucun intermédiaire n'ajoute d'en-tête ;
- **n'ajoute aucun en-tête de proxy.** Prometheus envoie `Accept`, `Accept-Encoding`, `User-Agent` et `X-Prometheus-Scrape-Timeout-Seconds`, rien d'autre.

Aucun des trois en-têtes surveillés n'est présent : la vue rend les métriques.

### Le piège : `ALLOWED_HOSTS`, et la parade

Interroger un pod sur son IP a une autre conséquence : la requête porte `Host: 10.42.0.x:8000`. Or `DJANGO_ALLOWED_HOSTS` ne contient que `localhost,127.0.0.1,dilane-shop.store`. Django rejette alors la requête **en 400 (`DisallowedHost`) avant même d'atteindre la vue**, et la cible serait marquée `down`.

Vérifié sous gunicorn avec la configuration de production :

| Requête vers le pod | Code |
| --- | --- |
| `Host: <IP du pod>`, sans en-tête de proxy, IP **absente** de `ALLOWED_HOSTS` | **400** `Invalid HTTP_HOST header` |
| `Host: localhost`, sans en-tête de proxy | 200 |
| `Host: localhost`, avec `X-Forwarded-For` | 404 |
| `Host: <IP du pod>`, IP **ajoutée** à `ALLOWED_HOSTS` (collecte par Prometheus) | 200, cible `up` |

Prometheus ne permet pas de forcer l'en-tête `Host` (`setting header "Host" is not allowed` à la validation de la configuration), et l'IP d'un pod change à chaque redémarrage. La parade, dans [patch-django-metriques.yaml](../k8s/overlays/production/patch-django-metriques.yaml) :

```yaml
- name: POD_IP
  valueFrom:
    fieldRef:
      fieldPath: status.podIP
- name: DJANGO_ALLOWED_HOSTS
  value: "$(DJANGO_ALLOWED_HOSTS),$(POD_IP)"
```

Le kubelet charge d'abord les variables d'`envFrom`, puis développe chaque entrée `env` avec elles avant de la remplacer (vérifié dans son code, `makeEnvironmentVariables`, `pkg/kubelet/kubelet_pods.go`) : `$(DJANGO_ALLOWED_HOSTS)` vaut la liste du ConfigMap, à laquelle s'ajoute l'IP du pod. Ainsi chaque pod accepte sa propre IP en plus des domaines, dont la liste reste définie à un seul endroit ([patch-configmap.yaml](../k8s/overlays/production/patch-configmap.yaml)). L'ordre compte : `POD_IP` doit précéder `DJANGO_ALLOWED_HOSTS`.

Accepter l'IP du pod comme nom d'hôte n'ouvre rien : cette IP n'est joignable que depuis le cluster, et une requête arrivée par l'Ingress porte de toute façon `X-Forwarded-For`, donc reçoit 404 sur `/metrics`.

`SECURE_SSL_REDIRECT` est désactivé en production (variable absente du ConfigMap et du Secret) : la collecte en HTTP n'est pas redirigée vers HTTPS. S'il était activé un jour, la collecte recevrait 301 et il faudrait exempter `/metrics` (`SECURE_REDIRECT_EXEMPT`).

### Mise en garde : NetworkPolicy

Aucune NetworkPolicy n'existe aujourd'hui dans `dilane-shop`, donc rien ne bloque le trafic de `observabilite` vers les pods Django. Si une politique « tout refuser » est ajoutée un jour, il faudra autoriser explicitement l'espace de noms `observabilite` vers le port 8000 des pods `app.kubernetes.io/name=django`.

## Le tableau de bord

Provisionné depuis [grafana/signaux-dor.json](../k8s/overlays/production/observabilite/grafana/signaux-dor.json), dans le dossier « Dilane Shop » : **Dilane Shop — signaux d'or**.

| Signal | Panneau | Requête (simplifiée) |
| --- | --- | --- |
| Latence | p50 et p95, global et par pod | `histogram_quantile(0.95, sum by (le) (rate(django_http_requests_latency_seconds_bucket[…])))` |
| Trafic | requêtes/s, total et par pod | `sum by (pod) (rate(django_http_requests_total[…]))` |
| Erreurs | part des 5xx (et des 4xx, à titre indicatif) | `sum(rate(…{status=~"5.."}[…])) / sum(rate(…[…]))` |
| Saturation | requêtes en cours par pod | `clamp_min(sum by (pod) (django_http_requests_in_progress) - 1, 0)` |

S'y ajoutent une ligne de synthèse (requêtes/s, taux de 5xx, p95, nombre de pods collectés) et un détail par route, par code de statut et des exceptions.

Deux corrections, constatées en mesurant :

- **Le trafic exclut `view="metrics"` et `view="healthz"`.** L'intergiciel compte toutes les requêtes, y compris les collectes de Prometheus (toutes les 30 s) et les sondes de Kubernetes (toutes les 10 et 20 s). Sans ce filtre, une boutique sans visiteur afficherait du trafic, et une latence tirée vers le bas par ces requêtes très rapides.
- **La saturation retranche 1.** La collecte est elle-même une requête en cours au moment où la jauge est lue : sans visiteur, `django_http_requests_in_progress` vaut 1, pas 0.

Chacune des requêtes du tableau de bord a été exécutée à travers l'API de Grafana, face au Prometheus d'essai : toutes renvoient des données. Le taux d'erreur vaut 0 en l'absence d'erreur (et non « No data ») ; il n'est vide qu'en l'absence de tout trafic.

Le tableau de bord n'est pas modifiable dans l'interface (`allowUiUpdates: false`) : la source de vérité est le fichier du dépôt. Pour le faire évoluer, l'éditer dans Grafana, l'exporter en JSON, remplacer le fichier, réappliquer la surcouche.

## Secret Grafana

Le compte administrateur est lu dans le Secret `grafana-admin` (clés `admin-user` et `admin-password`), monté en fichiers et lu par la syntaxe `GF_SECURITY_ADMIN_*__FILE` : la valeur n'apparaît ni dans le manifeste, ni dans les variables d'environnement du pod.

Emplacement : **`k8s/overlays/production/observabilite/grafana-admin.sops.yaml`**. Le chemin est couvert par la règle `k8s/.*\.sops\.yaml$` de [.sops.yaml](../.sops.yaml) : sops le chiffre avec la même clé age que les autres secrets. Comme eux, il n'est listé dans aucune kustomization.

**PORTABLE** — depuis la racine du dépôt

```bash
# 1. Générer un mot de passe et le noter dans le gestionnaire de mots de passe.
openssl rand -base64 24

# 2. Créer le fichier chiffré. sops ouvre l'éditeur sur un nouveau fichier et
#    le chiffre à l'enregistrement : aucune copie en clair ne reste sur le disque.
sops k8s/overlays/production/observabilite/grafana-admin.sops.yaml
```

Remplacer le contenu d'exemple proposé par sops par :

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: grafana-admin
  namespace: observabilite
type: Opaque
stringData:
  admin-user: admin
  admin-password: <mot de passe généré à l'étape 1>
```

Vérifier avant de commiter que `git diff` montre les noms de clés en clair et les valeurs sous forme `ENC[…]`.

La base interne de Grafana vit dans un `emptyDir` et repart de zéro à chaque démarrage : un mot de passe changé dans le Secret s'applique donc au prochain redémarrage du pod, sans étape supplémentaire. Contrepartie : un changement de mot de passe fait dans l'interface est perdu au redémarrage.

## Déployer

Prérequis : l'application déjà déployée (espace de noms `dilane-shop` existant), et le Secret ci-dessus créé et commité.

**Mémoire pendant le déploiement.** L'ajout des annotations et de `POD_IP` modifie le modèle de pod de Django : l'application de la surcouche déclenche une mise à jour progressive (`maxSurge: 1`), donc un troisième pod Django pendant quelques dizaines de secondes (256 Mi réservés, 512 Mi au plus). Lancer le déploiement hors des heures chargées, et vérifier la marge avant : `free -m` sur le serveur.

**SERVEUR** — mettre à jour le dépôt, créer l'espace de noms (il doit exister avant le Secret)

```bash
cd ~/e-commerce
git pull
kubectl apply -f k8s/overlays/production/observabilite/00-namespace.yaml
```

**PORTABLE** — injecter le Secret, déchiffré localement et transmis par SSH

```bash
sops --decrypt k8s/overlays/production/observabilite/grafana-admin.sops.yaml \
  | ssh $HOTE_SSH "kubectl apply -f -"
```

**SERVEUR** — appliquer la surcouche et suivre les déploiements

```bash
cd ~/e-commerce
kubectl kustomize k8s/overlays/production > /dev/null && echo "construction OK"
kubectl diff -k k8s/overlays/production        # facultatif : ce qui va changer

kubectl apply -k k8s/overlays/production

kubectl rollout status -n dilane-shop   deploy/django     --timeout=300s
kubectl rollout status -n observabilite deploy/prometheus --timeout=300s
kubectl rollout status -n observabilite deploy/grafana    --timeout=300s
kubectl get pods,pvc -n observabilite
```

La pile s'applique aussi seule, sans toucher à l'application : `kubectl apply -k k8s/overlays/production/observabilite`. Dans ce cas, les annotations et `POD_IP` ne sont pas posés sur Django, et Prometheus ne trouve aucune cible.

## Vérifier

**SERVEUR** — Django accepte bien l'IP de son pod

```bash
kubectl exec -n dilane-shop deploy/django -- printenv DJANGO_ALLOWED_HOSTS POD_IP
```

Attendu : la liste des domaines suivie de l'IP du pod, puis la même IP seule.

**SERVEUR** — Prometheus voit les deux cibles, `up`

```bash
kubectl exec -n observabilite deploy/prometheus -- \
  promtool query instant http://localhost:9090 'up{job="django"}'
```

Attendu : deux lignes, une par pod Django, chacune `=> 1`.

```
up{instance="10.42.0.21:8000", job="django", namespace="dilane-shop", pod="django-…-abcde"} => 1 @[…]
up{instance="10.42.0.22:8000", job="django", namespace="dilane-shop", pod="django-…-fghij"} => 1 @[…]
```

Une cible à `0`, ou absente : consulter l'erreur de collecte, dans la page *Status → Targets* de Prometheus (voir l'accès ci-dessous) ou directement :

```bash
kubectl exec -n observabilite deploy/prometheus -- \
  wget -qO- 'http://localhost:9090/api/v1/targets?state=active' | grep -o '"lastError":"[^"]*"'
```

`server returned HTTP status 400 Bad Request` signifie que l'IP du pod manque dans `ALLOWED_HOSTS` ; `404 Not Found`, qu'un en-tête de proxy a été ajouté en chemin.

**SERVEUR** — `/metrics` reste fermé depuis Internet

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://dilane-shop.store/metrics
```

Attendu : `404`.

**SERVEUR** — consommation réelle

```bash
kubectl top pods -n observabilite
```

## Accéder à Grafana (et à Prometheus)

Aucun des deux n'est exposé : ni Ingress, ni NodePort, et le pare-feu du VPS reste inchangé. L'accès passe par un double tunnel : `kubectl port-forward` sur le serveur, relayé par SSH jusqu'au portable. Les deux extrémités n'écoutent que sur l'interface locale (127.0.0.1).

**PORTABLE**

```bash
ssh -L 3000:127.0.0.1:3000 $HOTE_SSH \
  "kubectl port-forward -n observabilite svc/grafana 3000:3000"
```

Puis ouvrir <http://localhost:3000> et se connecter avec le compte du Secret `grafana-admin`. Le tableau de bord est dans *Dashboards → Dilane Shop*. `Ctrl+C` ferme les deux tunnels.

Pour l'interface de Prometheus (page *Status → Targets* notamment), même principe sur le port 9090 :

```bash
ssh -L 9090:127.0.0.1:9090 $HOTE_SSH \
  "kubectl port-forward -n observabilite svc/prometheus 9090:9090"
```

puis <http://localhost:9090/targets>.

## Retirer la pile

```bash
kubectl delete namespace observabilite                       # Prometheus, Grafana, données
kubectl delete priorityclass observabilite-faible-priorite
kubectl delete role,rolebinding -n dilane-shop prometheus-decouverte
```

Puis retirer `observabilite` et `patch-django-metriques.yaml` de [k8s/overlays/production/kustomization.yaml](../k8s/overlays/production/kustomization.yaml) et réappliquer la surcouche. Le volume local-path est supprimé avec sa revendication (politique `Delete`).

## Versions épinglées

| Image | Étiquette | Empreinte |
| --- | --- | --- |
| `prom/prometheus` | `v3.13.3` | `sha256:6976aa8a60fec930796ce5772b8d12da7a318a5daa8d40d69c5c7819a05eeed7` |
| `grafana/grafana` | `12.4.11` | `sha256:3ea272e5cab64a4a62240c682e2c62433b25614d956d44c299a10cb6994f6f2e` |

Étiquette et empreinte ensemble : l'étiquette dit la version, l'empreinte garantit l'image exacte, même si l'étiquette était republiée. Pour monter de version, remplacer les deux, dans `prometheus.yaml` (deux occurrences : conteneur principal et d'initialisation) ou `grafana.yaml`.
