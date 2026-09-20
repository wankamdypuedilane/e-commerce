# ADR-002 — Kubernetes plutôt qu'un serveur unique

## Statut

Accepté — 20/09/2026. Implémenté au Sprint 10 (issues #15 à #21). Document rédigé au titre de l'issue #22.

---

## Contexte

Deux architectures se sont succédé avant cette décision, et aucune ne répond au besoin actuel.

**Le déploiement EC2.** Une instance unique créée par Terraform, configurée au démarrage par `infra/terraform/bootstrap.sh` : installation des paquets, clone du dépôt, virtualenv, écriture du `.env`, migrations, Gunicorn et Nginx. Cette chaîne est décrite et critiquée en détail dans l'[ADR-001](001-conteneurisation.md). Elle n'est plus exécutable : **le compte AWS est fermé**, l'instance est supprimée, et le job `deploy` de la CI est neutralisé par `if: false` depuis le Sprint 9.

**Docker Compose, mis en place au Sprint 9.** Il rend l'exécution reproductible — même image, même interpréteur, même base PostgreSQL en local et ailleurs. Mais il décrit une seule machine, et trois limites en découlent :

- **Pas de redémarrage sur un autre nœud.** `restart: unless-stopped` relance un conteneur mort sur la même machine. Si la machine tombe, le site tombe avec elle. Il n'existe aucun mécanisme qui replace la charge ailleurs.
- **Pas de mise à jour sans coupure.** `docker compose up -d` après un changement d'image arrête le conteneur `web` puis en démarre un nouveau. Entre les deux, le site ne répond pas. Rien ne vérifie non plus que le nouveau conteneur est capable de servir avant de lui envoyer du trafic : Compose observe le processus, pas l'application.
- **Les secrets vivent dans un fichier `.env` sur disque.** `env_file: .env` lit un fichier en clair à la racine du projet, présent en permanence sur la machine hôte, avec la clé secrète Django, le mot de passe PostgreSQL et les clés Stripe et Brevo.

Le besoin est donc : un hébergement durable, à coût nul ou proche de zéro, capable de replacer un processus, de remplacer une version sans coupure et de ne pas écrire les secrets sur le disque de l'hôte.

---

## Décision

**Adopter Kubernetes comme plateforme de déploiement.**

L'adoption se fait en deux temps, délibérément séparés :

**1. Apprentissage et validation sur `kind`, en local.** `kind` (Kubernetes in Docker) crée un cluster complet à partir de conteneurs Docker. La configuration est versionnée dans `k8s/kind-cluster.yaml` : un nœud de contrôle portant le label `ingress-ready=true` avec les ports 80 et 443 mappés vers l'hôte, et deux nœuds de travail — deux nœuds précisément pour rendre la répartition des pods observable plutôt que théorique. Le cluster se recrée à l'identique par une commande.

**2. Hébergement durable sur `k3s`, sur une VM Azure.** `k3s` est une distribution Kubernetes légère, en un seul binaire, adaptée à une machine modeste. La cible est une VM **B2pts v2**, couverte par l'offre gratuite Azure pendant 12 mois. Les manifestes écrits pour `kind` s'appliquent sans modification sur `k3s` : c'est la même API. Seuls changent l'`IngressClass` par défaut, la `StorageClass` et l'autorité qui signe les certificats.

Ce que cette décision met en place, manifeste par manifeste :

| Manifeste | Objet | Ce qu'il apporte |
|---|---|---|
| `k8s/00-namespace.yaml` | Namespace `dilane-shop` | Isole le projet et permet de tout supprimer d'un coup |
| `k8s/01-configmap.yaml` | ConfigMap, 11 clés | Configuration non sensible, séparée de l'image |
| `k8s/02-secrets.example.yaml` | Modèle documenté | Le Secret réel est créé par `kubectl`, jamais versionné |
| `k8s/03-postgres.yaml` | Service headless + StatefulSet | Identité réseau et volume stables pour la base |
| `k8s/04-django.yaml` | Service + Deployment, 2 replicas | Répartition, `maxUnavailable: 0`, probes |
| `k8s/05-migration-job.yaml` | Job `django-migrate` | Migrations hors du cycle de vie des pods web |
| `k8s/06-ingress.yaml` | Ingress | Point d'entrée unique, redirection HTTP vers HTTPS |
| `k8s/07-ingress-controller-patch.yaml` | Correctif de placement | Contraint le contrôleur au nœud qui expose 80 et 443 |
| `k8s/08-tls.yaml` | Issuer + Certificate cert-manager | Certificat émis et renouvelé par le cluster |

---

## Alternatives considérées

### A. AKS — Azure Kubernetes Service, en continu

Le plan gratuit d'AKS ne facture pas le plan de contrôle. Tout le reste est facturé : les machines virtuelles du pool de nœuds, le load balancer public et l'adresse IP publique, soit **environ 60 USD par mois** pour une configuration minimale à deux nœuds.

Écartée pour une raison arithmétique : le crédit étudiant disponible est de **100 USD**. À 60 USD par mois, il est épuisé en **6 à 7 semaines**. Le cluster s'arrêterait donc pendant le projet, sans préavis utile, et l'arrêt surviendrait précisément au moment où le déploiement commencerait à servir à quelque chose.

AKS reste pertinent pour une session de travail délimitée — créer le cluster, faire la démonstration, le détruire — et cet usage n'est pas exclu.

### B. Docker Compose sur un VPS

Louer un VPS à **environ 4 EUR par mois** et y exécuter le `docker-compose.yml` existant. C'est l'option la moins chère et la plus rapide à mettre en œuvre : aucun apprentissage, aucun manifeste à écrire.

Écartée parce qu'elle ne corrige aucune des trois limites du contexte. Il n'y a ni auto-guérison — un conteneur mort redémarre sur la même machine, et une machine morte emporte le site — ni mise à jour progressive : le remplacement d'image reste un arrêt suivi d'un démarrage. Le `.env` resterait sur le disque du VPS. Payer 4 EUR par mois pour reproduire les limites déjà constatées en local n'apporte que l'adresse IP publique.

### C. EKS ou GKE

Les services Kubernetes gérés d'AWS et de Google facturent le plan de contrôle lui-même : **73 USD par mois**, avant tout nœud, tout volume et tout load balancer.

Écartée sans examen supplémentaire : le seul plan de contrôle consomme les trois quarts du crédit étudiant en un mois. S'y ajouterait, pour AWS, un compte fermé à rouvrir.

### D. Rester sur Docker Compose en local uniquement

Ne rien déployer, et se contenter de l'exécution locale.

Écartée : elle laisse le projet sans hébergement et repousse indéfiniment les questions que seul un déploiement réel fait apparaître — placement, reprise, certificats, migrations concurrentes.

---

## Conséquences

### Positives

Les points ci-dessous ont été observés pendant le Sprint 10, sur le cluster `kind` à trois nœuds. Ce sont des constats, pas des propriétés annoncées.

**Les pods sont répartis automatiquement sur deux nœuds différents.** Les deux replicas du Deployment `django` ont été placés par l'ordonnanceur sur `dilane-shop-worker` et `dilane-shop-worker2`, sans règle d'anti-affinité écrite. La perte d'un nœud laisse donc un replica en service.

**La suppression manuelle de `postgres-0` n'a pas perdu de données.** Le pod a été supprimé à la main. Le StatefulSet l'a recréé avec **le même nom** — c'est la propriété qui distingue un StatefulSet d'un Deployment — et le PersistentVolumeClaim `donnees-postgres-0` a été rattaché au nouveau pod. Les données étaient intactes. Sous Docker Compose, la persistance reposait sur un volume nommé attaché à une machine ; ici, elle repose sur une revendication de volume qui suit l'identité du pod.

**La mise à jour progressive a été observée, chronomètre à l'appui.** Lors du remplacement d'image, le nouveau pod est resté **21 secondes en `0/1` après être passé en `Running`**. Pendant ces 21 secondes, il ne recevait aucun trafic : la readiness probe interrogeait `/healthz/`, et tant qu'elle échouait, le pod restait hors du Service. Combiné à `maxUnavailable: 0`, aucun pod prêt n'est retiré avant qu'un remplaçant ne soit prêt. C'est exactement ce que Docker Compose ne peut pas faire : il n'a pas la notion « le processus tourne mais l'application n'est pas encore prête ».

**Les migrations sont isolées dans un Job.** `k8s/05-migration-job.yaml` exécute `migrate --noinput` une fois, dans un pod dédié qui se termine. Avec plusieurs replicas, jouer les migrations au démarrage de chaque pod ferait s'exécuter `migrate` en parallèle sur la même base. `bootstrap.sh` ne permettait pas cette séparation : les migrations y étaient une ligne au milieu du script d'installation, indissociable du reste et rejouée à chaque provisionnement.

**Les secrets sont injectés en mémoire, jamais écrits sur disque.** Le Secret est créé par `kubectl create secret`, stocké dans `etcd`, et exposé aux conteneurs comme variables d'environnement via `envFrom.secretRef`. Aucun fichier en clair n'existe sur la machine hôte, contrairement au `.env` de Docker Compose. Seul un **modèle sans valeur** est versionné.

### Négatives

**La courbe d'apprentissage est réelle.** Le sprint a demandé d'assimiler, pour un même besoin, une douzaine d'objets là où Docker Compose en demandait deux : Namespace, ConfigMap, Secret, Service, Service headless, Deployment, StatefulSet, PersistentVolumeClaim, Job, Ingress, IngressClass, Issuer, Certificate. Une panne de placement du contrôleur Ingress a demandé **un diagnostic en cinq étapes** avant d'aboutir — le détail figure dans la rétrospective du sprint. Le coût n'est pas théorique : il se paie en temps, au moment où quelque chose ne marche pas.

**Les Secrets Kubernetes sont encodés en base64, pas chiffrés.** C'est la conséquence la plus facile à mal comprendre. Une seule commande suffit à lire une valeur en clair :

```bash
kubectl get secret dilane-shop-secrets -n dilane-shop \
  -o jsonpath='{.data.DJANGO_SECRET_KEY}' | base64 -d
```

Quiconque a le droit de lire les Secrets du namespace a les clés Stripe. Le chiffrement au repos d'`etcd` n'est pas activé par défaut ; il doit être configuré sur le cluster. Le gain par rapport au `.env` est donc que le secret n'est plus un fichier sur un disque, pas qu'il est devenu confidentiel. Un dispositif dédié — Sealed Secrets, External Secrets Operator, ou le coffre du fournisseur cloud — reste nécessaire pour un déploiement réel. L'avertissement est écrit dans `k8s/02-secrets.example.yaml`.

**Il y a davantage de pièces mobiles à surveiller.** `docker compose ps` donne deux lignes. Le même état demande ici de regarder les pods de trois namespaces au moins (`dilane-shop`, `ingress-nginx`, `cert-manager`), l'état du Certificate, celui du PersistentVolumeClaim et celui du Job de migration. Chacun de ces composants a sa propre version, son propre cycle de mise à jour et ses propres modes de panne. Le contrôleur Ingress et cert-manager sont deux logiciels tiers supplémentaires dans la chaîne.

**Let's Encrypt est inutilisable en local, d'où un certificat auto-signé.** La validation ACME suppose un domaine public joignable depuis Internet. `dilane-shop.local` n'existe que dans le fichier `hosts` du poste. `k8s/08-tls.yaml` déclare donc un `Issuer` `selfSigned`, avec la durée et la fenêtre de renouvellement de Let's Encrypt (90 jours, renouvellement 15 jours avant). Conséquence pratique : le navigateur affiche un avertissement de sécurité, et `curl` exige `-k`. Le passage à un certificat reconnu suppose le domaine `dilane-shop.store` (issue #30) et ne changera que l'`issuerRef`.

---

## Critères de révision

Cette décision sera réexaminée si l'un des trois éléments suivants change :

- **Le trafic réel mesuré.** Tant qu'il reste nul ou confidentiel, Kubernetes est un investissement d'apprentissage, pas une réponse à une charge. Un trafic mesuré qui saturerait une VM `k3s` justifierait un cluster géré ; un trafic durablement nul justifierait l'inverse.
- **Le besoin d'un SLA.** Aucun engagement de disponibilité n'est pris aujourd'hui. Un nœud `k3s` unique reste un point de défaillance unique, quelle que soit la plateforme installée dessus : si une disponibilité contractuelle devenait nécessaire, il faudrait plusieurs nœuds, donc un plan de contrôle géré, donc le coût écarté en alternative A.
- **Le budget.** Le raisonnement ci-dessus repose sur 100 USD de crédit étudiant et une offre Azure gratuite de 12 mois. La fin de cette offre, ou l'apparition d'un budget d'exploitation, rouvre l'arbitrage — dans un sens comme dans l'autre.

---

## Liens

- Issues : #15 (cluster kind), #16 (Deployment et Service), #17 (StatefulSet et PVC), #18 (Secrets et ConfigMap), #19 (Job de migration), #20 (probes), #21 (Ingress et HTTPS), #22 (cet ADR), #30 (domaine `dilane-shop.store`)
- Commits : `cf7b30e`, `b8834da`, `748a5a4`, `29ee851`, `b9da8ac`
- [ADR-001 — Conteneurisation de l'application](001-conteneurisation.md) — l'étape précédente, et le détail des défauts de `bootstrap.sh`
- [ADR-003 — Monolithe modulaire plutôt que microservices](003-monolithe-modulaire.md) — pourquoi un seul Deployment applicatif et non six
- [docs/sprints/sprint-10-kubernetes.md](../sprints/sprint-10-kubernetes.md) — déroulé du sprint et diagnostic du placement de l'Ingress
- [docs/AUDIT.md](../AUDIT.md) — dette 1.6 (absence de HTTPS)
