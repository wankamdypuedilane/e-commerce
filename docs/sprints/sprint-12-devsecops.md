# Sprint 12 — DevSecOps

**Période :** 23/09/2026, 12h47 → 25/09/2026, 12h56
**Commits :** 21 sur `main`, dont 5 fusions de pull requests Dependabot (#74, #75, #76, #78, #79)
**Issues fermées :** #35, #36, #37, #38, #87 ; en marge de l'objectif : #70, #71, #84, #64, #62
**Issue avancée sans être fermée :** #39
**Issues ouvertes pendant le sprint :** #72, #81, #82, #83, #85, #86, #88, #89, #90, #91, #92
**Fichiers de tests produits :** `shop/test_acces_commandes.py`, `shop/test_medias.py`, `shop/test_image.py`, `shop/test_admin.py`, `shop/test_entetes.py`, `shop/test_navigateur.py`
**Document de décision :** [ADR-004 — Secrets chiffrés dans le dépôt avec SOPS et age](../adr/004-gestion-des-secrets.md)

---

## 1. Objectif du sprint

Sécuriser la chaîne avant le premier déploiement public : dépendances, code, image, en-têtes HTTP et secrets.

Au début du sprint, aucun de ces contrôles n'existait. Les dépendances étaient épinglées à des versions exactes, ce qui rend les constructions reproductibles mais n'apporte aucune correction de sécurité d'elle-même. Aucun outil n'analysait le code ni l'image. Les secrets du cluster étaient retapés à la main à chaque recréation.

Le Sprint 11 annonçait pour ce sprint le découpage de `shop` en six apps, conformément à l'[ADR-003](../adr/003-monolithe-modulaire.md). Ce découpage n'a pas été entamé : l'issue #49 reste ouverte.

---

## 2. Issues traitées

| # | Intitulé | Résultat |
|---|---|---|
| 35 | Scanner les dépendances dans la CI | **Fermée.** pip-audit en CI ; 30 failles connues corrigées d'abord. |
| 36 | Analyse statique du code Python | **Fermée.** Bandit en CI ; un constat, corrigé. |
| 37 | Scanner l'image Docker | **Fermée.** Trivy en CI ; pip retiré de l'image de production. |
| 38 | En-têtes de sécurité HTTP | **Fermée.** CSP appliquée, `Permissions-Policy` ajouté. |
| 87 | Supprimer le double chargement de jQuery | **Fermée.** Une seule version, sans faille connue. |
| 39 | Gestion des secrets hors base64 | **Ouverte, avancée.** ADR-004 et secrets chiffrés ; deux critères restent ouverts (section 6). |

Cinq autres issues ont été fermées pendant la période, en marge de l'objectif :

| # | Intitulé | Commit |
|---|---|---|
| 70 | Vérifier le propriétaire des commandes dans les vues de confirmation et de paiement | `dd2e594` |
| 71 | Le dossier des médias n'est pas inscriptible par l'application | `6bf7a60` |
| 84 | Le code de l'application est modifiable par le processus applicatif | `80278b6` |
| 64 | Exclure k8s du contexte de build Docker | `a9b7014` |
| 62 | Mettre à jour ARCHITECTURE.md et annoter l'audit | `cf4a610` |

### Détail

**#35 — Dépendances.** Le premier passage de pip-audit a relevé **30 failles connues** sur les dépendances épinglées : 17 sur Django 6.0.3, 13 sur Pillow 12.2.0. Elles ont été corrigées avant l'ajout de l'outil à la CI, en retenant le dernier correctif de chaque série, sans changement de version majeure (`35430e6`). pip-audit tourne ensuite en CI avant toute construction, sur `requirements-dev.txt` (`28fccf4`). Il n'a pas de niveaux de gravité : toute faille connue fait échouer la CI. Dependabot propose chaque semaine des mises à jour pour trois écosystèmes : `pip`, `docker` et `github-actions`. Le workflow se déclenche désormais aussi sur les pull requests, sans quoi les propositions de Dependabot n'auraient jamais été testées avant fusion.

**#36 — Analyse statique.** Bandit analyse `shop` et `ecommerce`, migrations et tests exclus, juste après pip-audit (`aebc26d`). Tout motif détecté fait échouer la CI, quelle que soit sa gravité. Son seul constat, `mark_safe` dans `shop/admin.py`, a été corrigé avant l'ajout de l'étape (`330c331`, section 3).

**#37 — Image.** Trivy analyse l'image de production juste après sa construction : paquets Debian et paquets Python, failles `HIGH` et `CRITICAL` disposant d'un correctif (`ee764a1`). Son premier passage a relevé deux failles, qui ont conduit à retirer pip de l'image (section 5).

**#38 — En-têtes HTTP.** Django envoyait déjà `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` et `Cross-Origin-Opener-Policy`. Deux en-têtes manquaient. La politique de sécurité du contenu utilise la prise en charge native de Django 6 ; elle a d'abord été déployée en mode Report-Only, pages parcourues une à une, puis appliquée (`f5b46ca`). Les scripts en ligne portent un jeton propre à chaque réponse. `Permissions-Policy` est posé par un intergiciel du projet, `shop/middleware.py`, que Django ne fournit pas. 6 tests, dont un qui vérifie le jeton sur quatre pages.

**#87 — jQuery.** Découverte en documentant #38 : `base.html` chargeait deux versions de jQuery (section 5). Une seule version 4.0 « slim » reste chargée (`6d8a526`). Un test vérifie qu'une seule version est chargée, et qu'elle n'est pas antérieure à 3.5.

**#39 — Secrets.** L'[ADR-004](../adr/004-gestion-des-secrets.md) retient SOPS avec une clé age : les secrets sont versionnés chiffrés dans `k8s/02-secrets.sops.yaml`, sans composant à installer dans le cluster, avec des binaires pour `amd64` et `arm64`. Seules les valeurs sous `data` et `stringData` sont chiffrées ; les noms des clés restent lisibles en revue (`24bab29`). `.gitignore` bloque les fichiers de secrets en clair, vérifié par `git check-ignore`. La clé privée age a été sauvegardée en deux exemplaires hors du poste ; la restauration a été vérifiée en déchiffrant avec une copie. La clé SMTP Brevo a été régénérée, dernier point laissé ouvert par l'issue #60. `k8s/02-secrets.example.yaml` est supprimé : le fichier chiffré liste déjà les noms des clés, et le README décrit les procédures.

---

## 3. Failles trouvées

| Faille | Trouvée par | Correction |
|---|---|---|
| 30 failles connues sur Django et Pillow | pip-audit, premier passage | `35430e6` : derniers correctifs des séries 6.0 et 12 |
| Lecture et annulation des commandes d'autres clients, par simple changement du numéro dans l'URL (dette 2.1 de l'audit) | Audit du 20/09 | `dd2e594`, #70 : connexion exigée et filtre par propriétaire ; la commande d'autrui répond 404, pas 403 |
| Injection de script stockée : un titre de produit contenant une balise `<script>` s'exécutait chez tout administrateur consultant une commande (dette 3.3) | Bandit, B308 et B703 | `330c331` : `format_html_join`, qui échappe chaque valeur insérée |
| Code de l'application modifiable par le processus qui l'exécute | Relecture de l'image, section 5 | `80278b6`, #84 : code copié en tant que `root` |
| jQuery 3.3 actif, affecté par CVE-2020-11022 et CVE-2020-11023 | Relecture de `base.html` | `6d8a526`, #87 |
| `msgpack` et `setuptools` vulnérables dans l'image | Trivy, premier passage | `ee764a1` : pip retiré de l'image de production |

Comme au Sprint 11, chaque correction a été accompagnée d'un test écrit avant elle et constaté rouge, ou d'une vérification dans les deux sens pour les outils de la CI : code 0 sur l'état corrigé, code 1 sur l'état d'avant.

Un défaut fonctionnel a aussi été corrigé : le dossier `/app/media`, absent de l'image, était créé par `root` au montage du volume Compose, et tout téléversement d'image depuis l'admin échouait (`6bf7a60`, #71). Il était passé inaperçu parce que les produits existants utilisent des URL d'images externes.

---

## 4. Décisions prises en cours de route

### Des seuils stricts, et des exceptions nominatives

Les trois outils échouent au premier constat : toute faille connue pour pip-audit, tout motif pour Bandit, toute faille grave ou critique corrigeable pour Trivy. Un seuil strict convient à un projet dont les dépendances épinglées avaient accumulé 30 failles sans alerte.

Aucune exception n'est accordée en masse. Un faux positif de Bandit se neutralise ligne par ligne, avec la règle nommée (`# nosec B703`) et une justification écrite ; une faille Trivy sans objet, identifiant par identifiant, dans un `.trivyignore` commenté. Aucune exception de ce type n'existe à la fin du sprint.

### Chaque garde-fou vérifié dans les deux sens

Chaque outil a été exécuté sur l'état corrigé et sur l'état d'avant, avec la commande exacte de la CI : pip-audit sur les versions d'avant la mise à jour, reprises dans l'historique Git ; Bandit sur `admin.py` d'avant la correction ; Trivy sur l'image de test, qui conserve pip ; le test du jeton CSP en retirant le jeton du script de la page de commande. C'est le critère 9 de la [Definition of Done](../definition-of-done.md).

### Des outils dans des conteneurs jetables

pip-audit et Bandit s'exécutent dans un conteneur `python:3.13-slim` jetable, Trivy dans le conteneur `aquasec/trivy`. Aucun outil de sécurité n'entre dans l'image de production ni dans `requirements-dev.txt`. Contrepartie : leurs versions sont écrites en dur dans `ci.yml`, et Dependabot ne les suit pas (issue #86).

### Retirer pip plutôt qu'ignorer ses failles

Les deux failles signalées par Trivy auraient pu être ignorées : elles ne touchent pas l'application. pip a été désinstallé de l'image de production, du virtualenv comme du Python système : l'application n'installe jamais de paquet à l'exécution, et pip n'y offrirait qu'un outil d'installation à un attaquant. L'étape `test` du Dockerfile le conserve pour installer `coverage`.

### Deux propositions de Dependabot non fusionnées telles quelles

Dependabot a proposé gunicorn 26.2.0 (#77) et Django 6.1.1 (#80), toutes deux avec une CI verte. Aucune n'a été fusionnée telle quelle : chacune a été remplacée par un commit qui corrigeait ce que la CI ne voyait pas (`74552b6`, `53b03a8`, section 5). La proposition de passer à Python 3.14 (#73) a été refermée ; l'évaluation est suivie par l'issue #81.

### Une CSP appliquée, avec deux exceptions écrites

Les scripts sont verrouillés par jeton. Les styles autorisent `'unsafe-inline'` : les jetons ne s'appliquent pas aux attributs `style=`, et une injection de style est bien moins grave qu'une injection de script. `form-action` autorise `checkout.stripe.com` pour la redirection vers le paiement, **sans vérification en conditions réelles** : les clés Stripe locales sont des valeurs d'exemple. `Strict-Transport-Security` attend un certificat reconnu : il est reporté à l'issue #42, qui prévoit de l'activer une fois le certificat Let's Encrypt stable.

### Plus de numéros de correctif dans la documentation

Les mises à jour de la matinée du 23/09 avaient déjà rendu faux les numéros de version cités dans le README et dans ARCHITECTURE. La documentation ne donne plus que la série de chaque paquet et renvoie à `requirements.txt` comme source unique (`53b03a8`).

### Le workflow renommé, le déploiement EC2 retiré

Le workflow s'appelait encore « CI/CD Deploy EC2 » et portait un job de déploiement désactivé depuis le Sprint 9, affiché comme ignoré à chaque exécution. Il est renommé `CI`, fichier `ci.yml`, et le job est supprimé (`1d37f77`). Les cinq secrets EC2 du dépôt, dont la clé SSH privée du serveur, ont été supprimés : la CI n'utilise aucun secret.

---

## 5. Ce qui a surpris

### Une CI verte ne prouve que ce que les tests exécutent

Dependabot a proposé gunicorn 26.2.0 (#77) avec une CI verte. Le journal des modifications, lu de la série 24 à la série 26, ne signalait aucun changement incompatible avec la configuration du projet. Le vrai conteneur, démarré à la main, affichait pourtant une erreur à chaque démarrage : l'interface de contrôle apparue dans gunicorn 25.1 tentait de créer son socket dans `/app`, non inscriptible. La CI ne pouvait pas la voir : les tests passent par le client de test de Django et ne lancent jamais gunicorn. L'interface est désactivée par `--no-control-socket`, option qui n'existe pas dans gunicorn 23 : les deux changements devaient donc être livrés ensemble, et non en fusionnant #77 tel quel (`74552b6`).

Même constat pour Django 6.1.1 (#80), une version de fonctionnalités : les notes de version ont été lues en entier avant tout le reste. Trois points touchaient le projet. La mise en page des formulaires de l'admin a changé, sans effet sur les sept gabarits d'admin surchargés, ce qu'a confirmé une vérification visuelle. Les réglages `EMAIL_*` utilisés pour Brevo sont dépréciés au profit de `MAILERS`, avec six avertissements suivis par l'issue #82. La commande `check` accède désormais aux bases de données. La combinaison effectivement livrée, Django 6.1 avec gunicorn 26, a été démarrée dans le vrai conteneur (`53b03a8`).

D'où une nouvelle étape de CI, le **test de fumée** : elle démarre le conteneur de production, attend `/healthz/` et échoue si les journaux de démarrage contiennent une erreur. Elle aurait détecté le défaut de gunicorn.

### Une affirmation fausse sur `/app`, répétée dans six endroits

Au Sprint 11, `coverage` n'avait pas pu écrire son fichier de mesures à la racine de `/app`. Il en a été conclu que `/app` appartenait à `root` et que le code n'était pas modifiable par l'utilisateur `django`. Cette conclusion s'est ensuite propagée :

| Endroit | Ce qui était écrit | Exact ? |
|---|---|---|
| Message de `215bac9` | `/app` appartient à `root` et reste non inscriptible, « une propriété à conserver » | Vrai pour le répertoire seul |
| Commentaire de `.coveragerc` | même affirmation | Vrai pour le répertoire seul |
| Rétrospective du Sprint 11 | « un processus compromis ne peut pas modifier le code qu'il exécute » | **Faux** |
| Message de `6bf7a60` | le code de l'application reste en lecture seule | **Faux** |
| Commentaire du Dockerfile, dossier des médias | « le seul emplacement de `/app` inscriptible » | **Faux** |
| Message de `74552b6` et commentaire de l'option gunicorn | `/app` volontairement non inscriptible | Vrai pour le répertoire seul |

En réalité, seul le répertoire `/app` lui-même appartenait à `root`. `COPY --chown=django:django . .` donnait à `django` tous les fichiers copiés : `manage.py`, `shop/`, `ecommerce/`… Le processus applicatif pouvait réécrire ses vues et sa configuration. L'erreur a été relevée pendant la synchronisation de la documentation, en tentant d'écrire, dans l'image et sous l'utilisateur `django`, dans `/app/shop` et dans `manage.py` : les deux écritures ont réussi. Le code est désormais copié en tant que `root`, et deux tests de `shop/test_image.py` vérifient, fichier par fichier et dossier par dossier, qu'il reste lisible et non modifiable (`80278b6`, #84).

Deux documents disaient pourtant l'inverse depuis le 20/09 : l'ADR-001 et le statut de la dette 1.3 de l'audit indiquaient que les fichiers appartenaient à `django`. La contradiction n'avait pas été relevée. Une vérification ponctuelle, un seul `touch` refusé à la racine, avait suffi à fonder une propriété de sécurité qui n'existait pas. Un erratum a été ajouté à la rétrospective du Sprint 11 et à l'ADR-001.

### `ls` sans `-A` masque les fichiers cachés

Après l'exclusion de `k8s/`, `Dockerfile`, `docker-compose.yml` et `.github/` du contexte de construction (`a9b7014`, #64), le message du commit affirme que `/app` ne contient plus que l'application, ses gabarits, ses fichiers statiques et ses médias. La vérification avait été faite avec `ls`, qui n'affiche pas les fichiers dont le nom commence par un point. `.coveragerc`, `.env.example` et `.dockerignore` étaient toujours dans l'image. Les deux derniers en ont été exclus (`cf4a610`). `.coveragerc` y reste, pour l'étape `test`.

### jQuery chargé deux fois, la version active étant vulnérable

`base.html` chargeait jQuery 4.0.0, puis jQuery 3.3.1 « slim ». La seconde remplaçait la première : la version réellement active était la 3.3, affectée par CVE-2020-11022 et CVE-2020-11023. Aucun outil de la CI ne pouvait le voir : pip-audit analyse les dépendances Python et Trivy l'image du serveur, alors que cette bibliothèque est téléchargée par le navigateur depuis un CDN. Le défaut a été trouvé en relisant `base.html` pour documenter les domaines autorisés par la CSP (#87). Un test couvre désormais ce que les scanners ne voient pas (`shop/test_navigateur.py`).

### Les failles signalées par Trivy venaient de pip lui-même

Au premier passage de Trivy, deux failles `HIGH` : `msgpack` et `setuptools`. Aucune n'est une dépendance de l'application. Toutes deux n'existaient dans l'image que sous forme de copies embarquées par pip, dans `pip/_vendor`, une fois dans le virtualenv et une fois dans le Python système. L'application n'installant jamais de paquet à l'exécution, pip a été retiré de l'image de production plutôt que ses failles ignorées (`ee764a1`). L'image de test, qui conserve pip, produit toujours ces deux failles : c'est elle qui sert à vérifier que Trivy échoue.

### Un `.trivyignore` n'aurait pas été lu

La première version de l'étape Trivy ne montait pas le dépôt dans le conteneur et s'exécutait depuis sa racine `/`. Un fichier `.trivyignore` placé dans le dépôt n'aurait donc jamais été lu : la règle des exceptions, écrite dans la documentation, n'aurait eu aucun effet. Vérifié avec un fichier d'essai, ignoré sans le montage et pris en compte avec lui. L'étape monte désormais le dépôt, comme pour pip-audit et Bandit. Aucune exception n'existant, rien n'était cassé ; la première aurait simplement été ignorée sans message.

---

## 6. Reporté

### Gestion des secrets — #39, partiellement

Faits : ADR-004, secrets chiffrés versionnés, clé sauvegardée et restauration vérifiée, procédures documentées. Restent ouverts :

- **le chiffrement au repos du cluster**, complémentaire de SOPS : une fois appliqués, les secrets redeviennent un Secret Kubernetes encodé en base64. À traiter avec k3s (#41) ;
- **la rotation des secrets**, pour laquelle aucune procédure n'est définie ;
- **l'application réelle à un cluster**, jamais exercée : aucun cluster n'est actif ;
- **les valeurs Stripe**, encore des marqueurs à renseigner au déploiement.

L'issue #39 mentionne un module Vault de la certification. SOPS ne le couvre pas : un exercice Vault distinct, hors du projet, est suivi par l'issue #92.

### Évaluer Semgrep — #85

Bandit ne couvre que quelques motifs propres à Django. Semgrep propose des règles Django plus larges, par exemple sur `csrf_exempt` ou sur `DEBUG` activé. L'issue demande de le lancer en local, de comparer ses résultats à ceux de Bandit, puis de décider : ajout à la CI, remplacement de Bandit, ou abandon.

### Versions des outils de sécurité non suivies — #86

Trivy, pip-audit, Bandit et l'image `python:3.13-slim` de leurs étapes sont épinglés dans les commandes de `ci.yml`. Dependabot ne lit que le Dockerfile, les fichiers `requirements` et les `uses:` des actions : ces outils vieilliront sans alerte.

### Collecte des violations de la CSP — #88

La politique ne déclare ni `report-uri` ni `report-to`. Une violation chez un visiteur, par exemple un script bloqué qui empêche une commande, ne laisse aucune trace côté serveur.

### Exception `'unsafe-inline'` sur les styles — #89

Six attributs `style=` dans les gabarits imposent cette exception. Les déplacer dans une feuille de style permettrait de la retirer.

### Saisie automatique du formulaire de commande — #90

Les champs d'adresse, de ville, de code postal et de pays n'ont pas d'attribut `autocomplete`. Signalé par l'onglet Issues des outils de développement de Chrome.

### Noms d'affichage des modèles — #91

L'administration affiche « Products » et « Order items » en anglais, à côté de « Catégories » et « Commandes ». `Product` et `OrderItem` n'ont ni `verbose_name` ni `verbose_name_plural`.

### Éléments hérités, toujours ouverts

| Issue ou dette | Élément | Origine |
|---|---|---|
| #49 | Découpage de `shop` en six apps, annoncé pour ce sprint | ADR-003 |
| #83, dette 2.5 | Aucune sauvegarde de la base | Sprint 7 |
| #72 | Médias téléversés stockés dans les pods | Sprint 12, à la suite de #71 |
| #82 | Réglages `EMAIL_*` dépréciés par Django 6.1 | Sprint 12 |
| #67, #68, #69 | Webhook sous appels simultanés, survente masquée, taux de TVA invalide | Sprint 11 |

---

## 7. État en fin de sprint

| Élément | État |
|---|---|
| Tests | 66 (46 au départ), tous verts |
| Couverture, branches incluses | 75,2 % au 24/09, selon `.coveragerc` (69,9 % au départ) |
| Seuil `fail_under` | 75 (69 au départ) |
| Contrôles de la CI | 8 : pip-audit, Bandit, construction, Trivy, `check`, tests et couverture, `check --deploy`, test de fumée |
| CI | Verte sur les 21 commits du sprint poussés sur `main` |
| Dépendances Python | Aucune faille connue selon pip-audit |
| Image de production | 235 Mo, sans pip, aucune faille `HIGH` ou `CRITICAL` corrigeable selon Trivy ; code non modifiable par l'utilisateur `django` |
| En-têtes HTTP | CSP appliquée et `Permissions-Policy` ; HSTS reporté (#42) |
| Secrets du cluster | Versionnés chiffrés par SOPS ; jamais appliqués à un cluster |
| Workflow | `CI`, sans job de déploiement ni secret |

---

## 8. Prochaines échéances

- **Sprint 13** — Premier déploiement public : VM Azure B2pts v2 en ARM64 (#40), k3s (#41), domaine et certificat Let's Encrypt (#42), publication de l'image dans un registre depuis la CI (#43). Premier usage réel des secrets chiffrés, et chiffrement au repos du cluster (#39).
- **Découpage en apps** — #49, sans sprint attribué. Relever d'abord la couverture de `shop/views.py`, comme le prévoyait le Sprint 11.
- **Issues ouvertes** — #85, #86, #88, #89, #90, #91, #92.
