# Sprint 10 — Kubernetes

**Période :** 20/09/2026, 17h35 → 19h04
**Commits :** 5 (`cf7b30e`, `b8834da`, `748a5a4`, `29ee851`, `b9da8ac`)
**Issues fermées :** #15, #16, #17, #18, #19, #20, #21 — #22 traitée en fin de sprint
**Documents produits :** `docs/adr/002-kubernetes.md`, `docs/sprints/sprint-10-kubernetes.md`, section Kubernetes du `README.md`
**Manifestes produits :** `k8s/`, 10 fichiers

---

## 1. Objectif du sprint

Déployer l'application sur un cluster Kubernetes, en local, avec des manifestes versionnés.

Le Sprint 9 avait rendu l'exécution reproductible : une image Docker, une base PostgreSQL en service séparé, une configuration lue depuis l'environnement. Il laissait trois limites explicites, énumérées dans sa rétrospective : pas de redémarrage sur une autre machine, pas de mise à jour sans coupure, et un `.env` en clair sur le disque de l'hôte. Le compte AWS étant fermé, aucun hébergement n'existait par ailleurs.

L'objectif retenu a donc été de décrire l'ensemble de la pile en manifestes Kubernetes et de la faire fonctionner sur un cluster `kind` à trois nœuds, jusqu'à obtenir le site en HTTPS. Le choix de Kubernetes, ses alternatives chiffrées et ses contreparties font l'objet de l'[ADR-002](../adr/002-kubernetes.md).

---

## 2. Issues traitées

| # | Intitulé | Résultat |
|---|---|---|
| 15 | Installer kind et créer un cluster local | **Fermée.** |
| 16 | Deployment et Service pour l'application Django | **Fermée.** |
| 17 | StatefulSet et PersistentVolumeClaim pour PostgreSQL | **Fermée.** |
| 18 | Secrets et ConfigMap Kubernetes | **Fermée.** |
| 19 | Job de migration distinct des pods web | **Fermée.** |
| 20 | Probes liveness et readiness | **Fermée.** |
| 21 | Ingress et HTTPS avec cert-manager | **Fermée avec un critère non réalisé** (voir ci-dessous). |
| 22 | ADR-002 : Kubernetes plutôt qu'un serveur unique | **Traitée en fin de sprint**, encore ouverte sur GitHub au moment de la rédaction. |

### Détail

**#15 — Cluster kind.** `kind` v0.33.0, configuration versionnée dans `k8s/kind-cluster.yaml`. Le cluster `dilane-shop` compte trois nœuds en Kubernetes v1.37.0 : un `control-plane` portant le label `ingress-ready=true` avec les ports 80 et 443 mappés vers l'hôte, et deux `worker`. Les deux nœuds de travail ont été demandés pour une raison précise : rendre la répartition des pods visible. Avec un seul nœud, « l'ordonnanceur place les pods » reste une affirmation invérifiable.

Le cluster se recrée à l'identique par `kind create cluster --config k8s/kind-cluster.yaml`. C'est la première fois dans ce projet qu'un environnement d'exécution complet est décrit par un fichier versionné plutôt que par un script d'installation.

**#17 et #18 — Namespace, configuration, secrets, PostgreSQL.** Le Namespace `dilane-shop` isole le projet ; sa suppression emporte tout ce qu'il contient. Le ConfigMap `dilane-shop-config` porte 11 clés non sensibles. Le Secret `dilane-shop-secrets` porte 8 clés et **n'est pas versionné** : seul `k8s/02-secrets.example.yaml` l'est, un modèle sans aucune valeur, qui documente la commande `kubectl create secret` et avertit qu'un Secret Kubernetes est encodé en base64 et non chiffré.

PostgreSQL est un StatefulSet à un replica, avec un Service headless (`clusterIP: None`) et un `volumeClaimTemplates` de 2 Gi. `PGDATA` pointe vers le sous-répertoire `/var/lib/postgresql/data/pgdata` : PostgreSQL refuse un répertoire de données non vide, et le volume monté contient un dossier `lost+found`.

La persistance a été vérifiée, pas supposée : le pod `postgres-0` a été supprimé à la main. Il a été recréé avec le même nom, rattaché au même PersistentVolumeClaim `donnees-postgres-0`, et les données étaient intactes.

**#16 et #19 — Deployment Django et Job de migration.** Deployment à 2 replicas, Service `ClusterIP` sur le port 8000. Stratégie `RollingUpdate` avec `maxSurge: 1` et `maxUnavailable: 0` : aucun pod en service n'est retiré avant qu'un remplaçant ne soit prêt. Les deux replicas ont été placés par l'ordonnanceur sur deux nœuds différents, sans règle d'anti-affinité écrite.

Les migrations sont sorties du cycle de vie des pods et confiées au Job `django-migrate` (`backoffLimit: 3`, `ttlSecondsAfterFinished: 300` pour laisser le temps de lire les journaux). La raison est mécanique : avec plusieurs replicas, jouer `migrate` au démarrage de chaque pod ferait s'exécuter plusieurs migrations concurrentes sur la même base. C'est le défaut que `bootstrap.sh` portait par construction, sans que le problème apparaisse — l'instance étant unique.

**#20 — Probes.** L'endpoint `/healthz/` (`shop/views.py:423`) exécute un `SELECT 1` et retourne 503 si la base est injoignable, 200 sinon. Il est volontairement sans authentification et sans gabarit : la sonde doit pouvoir l'appeler avant que le pod ne reçoive du trafic.

La readiness probe l'interroge toutes les 10 s, la liveness toutes les 20 s avec un `initialDelaySeconds` de 30. Les seuils de la liveness sont plus larges à dessein : une lenteur passagère doit retirer le pod du Service, pas le tuer. Les deux sondes envoient un en-tête `Host: localhost`, faute de quoi `ALLOWED_HOSTS` rejetterait leurs requêtes, qui arrivent par l'adresse IP du pod.

**#21 — Ingress et HTTPS.** Contrôleur `ingress-nginx` v1.15.1, manifeste `provider/kind`. L'Ingress route `dilane-shop.local` vers le Service `django`, avec `proxy-body-size: 10m` pour les images produits et `ssl-redirect: "true"`. cert-manager v1.16.2 émet le certificat à partir d'un `Issuer` `selfSigned`, dans le Secret `tls-dilane-shop` que l'Ingress consomme. Vérifié : HTTP répond **308** vers HTTPS, HTTPS répond **200**.

Le critère « certificat Let's Encrypt » **n'est pas réalisé**, et ne pouvait pas l'être : la validation ACME exige un domaine public joignable depuis Internet, alors que `dilane-shop.local` n'existe que dans le fichier `hosts` du poste. Le certificat est auto-signé, avec la durée et la fenêtre de renouvellement de Let's Encrypt (90 jours, renouvellement 15 jours avant expiration) afin que le passage à un `ClusterIssuer` réel ne change que l'`issuerRef`. L'issue #30 porte le domaine `dilane-shop.store`.

---

## 3. Décisions prises en cours de route

### Deux nœuds de travail plutôt qu'un

Un cluster `kind` à un seul nœud aurait suffi à faire tourner l'application. Le troisième nœud a été ajouté pour rendre observable ce qui, autrement, aurait été lu dans une documentation : la répartition des pods, et le fait qu'un pod supprimé est replacé ailleurs. Le coût est nul en local ; le bénéfice est qu'aucune propriété de cette rétrospective n'est une propriété annoncée.

### Le correctif de placement de l'Ingress est versionné, pas appliqué à la main

Le contrôleur Ingress s'est placé sur un nœud de travail (voir section 4). La correction pouvait se faire en une commande `kubectl patch` dans un terminal. Elle a été écrite dans `k8s/07-ingress-controller-patch.yaml`, avec le commentaire expliquant pourquoi elle existe.

La raison est celle qui a motivé tout le sprint : une correction appliquée à la main est une divergence de plus entre ce que le dépôt décrit et ce que le cluster contient. C'est exactement le défaut relevé par l'audit sur `bootstrap.sh` et `deploy.yml`, à une autre échelle.

### Un Secret créé par `kubectl`, et un modèle versionné

Deux options existaient pour les secrets : un manifeste `Secret` chiffré par un outil tiers (Sealed Secrets), ou une création par `kubectl create secret` hors du dépôt.

La seconde a été retenue pour ce sprint : elle n'ajoute aucun composant au cluster et suffit tant que le cluster est local. Ce qui est versionné est un **modèle sans valeur**, qui documente la commande exacte et ses huit clés. La limite est écrite noir sur blanc dans le fichier plutôt que découverte plus tard : un Secret Kubernetes est encodé, pas chiffré.

### Le certificat auto-signé garde les paramètres de Let's Encrypt

`duration: 2160h` et `renewBefore: 360h` n'ont aucune nécessité technique pour un certificat auto-signé, qui pourrait durer dix ans. Ces valeurs sont celles de Let's Encrypt. Le renouvellement automatique par cert-manager est donc exercé dans les mêmes conditions que la cible, et la bascule vers un certificat réel ne modifiera qu'une référence d'émetteur.

---

## 4. Ce qui a surpris

### Le contrôleur Ingress s'est placé sur le mauvais nœud, et le manifeste officiel en était la cause

Le symptôme : l'Ingress créé, la configuration relue et correcte, aucune réponse sur `dilane-shop.local`.

Le diagnostic a demandé cinq étapes :

1. **Vérifier l'Ingress** — `kubectl describe ingress` : hôte, chemin, `ingressClassName: nginx`, backend `django:8000`. Tout était conforme.
2. **Vérifier le Service et ses endpoints** — le Service `django` existait et pointait vers deux adresses de pods prêts. La chaîne Ingress → Service → pods n'était donc pas en cause.
3. **Vérifier que le contrôleur tournait** — `kubectl get pods -n ingress-nginx` : un pod `Running`, `1/1`. C'est ici que le diagnostic aurait pu s'arrêter sur une fausse piste, puisque tout était « vert ».
4. **Regarder où il tournait** — `kubectl get pods -n ingress-nginx -o wide`. Le contrôleur était sur `dilane-shop-worker`. Or les ports 80 et 443 ne sont mappés vers l'hôte que sur le nœud de contrôle, par `extraPortMappings` dans `k8s/kind-cluster.yaml`. Le trafic arrivait donc sur un nœud où personne n'écoutait.
5. **Relire le manifeste appliqué** — le manifeste `provider/kind` d'ingress-nginx est censé contraindre le contrôleur au nœud portant `ingress-ready=true`. Sur la version installée (v1.15.1), le `nodeSelector` du Deployment ne contenait que `kubernetes.io/os: linux`. Le label `ingress-ready` n'y figurait pas, alors que le nœud de contrôle le portait bien.

Deux enseignements, de portée inégale.

Le premier, ponctuel : **c'est `-o wide` qui a résolu le problème**, pas la lecture de la configuration de l'Ingress, qui était correcte depuis le début. Un pod `Running` et `1/1` ne dit rien de l'endroit où il s'exécute, et l'endroit était toute la question. Chercher l'erreur dans l'objet qu'on vient d'écrire est un réflexe coûteux quand l'erreur est dans le placement.

Le second, plus général : le manifeste d'installation était un fichier tiers, appliqué depuis une URL, supposé conforme à sa documentation. Il ne l'était pas. Un fichier appliqué sans être lu reste une boîte noire jusqu'au moment où il se comporte autrement qu'annoncé — et ce moment arrive au pire endroit, dans un composant qu'on n'a pas écrit.

La correction est versionnée dans `k8s/07-ingress-controller-patch.yaml`. Le contrôleur s'exécute depuis sur `dilane-shop-control-plane`.

### Les réglages de sécurité HTTPS existaient déjà dans `settings.py`

Avant d'ajouter la configuration HTTPS de Django, une relecture de `ecommerce/settings.py` a montré qu'un bloc complet s'y trouvait déjà, écrit lors d'un sprint antérieur (`settings.py:45-51`) : `SECURE_PROXY_SSL_HEADER`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` et les trois réglages HSTS.

Il était **plus fin que celui qui allait être ajouté** : chaque réglage est piloté par une variable d'environnement avec une valeur par défaut sûre, ce qui permet de les activer par environnement sans toucher au code — exactement ce qu'il faut quand le certificat local est auto-signé et que HSTS ne doit surtout pas être activé.

Ce qui manquait n'était donc pas dans l'application, mais devant elle : il n'y avait aucun HTTPS à faire respecter. **La dette 1.6 de l'audit concernait l'infrastructure, pas le code.** Le sprint n'a ajouté à `.env.example` que la documentation des noms de variables déjà lus par `settings.py`.

L'enseignement tient en une ligne : l'audit avait localisé la dette sur `settings.py:40-45`, et cette localisation était inexacte. Relire le code avant d'appliquer une correction d'audit a évité d'écraser un dispositif meilleur par un dispositif plus grossier.

### L'endpoint de santé a été validé dans ses deux états

Un endpoint de santé qui retourne toujours 200 ne se distingue pas d'un endpoint cassé qui retourne toujours 200. `/healthz/` a donc été vérifié dans les deux états :

- **503**, base injoignable — `{"status": "degraded", "database": "unreachable"}` ;
- **200**, base joignable — `{"status": "ok", "database": "reachable"}`.

Le premier état est celui qui donne sa valeur à la sonde. Sans le `SELECT 1`, la readiness probe n'aurait mesuré que la capacité de Gunicorn à répondre — un pod incapable de servir une seule page aurait été déclaré prêt et aurait reçu du trafic.

---

## 5. Reporté

### Domaine `dilane-shop.store` et certificat Let's Encrypt

Le certificat actuel est auto-signé : le navigateur affiche un avertissement et `curl` exige `-k`. Passer à un certificat reconnu suppose un domaine public, un enregistrement DNS pointant vers l'hébergement, et un `ClusterIssuer` ACME. La mécanique du certificat ne change pas — seul l'`issuerRef` de `k8s/08-tls.yaml` change. Issue #30.

### Sauvegarde automatisée

Il n'existe toujours aucune procédure de sauvegarde active. Les scripts `scripts/backup_postgres.sh` et `scripts/restore_postgres.sh` visent des chemins d'un serveur qui n'existe plus, et n'ont jamais fonctionné. Les données résident désormais dans le PersistentVolumeClaim `donnees-postgres-0`, ce qui déplace la question sans y répondre : une sauvegarde suppose un `CronJob` exécutant `pg_dump` et un stockage hors du cluster. Dette 2.5 de l'audit, ouverte depuis le Sprint 7.

### Déploiement sur la VM Azure

Toute la validation de ce sprint a été faite sur `kind`, en local. L'hébergement durable décidé par l'[ADR-002](../adr/002-kubernetes.md) — `k3s` sur une VM Azure B2pts v2 — n'est pas encore créé. Les manifestes s'appliqueront tels quels, mais trois éléments diffèrent et devront être traités : l'`IngressClass` fournie par `k3s` (Traefik par défaut), la `StorageClass` — `local-path` sur `kind` — et l'émetteur de certificats, qui devient ACME dès qu'un domaine public existe.

### CI publiant l'image dans un registre

`kind load docker-image` transfère une image construite localement dans les nœuds du cluster. Cela ne fonctionne que parce que le cluster tourne sur le poste. Un cluster distant impose de publier l'image dans un registre, donc de choisir ce registre, d'authentifier la CI, de définir une politique de nommage des versions et une purge. Le besoin était déjà noté comme conséquence négative de l'[ADR-001](../adr/001-conteneurisation.md) au Sprint 9 ; il n'a pas été traité ici et reste le prérequis du déploiement distant.

### Écart de version d'image entre le Job et le Deployment

`k8s/04-django.yaml` référence `dilane-shop:0.2.0`, `k8s/05-migration-job.yaml` référence encore `dilane-shop:0.1.0`. Les deux étiquettes sont chargées dans le cluster, et les migrations appliquées sont les mêmes — le Job n'a donc pas échoué et l'écart est passé inaperçu. Il reste à corriger : la version qui migre le schéma doit être celle qui le lit.

### Éléments hérités, toujours ouverts

| Dette | Élément | Origine |
|---|---|---|
| 2.5 | Aucune sauvegarde active de la base | Sprint 7 |
| 4.4 | Deux champs d'image concurrents sur `Product` (`image`, `image_file`) | Sprint 9 |

Les écarts relevés en revue du Sprint 9 — fichiers `.pyc` suivis, `CSRF_TRUSTED_ORIGINS`, `LOGGING`, répertoire `Templates`, version Python de la CI — ont tous été traités avant ce sprint par le commit `c7dcaee` (issues #25 à #28). La CI s'exécute désormais sur Python 3.13, comme l'image.

---

## 6. État en fin de sprint

| Élément | État |
|---|---|
| Cluster `kind` `dilane-shop`, 3 nœuds | Actif, Kubernetes v1.37.0 |
| Pods `django` | 2/2 prêts, sur deux nœuds différents |
| `postgres-0` | Prêt, PVC `donnees-postgres-0` lié, 2 Gi |
| Ingress `dilane-shop.local` | Actif, HTTP 308 vers HTTPS, HTTPS 200 |
| Certificate `dilane-shop-tls` | `Ready: True`, auto-signé |
| Job `django-migrate` | Terminé et purgé par `ttlSecondsAfterFinished` |
| Job CI `deploy` (EC2) | Toujours neutralisé par `if: false` |
| Déploiement distant | Aucun — cluster local uniquement |

Le site n'est accessible qu'en local. Ce sprint a produit une architecture de déploiement vérifiée, pas un déploiement.

---

## 7. Prochaines échéances

- **Sprint 11** — Tests. Prérequis annoncé dès le Sprint 9 et toujours pas entamé.
- **Sprint 12** — Découpage en six apps Django, conformément à l'[ADR-003](../adr/003-monolithe-modulaire.md).
- **Hors sprint** — domaine `dilane-shop.store` (#30), VM Azure, registre d'images, sauvegarde automatisée.
