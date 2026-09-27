# Observabilité — Prometheus et Grafana (production)

Issue #44. Collecte et visualisation des métriques que Django expose sur `/metrics` depuis #45 : les quatre signaux d'or (latence, trafic, erreurs, saturation). Issue #48 : alertes par courriel, évaluées par Grafana lui-même (voir [Alertes](#alertes)). Un test k6 du catalogue permet d'observer ces signaux sous charge (voir [Test de charge k6](#test-de-charge-k6)).

Les commandes suivent les conventions de [deploiement-production.md](deploiement-production.md) : **SERVEUR** désigne un shell sur le VPS, dans `~/e-commerce` ; **PORTABLE** le poste qui détient la clé age et l'alias SSH `$HOTE_SSH`.

## Périmètre

| Inclus | Exclu, volontairement |
| --- | --- |
| Prometheus, une seule tâche de collecte : les pods Django | kube-prometheus-stack, trop lourd pour le VPS |
| Grafana, source de données et tableau de bord provisionnés | Alertmanager séparé : Grafana embarque le sien (#48) |
| Trois alertes par courriel, provisionnées par fichier (#48) | |
| RBAC en lecture seule sur les pods de `dilane-shop` | Surveillance de Kubernetes, des nœuds, de PostgreSQL, de Prometheus lui-même |
| | Tout accès public : ni Ingress, ni NodePort |

La pile ne concerne que la production. Elle vit dans [k8s/overlays/production/observabilite/](../k8s/overlays/production/observabilite/), incluse par la surcouche de production, et **pas dans `k8s/base`** : le cluster kind du poste n'en a pas l'usage. La sortie de `kubectl kustomize k8s/overlays/local` est identique avant et après cet ajout.

## Budget mémoire

VPS de 4 Go, environ 2,2 Go libres, **sans swap** : un dépassement ne ralentit pas, il déclenche le tueur de processus du noyau. Chaque conteneur a donc une limite stricte, et les deux Deployments sont en `strategy: Recreate`, si bien qu'une mise à jour ne fait jamais coexister l'ancien et le nouveau pod.

| Composant | Mesuré | Requête | Limite | Plafond du ramasse-miettes Go |
| --- | --- | --- | --- | --- |
| Prometheus v3.13.3 | 21 à 35 Mi | 64 Mi | 128 Mi | automatique, 90 % de la limite |
| Grafana 12.4.11, alertes comprises | 102 à 106 Mi | 128 Mi | 192 Mi | `GOMEMLIMIT=150MiB` |
| Conteneur d'initialisation (chown) | — | 16 Mi | 32 Mi | — |
| **Total** | **~145 Mi** | **192 Mi** | **320 Mi** | |

Le conteneur d'initialisation de Prometheus s'exécute et se termine avant le démarrage de Prometheus : il ne s'ajoute pas au total.

Activer les alertes (#48) a coûté environ 3 Mi à Grafana : 103 Mi sans, 106 Mi avec les trois règles évaluées chaque minute et un envoi de courriel. Aucun pod supplémentaire.

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

## Alertes

Issue #48. Grafana évalue lui-même trois règles contre Prometheus, chaque minute, et envoie un courriel par le relais SMTP de Brevo déjà utilisé par l'application. **Aucun Alertmanager séparé** : Grafana embarque le sien, qui groupe, répète et résout les notifications. Coût mesuré : environ 3 Mi de mémoire, aucun pod en plus.

### Provisionnées comme code

Grafana n'a pas de volume persistant : une règle ou un point de contact créé dans l'interface disparaîtrait au redémarrage. Tout est donc décrit par des fichiers, montés dans `/etc/grafana/provisioning/alerting` par le ConfigMap `grafana-alertes` :

| Fichier | Contenu |
| --- | --- |
| [grafana/alertes/regles.yaml](../k8s/overlays/production/observabilite/grafana/alertes/regles.yaml) | les trois règles, dans le dossier « Dilane Shop » |
| [grafana/alertes/points-de-contact.yaml](../k8s/overlays/production/observabilite/grafana/alertes/points-de-contact.yaml) | le point de contact `courriel-dilane-shop` → `wankamdypuedilane@gmail.com` |
| [grafana/alertes/politique.yaml](../k8s/overlays/production/observabilite/grafana/alertes/politique.yaml) | la politique de notification : tout vers ce courriel, groupé par règle |

Ces objets sont marqués « provisionnés » dans l'interface et n'y sont pas modifiables. Pour changer un seuil : éditer le fichier, réappliquer la surcouche ; l'empreinte du ConfigMap change et le pod Grafana redémarre avec la nouvelle version.

Si un fichier est invalide, **Grafana refuse de démarrer** (`Failed to provision alerting` dans ses journaux) plutôt que de tourner sans alertes : le déploiement échoue visiblement, `kubectl rollout status` ne se termine pas.

### Les trois règles

Les seuils sont repérés par le mot **`SEUIL`** dans [regles.yaml](../k8s/overlays/production/observabilite/grafana/alertes/regles.yaml), chacun commenté.

| Règle | Requête | Seuil | Durée (`for`) | Gravité |
| --- | --- | --- | --- | --- |
| Site injoignable | `sum(up{job="django"}) or vector(0)` | `< 1` pod | 2 min | critique |
| Taux d'erreur 5xx élevé | part des réponses 5xx sur 5 min | `> 0,05` (5 %) | 2 min | critique |
| Latence p95 élevée | `histogram_quantile(0.95, …[5m])` | `> 1` s | 2 min | avertissement |

Toutes excluent `/metrics` et `/healthz/`, comme le tableau de bord.

**Site injoignable.** `up` vaut 0 quand Prometheus n'obtient pas de réponse d'un pod ; mais si les pods n'existent plus du tout (Deployment à zéro, pods supprimés), la série `up` disparaît au lieu de valoir 0. `or vector(0)` couvre ce cas. Seuil à `1` : l'alerte part quand **aucun** pod ne répond ; le mettre à `2` pour être prévenu dès qu'un des deux replicas tombe.

**Taux d'erreur 5xx : gardes contre le faible trafic.** La requête ne rend un résultat que si **au moins 20 requêtes** ont été servies en 5 minutes (`and on() sum(increase(…[5m])) >= 20`). Sans cette garde, une erreur sur deux requêtes à 4 h du matin ferait 50 %, et l'absence totale de trafic donnerait une division par zéro. Sous ce volume, la règle reste « Normal » (`noDataState: OK`). À l'inverse, `or vector(0)` sur le numérateur fait valoir 0 % quand aucune erreur n'a été vue, plutôt que « pas de donnée ».

**Latence p95.** Même garde de volume : un p95 calculé sur trois requêtes n'a pas de sens. L'histogramme a des bornes à 0,5 s, 1 s et 2,5 s ; un seuil posé entre deux bornes est estimé par interpolation.

**Ce que ces règles ne voient pas.** Seules les réponses produites par Django sont comptées. Les 502 et 503 qu'ingress-nginx renvoie lui-même quand aucun pod ne répond n'apparaissent pas dans `django_http_requests_total` ; ce cas est couvert par « Site injoignable ». Une panne de Prometheus lui-même produit une alerte distincte, `DatasourceError` (`execErrState: Error`), plutôt qu'une fausse alerte « Site injoignable ».

**Délais.** Entre le début d'une panne et le courriel, compter environ 3 à 4 minutes : collecte toutes les 30 s, évaluation chaque minute, 2 minutes de `for`, 30 s de `group_wait`. Le courriel de résolution suit le `group_interval` : jusqu'à 5 minutes après le retour à la normale. Tant qu'une alerte reste active, un rappel part toutes les 4 heures (`repeat_interval`).

Ces comportements ont été vérifiés :

- **Expressions PromQL**, par `promtool test rules` sur des séries synthétiques : alerte 5xx et p95 sous fort trafic avec 10 % d'erreurs et des requêtes lentes ; aucune alerte avec 2 erreurs sur 3 requêtes, ni sans trafic (division par zéro), ni sans aucune série 5xx ; « Site injoignable » quand `up` vaut 0 comme quand ses séries disparaissent.
- **De bout en bout**, avec Grafana 12.4.11, Prometheus v3.13.3 et Django sous gunicorn, un faux serveur SMTP (Mailpit) à la place de Brevo : les trois règles se chargent et s'évaluent sans erreur ; Django arrêté, « Site injoignable » passe à *Pending* puis *Alerting*, et le courriel `[FIRING:1] Site injoignable Dilane Shop (critique)` arrive environ 3 min 20 après l'arrêt, description rendue (« Pods Django répondant à Prometheus : 0 »), avec les liens vers l'alerte et le tableau de bord ; Django relancé, le courriel `[RESOLVED]` suit.
- **SMTP**, face à un serveur exigeant STARTTLS et une authentification : l'envoi réussit avec la politique `MandatoryStartTLS` de production et les identifiants lus dans les fichiers du Secret ; une mauvaise clé est refusée (`535 Authentication credentials invalid`) et l'erreur remonte au test du point de contact.

### Secret SMTP des alertes

Grafana envoie par Brevo avec les mêmes identifiants que l'application. Ils sont dans `dilane-shop-secrets`, **dans l'espace de noms `dilane-shop`** ; un Secret n'est lisible que dans son propre espace de noms, et Grafana tourne dans `observabilite`.

Solution retenue : **recopier les trois valeurs utiles dans un Secret propre à l'observabilité**, `grafana-smtp`, chiffré par SOPS comme les autres. Écartées :

- donner à Grafana un accès à `dilane-shop-secrets` (RBAC entre espaces de noms, ou synchronisation de Secrets) : Grafana obtiendrait aussi les clés Stripe, le mot de passe de la base et la clé secrète de Django ;
- déplacer Grafana dans `dilane-shop` : même problème, et l'isolement de la pile d'observabilité serait perdu.

Contrepartie : une rotation de la clé Brevo doit être reportée dans les deux fichiers.

Emplacement : **`k8s/overlays/production/observabilite/grafana-smtp.sops.yaml`**, couvert par la règle `k8s/.*\.sops\.yaml$` de [.sops.yaml](../.sops.yaml). Trois clés :

| Clé | Recopiée depuis | Variable Grafana |
| --- | --- | --- |
| `smtp-user` | `BREVO_SMTP_LOGIN` | `GF_SMTP_USER__FILE` |
| `smtp-password` | `BREVO_SMTP_KEY` | `GF_SMTP_PASSWORD__FILE` |
| `from-address` | `EMAIL_FROM` | `GF_SMTP_FROM_ADDRESS__FILE` |

L'expéditeur est celui de l'application : Brevo n'accepte que des expéditeurs validés dans le compte, et celui-ci l'est déjà. Le nom affiché est « Dilane Shop — alertes » (`GF_SMTP_FROM_NAME`, non secret). Serveur `smtp-relay.brevo.com:587`, STARTTLS obligatoire (`MandatoryStartTLS`) : Grafana refuse d'envoyer plutôt que de transmettre les identifiants en clair.

**PORTABLE** — depuis la racine du dépôt. Les valeurs sont déchiffrées vers un tube et rechiffrées aussitôt : aucune copie en clair n'est écrite sur le disque, et aucune valeur n'apparaît à l'écran.

```bash
SRC=k8s/overlays/production/secrets.sops.yaml
DEST=k8s/overlays/production/observabilite/grafana-smtp.sops.yaml
valeur() {  # extrait une clé du Secret applicatif, protégée pour YAML
  sops --decrypt --extract "[\"stringData\"][\"$1\"]" "$SRC" | sed "s/'/''/g"
}
{
  printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: grafana-smtp\n  namespace: observabilite\ntype: Opaque\nstringData:\n'
  printf "  smtp-user: '%s'\n"     "$(valeur BREVO_SMTP_LOGIN)"
  printf "  smtp-password: '%s'\n" "$(valeur BREVO_SMTP_KEY)"
  printf "  from-address: '%s'\n"  "$(valeur EMAIL_FROM)"
} | sops --encrypt --filename-override "$DEST" --input-type yaml --output-type yaml /dev/stdin > "$DEST"
```

Vérifier ensuite que `git diff` montre les trois noms de clés en clair et les valeurs sous forme `ENC[…]`, et qu'aucune autre clé n'a été recopiée. Cette commande a été essayée avec sops 3.13.3 et une clé age jetable, sur un faux Secret applicatif : seules les trois clés sont recopiées, et une valeur contenant une apostrophe, un deux-points et un dièse est restituée à l'identique.

### Tester une alerte sans attendre une panne

Trois niveaux, du plus simple au plus complet. Tous passent par le tunnel SSH décrit dans [Accéder à Grafana](#accéder-à-grafana-et-à-prometheus).

**1. Le point de contact : le SMTP fonctionne-t-il ?** Dans Grafana : *Alerting → Contact points → courriel-dilane-shop → Test*, puis *Send test notification*. Un courriel `[FIRING:1] TestAlert` doit arriver dans la boîte `wankamdypuedilane@gmail.com` en moins d'une minute. Une erreur d'identifiants Brevo ou de STARTTLS s'affiche directement dans l'interface. Sans navigateur, depuis le serveur :

```bash
# SERVEUR
kubectl exec -n observabilite deploy/grafana -- sh -c '
  AUTH=$(printf "%s:%s" "$(cat /etc/grafana-admin/admin-user)" "$(cat /etc/grafana-admin/admin-password)" | base64 -w0)
  wget -qO- --header "Authorization: Basic $AUTH" --header "Content-Type: application/json" \
    --post-data "{\"receivers\":[{\"name\":\"courriel-dilane-shop\",\"grafana_managed_receiver_configs\":[{\"uid\":\"courriel-dilane-shop\",\"name\":\"courriel-dilane-shop\",\"type\":\"email\",\"settings\":{\"addresses\":\"wankamdypuedilane@gmail.com\"}}]}]}" \
    http://localhost:3000/api/alertmanager/grafana/config/api/v1/receivers/test' \
  | grep -o '"status":"[a-z]*"\|"error":"[^"]*"'
```

Attendu : `"status":"ok"`, et le courriel reçu. Vérifier aussi qu'il n'est pas classé en indésirables.

**2. La chaîne complète : règle → politique → courriel.** Le test du point de contact ne passe ni par une règle ni par la politique. Pour les éprouver sans panne, créer une règle temporaire qui se déclenche d'elle-même : *Alerting → Alert rules → New alert rule*, requête `sum(rate(django_http_requests_total{job="django"}[5m]))`, seuil *IS ABOVE* `0` (toujours vrai : les collectes de Prometheus suffisent), dossier « Dilane Shop », pending period `1m`. Le courriel `[FIRING:1] …` arrive en 2 à 3 minutes (vérifié dans l'environnement d'essai : environ 2 minutes, dossier provisionné compris) ; supprimer ensuite la règle, le courriel `[RESOLVED]` suit dans les 5 minutes. Une règle créée dans l'interface disparaît de toute façon au prochain redémarrage de Grafana, ce qui garantit qu'aucun test ne reste en place.

**3. Une vraie règle, par un test de charge.** Le script k6 du catalogue produit un trafic réel mesurable dans les quatre signaux d'or, et peut faire passer la règle « Latence p95 élevée » en *Pending* puis *Alerting* **si la latence mesurée dans Django dépasse vraiment 1 seconde** sous cette charge. Ce n'est pas garanti, ni même probable avec 6 à 8 utilisateurs virtuels : voir [Test de charge k6](#test-de-charge-k6). Pour éprouver la chaîne d'envoi, le test 2 (règle temporaire) reste la méthode fiable ; il est distinct du test k6. La règle 5xx ne se provoque pas proprement en production (aucune route n'échoue volontairement) : elle a été vérifiée par les tests `promtool` décrits plus haut.

La règle « Site injoignable » peut être éprouvée pour de bon lors d'une maintenance planifiée, par `kubectl scale -n dilane-shop deploy/django --replicas=0` puis `--replicas=2` : c'est une vraie coupure du site, à réserver à ce cas.

### Limites connues

- **État en mémoire.** L'Alertmanager intégré garde ses silences et son journal d'envoi dans la base SQLite de Grafana, donc dans l'`emptyDir` : un redémarrage de Grafana efface les silences, et une alerte encore active peut être notifiée une seconde fois.
- **Quota Brevo.** Les courriels d'alerte consomment le même quota d'envoi que les courriels transactionnels de la boutique. Le groupement par règle et le rappel toutes les 4 heures limitent le volume.
- **Un seul canal.** Si Brevo ou la boîte de réception est indisponible, l'alerte n'arrive pas, et rien ne le signale. Un second point de contact (webhook, messagerie) serait le remède.

## Test de charge k6

Le script [scripts/k6/catalogue.js](../scripts/k6/catalogue.js) produit un trafic de lecture sur le catalogue, pour observer les quatre signaux d'or dans Grafana et, si la latence réelle le permet, voir la règle « Latence p95 élevée » réagir.

### Ce que fait le script

Chaque itération suit une visite de catalogue : trois **GET**, avec une pause de 0,5 s après chacun.

1. `/` : la page d'accueil, liste paginée des produits ;
2. `/api/produits/?item-name=Casque` : la recherche de produits, en JSON ;
3. `/<id>` : la fiche du **premier produit renvoyé par la recherche** (route `detail` de `shop/urls.py`).

Aucun checkout, paiement, création de compte ni écriture.

**Terme de recherche.** « Casque » par défaut, modifiable par `-e TERME_RECHERCHE=…`. Le terme est encodé dans l'URL (`encodeURIComponent`) : espaces, accents, `&` ou `#` ne peuvent ni casser la requête ni ajouter de paramètre. Il doit compter de 1 à 64 caractères, sinon le test refuse de démarrer. Surtout, il doit **trouver au moins un produit** dans le catalogue visé : dans le catalogue de démonstration (`fixtures/demo-catalogue.json`), « Casque » trouve « Casque Audio Premium ». Avant de viser la production, vérifier que le terme y trouve bien un produit, ou en choisir un autre.

| Mode | Profil | Volume |
| --- | --- | --- |
| `smoke` (défaut) | 1 utilisateur virtuel, 5 itérations | 15 requêtes si le parcours réussit (10 si la recherche ne trouve rien : la fiche est alors sautée) |
| `charge` | montée 1 min, palier 8 min, descente 1 min | 6 utilisateurs virtuels par défaut, 8 au plus (`VUS`) |

Chaque utilisateur virtuel attend la réponse avant d'envoyer la requête suivante. Le débit est donc borné : environ 2 requêtes par seconde et par utilisateur virtuel tant que les réponses sont rapides (3 requêtes par itération, 1,5 s de pause), soit environ 12 req/s à 6 VUS et 16 req/s à 8 VUS. Il baisse si le site ralentit.

### Garde-fous

- **Cible obligatoire et restreinte.** `CIBLE` n'accepte que `https://dilane-shop.store`, ou une adresse locale explicite : `http(s)://localhost`, `127.0.0.1` ou `[::1]` (port facultatif), ou `https://dilane-shop.local` (cluster kind, seule cible pour laquelle le certificat n'est pas vérifié). L'origine est comparée en entier : `http://dilane-shop.store`, `https://dilane-shop.store.exemple.com`, `https://dilane-shop.store@exemple.com`, une IP privée ou un chemin sont refusés.
- **Charge sur la production : consentement explicite.** `MODE=charge` avec la cible de production exige `-e AUTORISER_CHARGE_PROD=oui`, exactement.
- **Plafond de 8 utilisateurs virtuels.** `VUS` hors de 1 à 8 : refus. Les options `--vus`, `--duration` et `--iterations`, qui remplaceraient les scénarios du script, sont détectées avant le premier utilisateur virtuel et interrompent le test.
- **Arrêt automatique**, 10 s après le début au plus tôt, dès que l'un de ces seuils est franchi :
  - 2 % de requêtes en échec (erreur réseau ou statut ≥ 400) ;
  - p95 côté client de 5 secondes ;
  - moins de 98 % de réponses HTTP 200 ;
  - **une seule** recherche répondue en 200 mais inexploitable : liste vide, JSON illisible, ou premier produit sans identifiant entier positif (métrique `recherches_inexploitables`) ;
  - **une seule** fiche répondue en 200 mais pas en HTML (métrique `fiches_non_html`).

Les deux derniers seuils sont stricts parce qu'ils ne décrivent pas une défaillance passagère sous charge, mais un terme ou un catalogue inadapté, ou une route qui ne rend pas ce qu'elle devrait. Une recherche en erreur HTTP (5xx, délai dépassé) relève, elle, des trois premiers seuils, qui tolèrent de rares échecs ; la fiche est alors sautée pour cette itération.

Le smoke dure environ 8 secondes, moins que ce délai : ses seuils sont jugés à la fin, et un seul échec sur ses 15 requêtes suffit à le faire échouer.

Un refus survient avant tout envoi : aucune requête ne part. Les requêtes du test portent le User-Agent `dilane-shop-k6-catalogue/1.0`, qui permet de les isoler dans les journaux d'ingress-nginx. Codes de sortie de k6 : `0` réussite, `99` seuil franchi, `107` refus à la lecture des variables, `108` refus au contrôle des scénarios.

### Lancer le test

Depuis le **portable** ou une autre machine extérieure au VPS, jamais depuis le VPS : k6 y consommerait la mémoire et le processeur qu'il est censé éprouver. Référence : k6 v2.3.0 (le script fonctionne aussi avec la 1.8.1). Sans k6 installé, l'image officielle suffit :

```bash
# PORTABLE — depuis la racine du dépôt
alias k6='docker run --rm -i -v "$PWD/scripts/k6:/scripts/k6:ro" -w / grafana/k6:2.3.0'
```

**Smoke** : 15 requêtes, pour vérifier que le script et la cible répondent, et que le terme de recherche trouve un produit. À faire avant toute charge.

```bash
k6 run -e CIBLE=https://dilane-shop.store scripts/k6/catalogue.js
# Autre terme de recherche :
k6 run -e CIBLE=https://dilane-shop.store -e TERME_RECHERCHE="Enceinte" scripts/k6/catalogue.js
```

Le résumé doit afficher `http_reqs` à 15 et `checks_succeeded` à 100 %. Un smoke qui se termine en code `99` avec `recherches_inexploitables` à 5 signale un terme qui ne trouve rien dans ce catalogue.

**Charge** : 10 minutes. À lancer hors des heures d'affluence, avec le tableau de bord ouvert, et en surveillant la mémoire du VPS (`free -m`, `kubectl top pods -A`) dans un autre terminal.

```bash
k6 run -e CIBLE=https://dilane-shop.store -e MODE=charge \
  -e AUTORISER_CHARGE_PROD=oui scripts/k6/catalogue.js
# 8 utilisateurs virtuels au lieu de 6 :
k6 run -e CIBLE=https://dilane-shop.store -e MODE=charge -e VUS=8 \
  -e AUTORISER_CHARGE_PROD=oui scripts/k6/catalogue.js
```

Contre le cluster kind du poste : `-e CIBLE=https://dilane-shop.local`. Contre un Django lancé à la main : `-e CIBLE=http://localhost:8000`. Pour interrompre un test en cours : `Ctrl+C`.

### Quoi observer dans Grafana

Tableau de bord *Dilane Shop — signaux d'or*, période « Last 30 minutes », pendant et juste après le test :

| Panneau | Attendu pendant le palier |
| --- | --- |
| Pods Django collectés | 2 en permanence. Une baisse signale un pod redémarré, par exemple tué pour dépassement de mémoire. |
| Trafic — requêtes / s | le débit de k6 (environ 12 req/s à 6 VUS), réparti à peu près également entre les deux pods, en plus du trafic réel. La montée et la descente d'une minute sont visibles. |
| Erreurs — part des réponses | 5xx à 0. Les 4xx n'augmentent pas : les trois routes répondent 200. |
| Latence — p50 et p95 | la latence mesurée **dans Django**. C'est elle que surveille la règle d'alerte. |
| Saturation — requêtes en cours | 0 à 1 le plus souvent. 3 sur un pod veut dire que ses 3 workers sont tous occupés. |
| Latence p95 par route | `home`, `search_products` et `detail` séparément. La fiche produit est la seule des trois à lire un produit précis. |

Dans *Alerting → Alert rules*, la règle « Latence p95 élevée » est en « Normal (NoData) » tant que le site reçoit moins de 20 requêtes en 5 minutes (garde de volume). Pendant le test, elle passe à **« Normal »** : elle est alors réellement évaluée. Elle ne passe en *Pending*, puis en *Alerting* 2 minutes plus tard, que si le p95 mesuré dans Django dépasse 1 seconde. Le courriel suit alors dans les 30 s (`group_wait`), puis un courriel de résolution après la fin du test.

Côté serveur : `kubectl top pods -n dilane-shop` pendant le palier, et après le test, `kubectl get pods -n dilane-shop` pour vérifier qu'aucun redémarrage n'est apparu (colonne `RESTARTS`).

### Latence k6 et latence Grafana : deux mesures différentes

| | k6 (`http_req_duration`) | Grafana (`django_http_requests_latency_seconds`) |
| --- | --- | --- |
| Point de mesure | le client, à l'extérieur | l'intergiciel de Django, dans le pod |
| Commence | à l'envoi de la requête, connexion et TLS déjà établis | quand un worker gunicorn prend la requête en charge |
| Inclut | réseau aller-retour (portable ↔ VPS), ingress-nginx, **attente d'un worker libre**, traitement Django, transfert de la réponse | traitement Django seulement (intergiciels, vue, base de données, rendu) |
| Portée | les requêtes du test seulement | tout le trafic, visiteurs réels compris, hors `/metrics` et `/healthz/` |
| Calcul du p95 | exact, sur toutes les requêtes du test (montée et descente comprises) | estimé par l'histogramme (bornes 0,5 s, 1 s, 2,5 s…), sur une fenêtre glissante de 5 minutes |

La latence k6 est donc **toujours plus élevée** que celle de Grafana, de la durée du réseau au moins. Surtout, quand tous les workers sont occupés, une requête attend dans la file de gunicorn **avant** que Django ne commence à la mesurer : cette attente apparaît dans k6, pas dans Grafana. Un p95 k6 élevé avec un p95 Grafana bas signale donc un manque de workers ou un réseau lent, pas une application lente. La règle d'alerte ne voit que le second cas.

### Pourquoi la règle p95 ne se déclenchera probablement pas

Rien ne garantit que cette charge fasse passer la règle en *Alerting*, et c'est même peu probable :

- **La charge est bornée.** Chaque utilisateur virtuel attend sa réponse avant de continuer : au plus 8 requêtes sont en cours à la fois, pour 6 workers (2 pods × 3). Au pire, deux requêtes attendent un worker, et cette attente est invisible pour Django (voir ci-dessus).
- **Le catalogue est léger.** La page d'accueil pagine par 4 produits, la recherche est limitée à 24 résultats, et la fiche lit un seul produit.
- **Mesures de l'ancien parcours.** Avant le parcours à trois requêtes, le script ne faisait que deux GET, `/` et `/api/produits/?item-name=livre`, et cette recherche **ne trouvait aucun produit** : elle rendait une liste vide, moins coûteuse qu'une recherche fructueuse, et aucune fiche n'était ouverte. Les deux résultats ci-dessous concernent ce parcours et **ne valent pas pour le parcours actuel** à trois requêtes :
  - test du 27/09/2026 : 5 912 requêtes, 0 échec, p95 côté k6 de 74,86 ms ;
  - mesure locale, sur un seul pod Django (3 workers gunicorn, 2 CPU, SQLite, catalogue de démonstration de 30 objets), 6 VUS pendant 10 minutes : 6 406 requêtes, environ 11,9 req/s en palier, 100 % de 200, p95 k6 de 7,6 ms, p95 Django de l'ordre de 10 ms, 6 % de CPU pour Django, règle restée « Normal ». Ce n'était pas le VPS (processeur, PostgreSQL, réseau, TLS et ingress diffèrent).

  Le nouveau parcours n'a pas encore été mesuré sous charge. Il ajoute, à chaque itération, une recherche qui trouve des produits et l'ouverture d'une fiche : ses latences ne se déduisent pas des chiffres ci-dessus, seule une nouvelle mesure les donnera.

Si le p95 de Grafana reste sous 1 s, c'est un **résultat** : l'application tient cette charge. Il ne faut pas monter les VUS pour forcer l'alerte : le plafond de 8 protège le VPS, qui n'a pas de swap. Pour vérifier la chaîne « règle → politique → courriel », utiliser la règle temporaire décrite dans [Tester une alerte](#tester-une-alerte-sans-attendre-une-panne) : c'est un test distinct du test k6.

Si le terme de recherche ne trouve rien dans le catalogue visé, le test échoue au lieu de mesurer un parcours vide : c'est ce qui rendait l'ancien parcours peu représentatif.

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

Prérequis : l'application déjà déployée (espace de noms `dilane-shop` existant), et les deux Secrets `grafana-admin` et `grafana-smtp` créés et commités (voir [Secret Grafana](#secret-grafana) et [Secret SMTP des alertes](#secret-smtp-des-alertes)). Sans `grafana-smtp`, le pod Grafana reste en `ContainerCreating` : le volume qui monte ce Secret ne peut pas être créé.

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
sops --decrypt k8s/overlays/production/observabilite/grafana-smtp.sops.yaml \
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

**SERVEUR** — les trois règles d'alerte sont chargées et s'évaluent sans erreur

```bash
kubectl exec -n observabilite deploy/grafana -- sh -c '
  AUTH=$(printf "%s:%s" "$(cat /etc/grafana-admin/admin-user)" "$(cat /etc/grafana-admin/admin-password)" | base64 -w0)
  wget -qO- --header "Authorization: Basic $AUTH" http://localhost:3000/api/prometheus/grafana/api/v1/rules' \
  | grep -o '"state":"[a-zA-Z]*","name":"[^"]*"\|"health":"[a-z]*"'
```

Attendu : les trois règles (`Site injoignable`, `Taux d'erreur 5xx élevé`, `Latence p95 élevée`), chacune `"health":"ok"`, et `"state":"inactive"` quand tout va bien. Les identifiants sont lus dans le Secret monté, à l'intérieur du pod : ils n'apparaissent ni sur la ligne de commande ni dans l'historique du shell. Pour l'envoi du courriel lui-même, voir [Tester une alerte](#tester-une-alerte-sans-attendre-une-panne).

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
kubectl delete namespace observabilite                       # Prometheus, Grafana, alertes, données
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
