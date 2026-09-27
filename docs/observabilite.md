# Observabilité — Prometheus et Grafana (production)

Issue #44. Collecte et visualisation des métriques que Django expose sur `/metrics` depuis #45 : les quatre signaux d'or (latence, trafic, erreurs, saturation). Issue #48 : alertes par courriel, évaluées par Grafana lui-même (voir [Alertes](#alertes)).

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

**3. Une vraie règle, par un test de charge.** La règle « Latence p95 élevée » sera déclenchée par un **test de charge k6** : chaque pod Django n'a que 3 workers gunicorn synchrones, une charge soutenue sur les pages du catalogue fait monter les requêtes en attente, et donc le p95 au-delà d'une seconde. Le même test vérifie au passage la garde de volume (plus de 20 requêtes en 5 minutes) et, selon la charge atteinte, la saturation du tableau de bord. Ce test de charge est à écrire ; à lancer hors des heures d'affluence, depuis une machine extérieure au VPS (k6 sur le VPS consommerait la mémoire qu'il est censé éprouver), en surveillant `kubectl top pods -A`. La règle 5xx ne se provoque pas proprement en production (aucune route n'échoue volontairement) : elle a été vérifiée par les tests `promtool` décrits plus haut.

La règle « Site injoignable » peut être éprouvée pour de bon lors d'une maintenance planifiée, par `kubectl scale -n dilane-shop deploy/django --replicas=0` puis `--replicas=2` : c'est une vraie coupure du site, à réserver à ce cas.

### Limites connues

- **État en mémoire.** L'Alertmanager intégré garde ses silences et son journal d'envoi dans la base SQLite de Grafana, donc dans l'`emptyDir` : un redémarrage de Grafana efface les silences, et une alerte encore active peut être notifiée une seconde fois.
- **Quota Brevo.** Les courriels d'alerte consomment le même quota d'envoi que les courriels transactionnels de la boutique. Le groupement par règle et le rappel toutes les 4 heures limitent le volume.
- **Un seul canal.** Si Brevo ou la boîte de réception est indisponible, l'alerte n'arrive pas, et rien ne le signale. Un second point de contact (webhook, messagerie) serait le remède.

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
