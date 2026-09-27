# Sprint 13 — Mise en production

**Période :** 26/09/2026, 07h43 → 27/09/2026, 07h19
**Commits :** 7 sur `main` (`4b84315`, `0aa7334`, `fb77897`, `6b65ace`, `1db904d`, `0203202`, `0fba9d2`)
**Issues fermées :** #96, #43, #31, #41, #42, #40 (abandonnée), #83
**Issue ouverte pendant le sprint :** #96
**Documents produits :** `docs/deploiement-production.md`, addenda datés de l'[ADR-002](../adr/002-kubernetes.md) et de l'[ADR-004](../adr/004-gestion-des-secrets.md)
**Manifestes produits :** `k8s/base/`, `k8s/overlays/local/`, `k8s/overlays/production/`, `k8s/base/09-backup-cronjob.yaml`

---

## 1. Objectif du sprint

Mettre l'application en production, accessible en HTTPS sur `dilane-shop.store`.

Les trois sprints précédents avaient préparé chaque pièce sans jamais en exercer l'assemblage à distance : une image reproductible au Sprint 9, des manifestes Kubernetes validés sur `kind` au Sprint 10, une chaîne de contrôles et des secrets chiffrés au Sprint 12. Aucun hébergement n'existait depuis la fermeture du compte AWS, et l'ADR-002 annonçait une VM Azure qui n'avait jamais été créée.

L'objectif retenu a donc été de partir d'un serveur nu et d'aller jusqu'au site joignable depuis Internet, avec un certificat reconnu par les navigateurs, en consignant chaque étape pour pouvoir la rejouer.

---

## 2. Issues traitées

| # | Intitulé | Résultat |
|---|---|---|
| 40 | Provisionner la VM Azure B2pts v2 | **Abandonnée.** Remplacée par #96 (section 5). |
| 96 | Provisionner un VPS OVH pour le déploiement | **Fermée.** Ouverte et traitée le même jour. |
| 43 | Publier l'image dans un registre depuis la CI | **Fermée.** |
| 31 | Centraliser la version de l'image dans les manifests | **Fermée**, par construction. |
| 41 | Installer k3s et déployer les manifests | **Fermée.** |
| 42 | Pointer `dilane-shop.store` et obtenir un certificat Let's Encrypt | **Fermée.** |
| 83 | Sauvegarde automatisée de PostgreSQL | **Fermée**, avec deux points explicitement reportés (section 6). |

### Détail

**#96 — Le serveur.** VPS OVH VPS-1 : 2 vCPU, 4 Go de mémoire, Gravelines, Ubuntu 24.04 en `amd64`. Accès par clé Ed25519 uniquement, mot de passe et connexion `root` désactivés. L'issue avait été ouverte le matin même, après l'abandon d'Azure.

**#43 — L'image dans un registre.** Une étape de la CI publie l'image sur `ghcr.io/wankamdypuedilane/dilane-shop` après que tous les contrôles ont réussi, et seulement sur `main` : une proposition de pull request ne publie rien (`4b84315`). Deux étiquettes sont posées, `latest` et l'empreinte du commit. L'authentification utilise le `GITHUB_TOKEN` fourni au workflow, avec la permission `packages: write` : aucun secret à configurer. Le paquet est public, ce qui évite un `imagePullSecret` dans le cluster.

**#31 — Une seule étiquette d'image.** Le Sprint 10 avait laissé le Deployment sur `dilane-shop:0.2.0` et le Job de migration sur `0.1.0`, sans que rien ne le signale. Le champ `images` d'une surcouche Kustomize vaut pour les deux ressources à la fois : l'écart n'est plus exprimable. L'issue est fermée par construction, non par correction ponctuelle.

**#41 — k3s et les manifestes.** k3s installé avec `--disable traefik`, puisque les manifestes déclarent `ingressClassName: nginx` et des annotations propres à ingress-nginx, et `--write-kubeconfig-mode 644` pour piloter le cluster sans `sudo`. ingress-nginx en variante `baremetal`, cert-manager, puis `kubectl apply -k k8s/overlays/production`.

**#42 — Domaine et certificat.** Enregistrement `A` de `dilane-shop.store` vers l'adresse du VPS. Certificat demandé d'abord à l'environnement de test de Let's Encrypt, puis basculé sur celui de production après une émission réussie (`6b65ace`). Relevé le 27/09 : HTTP répond `308` vers HTTPS, HTTPS répond `200`, l'émetteur est Let's Encrypt et le certificat court jusqu'au 25/12/2026.

**#83 — Sauvegarde.** CronJob quotidien à 03h00, heure de Paris, dans `k8s/base/09-backup-cronjob.yaml` (`0fba9d2`) : `pg_dump` vers un volume dédié de 2 Gi, rotation sur les 7 sauvegardes les plus récentes, mot de passe transmis par `PGPASSWORD` et jamais en argument de commande. Éprouvé dans les deux sens sur le cluster réel : une sauvegarde déclenchée à la main, puis restaurée dans une base de vérification temporaire avec `ON_ERROR_STOP=1`, base supprimée ensuite. La base de production n'a pas été touchée par ce test.

---

## 3. Décisions prises en cours de route

### Une base Kustomize et deux surcouches, plutôt que des manifestes dupliqués

Quatre valeurs seulement diffèrent entre le poste et la production : l'image, les hôtes autorisés, l'hôte de l'Ingress et l'autorité qui signe le certificat. Les modifier à la main au moment du déploiement aurait reproduit le défaut que l'ADR-001 reprochait à `bootstrap.sh` : un écart non consigné entre ce que le dépôt décrit et ce qui tourne.

Les manifestes sont donc devenus une base et deux surcouches (`0aa7334`). La base ne contient aucune valeur propre à un environnement : l'image n'y porte pas d'étiquette et l'hôte de l'Ingress est le substitut `dilane-shop.example`, un TLD réservé qui ne résout jamais.

**La surcouche locale a été prouvée équivalente à l'existant, pas supposée telle.** Les anciens manifestes et la surcouche ont été construits de la même façon, puis les deux sorties comparées : elles ne diffèrent en rien. La vérification a été refaite à la rédaction de cette rétrospective, sur le commit `0aa7334`, avec le même résultat. C'est ce qui permet d'affirmer que la réorganisation n'a rien changé au comportement local.

### L'image figée sur l'empreinte du commit, non sur `latest`

La surcouche de production référence l'image par l'empreinte du commit qui l'a produite. La version en service est donc lisible dans le dépôt, et revenir en arrière consiste à remettre l'empreinte précédente. `imagePullPolicy` repasse à `IfNotPresent`, une empreinte désignant un contenu immuable — là où `latest` obligeait à `Always`.

### Les secrets restent déchiffrés sur le portable

La clé privée age n'est jamais installée sur le serveur. Les secrets sont déchiffrés localement et transmis à `kubectl` à travers le tunnel SSH :

```bash
sops --decrypt k8s/overlays/production/secrets.sops.yaml | ssh dilane-shop "kubectl apply -f -"
```

Rien n'est écrit en clair, ni sur le portable ni sur le serveur. Un serveur compromis livrerait les secrets de son cluster — ils y sont de toute façon, encodés en base64 — mais pas la clé qui déchiffre tous les secrets du dépôt, présents et passés. Installer la clé sur le serveur aurait échangé cette garantie contre une commande plus courte.

Les secrets sont par ailleurs séparés par environnement, en cohérence avec la structure Kustomize : le fichier de production porte de vraies clés Stripe de test et un mot de passe de base distinct de celui du poste.

### Fermer l'API Kubernetes avec iptables, pas avec ufw

k3s expose son API (6443) et le kubelet (10250) sur toutes les interfaces, donc sur Internet. Le cluster étant piloté depuis le serveur ou par SSH, ces ports n'ont aucune raison d'être joignables de l'extérieur. Deux règles `iptables` les bloquent sur la seule interface publique, sans toucher au trafic interne de k3s ni à SSH, rendues permanentes par `iptables-persistent` (`0203202`).

`ufw` a été écarté : il entre en conflit avec le réseau de k3s. Vérifié depuis l'extérieur après rechargement des règles, et de nouveau à la rédaction : 6443 et 10250 injoignables, 22, 80 et 443 en écoute, site et point de santé opérationnels.

### Une procédure de reprise, écrite pendant l'installation

`docs/deploiement-production.md` (`1db904d`) décrit les dix étapes du serveur nu au site en HTTPS, chaque bloc marqué PORTABLE ou SERVEUR. Sa raison d'être est précise : consigner les réglages qui n'existent nulle part ailleurs et seraient perdus avec le VPS, au premier rang desquels le correctif `hostPort` de la section 5.

---

## 4. Ce qui a surpris

### Azure for Students ne permettait aucune machine économique

Le plan tenait depuis l'ADR-002 : une VM **B2pts v2**, couverte par les 750 heures mensuelles de l'offre étudiante pendant 12 mois. Il supposait que cette taille soit disponible.

Le compte impose une **politique de régions limitée à cinq régions** — Espagne, Allemagne, Suisse, Pologne, Émirats — et aucune ne proposait la VM ARM gratuite, ni aucune taille de série B économique. Les tailles réellement disponibles y coûtaient environ 60 USD par mois, soit le crédit de 100 USD épuisé en six semaines : exactement le calcul qui avait fait écarter AKS dans l'ADR-002, appliqué cette fois à la machine elle-même.

Le déploiement s'est fait sur un VPS OVH, environ 5 € par mois, données en France, en `amd64`. Cette architecture a d'ailleurs simplifié la chaîne : l'obligation de construire l'image en `arm64`, inscrite dans les critères de l'issue #40, devient sans objet, et l'image publiée par la CI depuis un exécuteur `amd64` convient directement. Le crédit Azure est réservé aux exercices de la certification. Les deux ADR touchées ont reçu un addendum daté plutôt qu'une réécriture.

Ce qui surprend n'est pas qu'une offre gratuite ait des limites, mais que la contrainte décisive — la politique de régions — n'apparaisse qu'au moment de créer la machine, après avoir été inscrite dans une décision d'architecture trois sprints plus tôt.

### Trois vérifications qui semblaient concluantes sans l'être

La journée d'exploration d'Azure a produit trois faux positifs, chacun d'une nature différente. Ils sont notés ici parce qu'ils se ressemblent : dans les trois cas, une commande a renvoyé un résultat lisible, et ce résultat ne répondait pas à la question posée.

- **Une taille de machine « présente » mais inutilisable.** La liste des tailles d'une région contenait bien la taille visée. Elle y figurait comme existante, alors qu'elle était marquée indisponible pour cet abonnement. Lister ce qu'une région propose et vérifier ce qu'un abonnement peut y créer sont deux questions distinctes.
- **Une option de simulation qui n'existait pas.** Un essai devait valider une création sans rien créer, au moyen d'une option `--what-if` supposée s'appliquer à cette commande. Elle ne s'y applique pas. Le test paraissait passer, sans avoir rien éprouvé.
- **Un `grep -c` renvoyant 0 pour une raison d'indentation.** Le comptage portait sur un motif mal aligné dans un bloc YAML, et non sur l'absence de ce qui était cherché. Zéro a été lu comme « rien trouvé, donc rien à corriger », alors qu'il signifiait « la recherche n'a pas porté là où on croyait ».

Le Sprint 11 avait déjà relevé deux « fausses assurances venues d'une sortie mal lue », et la [Definition of Done](../definition-of-done.md) en a fait son critère 8. Ces trois cas en ajoutent une variante : une commande peut s'exécuter sans erreur, renvoyer une sortie plausible, et ne pas répondre à la question. Le critère 9 — éprouver un garde-fou dans les deux sens — est ce qui les aurait attrapés.

### Le durcissement SSH était masqué par un fichier de cloud-init

Le fichier `99-durcissement.conf` écrit dans `/etc/ssh/sshd_config.d/` posait `PasswordAuthentication no`. L'authentification par mot de passe restait pourtant acceptée.

La cause est l'ordre de lecture. `sshd_config` inclut `sshd_config.d/*.conf`, les fichiers sont lus par ordre alphabétique, et **la première valeur rencontrée pour une option l'emporte** — l'inverse de l'intuition, qui voudrait que le dernier fichier gagne. L'image Ubuntu d'OVH fournit `50-cloud-init.conf`, contenant `PasswordAuthentication yes` : lu avant le fichier `99`, il décidait. Le durcissement était écrit, versionné dans la procédure, et sans effet.

La correction a porté sur les deux fichiers. Surtout, la vérification a changé de nature : `sshd -T` affiche la configuration **effective**, après résolution de l'ordre, au lieu de relire les fichiers un par un en supposant leur priorité. Le contrôle final se fait depuis l'extérieur, en tentant une connexion par mot de passe, qui doit échouer.

### `fsGroup` n'est pas honoré par les volumes de k3s

Le CronJob de sauvegarde tourne en utilisateur non privilégié, 70, et écrit dans un volume. `fsGroup: 70` devait suffire : le kubelet donne alors le volume à ce groupe. L'écriture échouait en « Permission denied ».

`fsGroup` n'est appliqué que pour les types de volume qui déclarent le prendre en charge, et les PersistentVolumes de type `hostPath` — ce que produit `local-path`, la classe de stockage par défaut de k3s — n'en font pas partie. Le comportement dépend donc de la classe de stockage, pas du manifeste.

Plutôt que de parier sur un réglage dont l'effet varie, un conteneur d'initialisation s'exécute en `root` et donne le répertoire à l'utilisateur 70 avant que la sauvegarde ne démarre. `fsGroup` est conservé : inoffensif là où il est ignoré, utile là où il fonctionne. Le comportement a été constaté sur un volume neuf, et l'enchaînement corrigé vérifié de bout en bout contre un vrai PostgreSQL 17 : sauvegarde produite, puis restaurée dans une base vierge avec ses données intactes.

### Un `pg_dump` en échec pouvait passer pour une sauvegarde valide

Le script de sauvegarde envoie `pg_dump` vers `gzip` par un tube. Dans un tube, le code de sortie retenu est celui de la **dernière** commande : `gzip` réussit à compresser une entrée vide ou tronquée, et rapporte donc un succès, même quand `pg_dump` a échoué. Une sauvegarde inutilisable aurait été comptée comme réussie, et la rotation aurait fini par supprimer les bonnes.

`set -o pipefail` corrige ce point — vérifié disponible dans le shell BusyBox de l'image Alpine, ce qui n'allait pas de soi. Le fichier est de plus écrit sous un nom temporaire et renommé seulement en cas de succès : une exécution interrompue ne laisse pas de fichier d'apparence valide que la rotation compterait.

---

## 5. Le correctif `hostPort`, seul réglage non versionné

Il mérite une section : c'est la fragilité principale de l'installation, et le seul élément de la production qui n'existe nulle part dans le dépôt.

La variante `baremetal` d'ingress-nginx crée un Service de type **NodePort** et son Deployment ne déclare **aucun** `hostPort` : le contrôleur n'écoute que sur des ports de la plage 30000-32767. Rien n'écoute sur les ports 80 et 443 de l'interface publique. Ce manifeste suppose un équilibreur de charge externe, qui n'existe pas sur un VPS unique. Un correctif appliqué à la main attache les deux ports du nœud au pod du contrôleur.

Le symptôme de son absence est déroutant : tous les pods sont `Running`, le certificat est valide, et le site ne répond pas. Comme il est appliqué à une ressource installée depuis une URL externe, **il est perdu à chaque réinstallation ou mise à jour d'ingress-nginx**. La procédure de reprise le signale à deux endroits et donne la commande de contrôle.

C'est le premier candidat à l'automatisation, par exemple en le versionnant comme son équivalent local `k8s/overlays/local/07-ingress-controller-patch.yaml`, ou en passant par `ServiceLB`, l'équilibreur intégré de k3s — un changement de mécanisme, donc à éprouver.

---

## 6. Reporté

### Sauvegardes hors du serveur, et alerte en cas d'échec — #83, #48

Les sauvegardes sont écrites dans un volume fourni par `local-path`, donc **sur le disque du VPS**. Elles protègent d'une erreur logique — suppression involontaire, migration ratée — mais pas de la perte de la machine. Les sortir vers un stockage objet reste à faire.

Par ailleurs, un CronJob qui échoue est silencieux : `failedJobsHistoryLimit: 1` conserve le dernier échec pour consultation, rien ne le signale. La supervision est prévue au Sprint 14 (issue #48).

L'issue #83 a été fermée avec ces deux réserves écrites dans son dernier commentaire.

### Médias téléversés stockés dans les pods — #72

Le volume des médias suit le pod. Avec deux replicas, une image téléversée n'est visible que depuis le pod qui l'a reçue, et disparaît à sa recréation. Le catalogue actuel utilise des URL externes, ce qui masque le problème. Un stockage objet, ou un volume partagé, est nécessaire.

### Le webhook Stripe n'a jamais été exercé en conditions réelles

C'est la limite la plus notable de cette mise en production. L'audit relevait que le webhook ne pouvait être exercé depuis aucun des environnements, tous locaux. **Le déploiement public lève cet obstacle** : `https://dilane-shop.store/webhooks/stripe/` est joignable depuis Internet et les clés Stripe de test sont en place dans les secrets de production.

Restent à faire : déclarer l'URL dans le tableau de bord Stripe, effectuer un paiement complet, et vérifier que l'événement est reçu, que le stock est décrémenté et que l'email de confirmation part. Tant que ce n'est pas fait, le seul code qui touche au stock en production n'a jamais fonctionné en production. La redirection vers `checkout.stripe.com` autorisée par la politique de sécurité du contenu attend la même vérification.

### Le sous-domaine `www` n'est pas servi

L'enregistrement `CNAME` existe et résout vers le VPS, mais l'Ingress ne déclare que le domaine racine, le certificat ne couvre que ce nom, et `DJANGO_ALLOWED_HOSTS` ne contient pas `www.dilane-shop.store`. Un visiteur qui tape `www` obtient le certificat par défaut du contrôleur, donc un avertissement du navigateur. Trois issues possibles : l'ajouter partout, poser une redirection, ou retirer l'enregistrement DNS.

### Éléments hérités, toujours ouverts

| Issue | Élément | Origine |
|---|---|---|
| #49 | Découpage de `shop` en six apps, annoncé pour le Sprint 12 | ADR-003 |
| #39 | Chiffrement au repos du cluster, rotation des secrets | Sprint 12 |
| #86 | Versions des outils de sécurité de la CI non suivies par Dependabot | Sprint 12 |
| #67, #68, #69 | Webhook sous appels simultanés, survente masquée, taux de TVA invalide | Sprint 11 |
| #93, #94, #95 | `.coveragerc` dans l'image, test d'intrusion, détection dans les journaux | Sprint 12 |

---

## 7. État en fin de sprint

| Élément | État |
|---|---|
| Site | `https://dilane-shop.store` — HTTP `308` vers HTTPS, HTTPS `200` |
| Certificat | Let's Encrypt, reconnu par les navigateurs, valable jusqu'au 25/12/2026 |
| Point de santé | `{"status": "ok", "database": "reachable"}` |
| Hébergement | VPS OVH VPS-1, Ubuntu 24.04 `amd64`, k3s mono-nœud |
| Ports exposés | 22, 80, 443 ; API Kubernetes (6443) et kubelet (10250) fermés, vérifié de l'extérieur |
| Image déployée | `ghcr.io/wankamdypuedilane/dilane-shop`, figée sur l'empreinte d'un commit |
| Manifestes | Base Kustomize et deux surcouches ; les deux construisent |
| Secrets | Chiffrés par environnement ; clé age jamais présente sur le serveur |
| Sauvegarde | CronJob quotidien, 7 sauvegardes conservées, restauration éprouvée sur le cluster |
| Tests | 66, tous verts |
| Couverture, branches incluses | 75,2 %, seuil `fail_under` à 75 |
| CI | Verte sur les 7 commits du sprint ; 13 étapes, dont la publication de l'image |
| Déploiement | Manuel : `kubectl apply -k` sur le serveur, aucun workflow ne déploie |

---

## 8. Prochaines échéances

- **Sprint 14** — Supervision : Prometheus et Grafana (#44), instrumentation (#45), agrégation des journaux (#46), alertes sur indisponibilité et taux d'erreur (#48). C'est ce qui manque le plus à un site désormais public : aujourd'hui, une panne se constate en visitant le site.
- **Vérifier le paiement de bout en bout**, webhook compris, maintenant que le site est joignable depuis Internet.
- **Réduire ce qui reste manuel** : correctif `hostPort` versionné, installation des composants scriptée, déploiement automatisé (#43 a livré la publication de l'image, pas le déploiement).
- **Issues ouvertes** — #72, #83 pour ses deux réserves, #39, #49, #86, #93, #94, #95.
