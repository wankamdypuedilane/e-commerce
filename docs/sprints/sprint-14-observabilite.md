# Sprint 14 — Observabilité

**Période :** 27/09/2026, 12h47 → 28/09/2026, 02h28
**Commits :** 9 sur `main` (`5df4ad5`, `4adb8e6`, `6d4fd09`, `d9b54e0`, `d2a7a04`, `4b1168a`, `f153d51`, `7ea679b`, `44373af`)
**Issues fermées :** #45, #44, #48
**Issues non traitées :** #46 (journaux), #47 (traçage)
**Issue ouverte pendant le sprint :** #98
**Pull requests :** #97, #99, #100, #101 fusionnées ; #102 fermée sans fusion
**Document produit :** `docs/observabilite.md`
**Manifestes produits :** `k8s/overlays/production/observabilite/`, `k8s/overlays/production/patch-django-metriques.yaml`
**Script produit :** `scripts/k6/catalogue.js`

---

## 1. Objectif du sprint

Observer l'application en production.

Le Sprint 13 avait mis le site en ligne, sans aucun moyen de savoir comment il se portait : une panne se constatait en visitant le site. L'objectif retenu a été de mesurer les quatre signaux d'or — latence, trafic, erreurs, saturation — de les visualiser, et d'être prévenu par courriel quand le site tombe ou se dégrade.

La contrainte structurante était la mémoire : le VPS dispose de 4 Go, environ 2,2 Go libres, et n'a pas de swap. Un dépassement ne ralentit pas le serveur, il déclenche le tueur de processus du noyau. La supervision ne devait jamais pouvoir étouffer Django ou PostgreSQL.

---

## 2. Issues traitées

| # | Intitulé | Résultat |
|---|---|---|
| 45 | Instrumenter Django avec les quatre signaux d'or | **Fermée** le 27/09. |
| 44 | Déployer Prometheus et Grafana sur le cluster | **Fermée** le 27/09. |
| 48 | Alertes sur indisponibilité et taux d'erreur | **Fermée** le 28/09. |
| 46 | Agréger les journaux du cluster | **Non traitée.** Reportée (section 6). |
| 47 | Traçage distribué avec OpenTelemetry | **Non traitée.** Écartée par décision (section 6). |

### Détail

**#45 — Les métriques** (`5df4ad5`). Django expose les quatre signaux d'or sur `/metrics`, au moyen de `prometheus-client` et d'un intergiciel écrit pour le projet (`shop/middleware.py`, `shop/metrics.py`). `django-prometheus` a été écarté : sa version stable exige `Django<6.1`, alors que le projet tourne en 6.1.1. Les métriques en reprennent les noms, pour qu'un passage ultérieur à cette bibliothèque ne demande pas de réécrire les tableaux de bord.

Les métriques sont étiquetées par **nom de route** Django, jamais par chemin demandé : étiqueter par chemin aurait créé une série par identifiant de produit et par URL inexistante visitée par un robot. Un test échoue si cette règle régresse.

`/metrics` n'est pas public : la vue répond 404 dès que la requête porte un en-tête de proxy (`X-Forwarded-For`, `X-Real-IP`, `Forwarded`), qu'ingress-nginx pose sur toute requête qu'il relaie. 404 plutôt que 403, comme pour les pages de commande (#70), pour ne pas confirmer l'existence de l'adresse. Vérifié en production : 200 depuis l'intérieur du cluster, 404 depuis Internet.

13 tests ajoutés, 79 au total. Couverture de 75,2 % à 76,9 %, seuil relevé à 76. L'image de production a été réalignée sur ce commit (`4adb8e6`).

**#44 — Prometheus et Grafana** (`d9b54e0`, `d2a7a04`). Prometheus v3.13.3 et Grafana 12.4.11, en manifestes écrits pour le projet dans l'espace de noms `observabilite`, sans kube-prometheus-stack. La pile ne concerne que la surcouche de production : la construction de la surcouche locale est restée identique octet pour octet.

- Prometheus découvre les **pods** Django (`kubernetes_sd_configs`, `role: pod`), restreint à l'espace de noms `dilane-shop` et au label `app.kubernetes.io/name=django`, avec consentement par annotation `prometheus.io/scrape`. Chaque replica est interrogé sur son IP : le Service répartirait les collectes entre les deux pods au hasard. Un `Role` en lecture seule sur les pods suffit, sans `ClusterRole`. Rétention de 7 jours, volume de 2 Gi.
- Grafana est entièrement provisionné depuis le dépôt : source de données, tableau de bord des quatre signaux d'or, compte administrateur lu dans un Secret chiffré par SOPS. Pas d'Ingress : l'accès passe par `kubectl port-forward` sur le serveur, relayé par un tunnel SSH jusqu'au portable.
- Relevé en production à la fermeture : deux cibles `up`, p95 d'environ 89 ms, 0 % d'erreur, environ 140 Mo de mémoire pour les deux composants, sous des limites strictes de 128 Mi et 192 Mi.

**#48 — Les alertes** (`4b1168a`, `f153d51`). Alertes par courriel, évaluées par Grafana et envoyées par son Alertmanager intégré : pas d'Alertmanager séparé. Coût mesuré : environ 3 Mo, aucun pod supplémentaire. Trois règles, provisionnées par fichier :

| Règle | Condition | Durée |
|---|---|---|
| Site injoignable | aucun pod Django collecté | 2 min |
| Taux d'erreur 5xx élevé | plus de 5 % de 5xx sur 5 min | 2 min |
| Latence p95 élevée | p95 au-delà de 1 s sur 5 min | 2 min |

Les deux dernières ne s'évaluent qu'à partir de 20 requêtes en 5 minutes : sans cette garde, une erreur sur deux requêtes nocturnes ferait 50 %, et l'absence de trafic donnerait une division par zéro. Les expressions ont été éprouvées par `promtool test rules` sur des séries synthétiques.

Envoi par le relais SMTP de Brevo, identifiants recopiés dans un Secret propre à l'espace de noms `observabilite` (`f153d51`), plutôt que d'ouvrir à Grafana le Secret applicatif, qui contient aussi les clés Stripe et le mot de passe de la base.

Ce qui a été vérifié, et où :
- **en production**, l'envoi : le courriel de test du point de contact a été reçu ;
- **dans un environnement de validation**, le cycle complet : Django arrêté, l'alerte « Site injoignable » est passée à *Firing*, un courriel est parti, puis un courriel *Resolved* au retour de Django.

Une panne réelle n'a pas été provoquée en production pour éprouver le cycle complet.

**Hors issue — le secret du webhook Stripe** (`6d4fd09`). La valeur de `STRIPE_WEBHOOK_SECRET` saisie le 27/09, lors de la configuration du webhook dans le tableau de bord Stripe, n'avait pas été reportée dans le dépôt. Le fichier chiffré de production a été resynchronisé ; les autres valeurs sont inchangées.

---

## 3. Décisions prises en cours de route

### Une pile légère plutôt que kube-prometheus-stack

kube-prometheus-stack surveille aussi le cluster, les nœuds et ses propres composants, et demande plusieurs centaines de mégaoctets. Seules les métriques applicatives étaient nécessaires. Les deux composants tiennent dans environ 140 Mo mesurés, avec des garde-fous :

- limites mémoire strictes, et `GOMEMLIMIT` pour que le ramasse-miettes de Go resserre avant le plafond ;
- `strategy: Recreate`, pour qu'une mise à jour ne fasse jamais coexister l'ancien et le nouveau pod ;
- une `PriorityClass` à -100 : en cas de manque de mémoire, Prometheus et Grafana cèdent avant Django et PostgreSQL.

### Tout provisionner, rien dans un volume

Grafana n'a pas de volume persistant : sa base SQLite vit dans un `emptyDir`, recréé à chaque démarrage. Source de données, tableau de bord, règles d'alerte, point de contact et politique sont donc décrits par des fichiers du dépôt, et non créés dans l'interface, où ils disparaîtraient au redémarrage. La source de vérité est le dépôt ; la contrepartie est qu'une modification faite dans l'interface est perdue.

### Des tests de charge bornés, faits pour observer, pas pour mesurer une limite

`scripts/k6/catalogue.js` (`7ea679b`, puis `44373af`) ne fait que des GET, sur le catalogue. Il n'accepte comme cible que la production ou une adresse locale explicite, exige `AUTORISER_CHARGE_PROD=oui` pour charger la production, et plafonne la charge à 8 utilisateurs virtuels. Son but est de produire assez de trafic pour lire les quatre signaux dans Grafana, sans risquer d'éprouver le VPS. La section 5 précise ce que ses résultats permettent de conclure.

---

## 4. Ce qui a surpris

### La collecte recevait 400, pas seulement la protection 404

La protection de `/metrics` avait été conçue en pensant au seul risque de 404 : une collecte qui passerait par l'Ingress en porterait les en-têtes de proxy. Collecter chaque pod directement sur son IP évitait ce piège.

Mais une requête adressée à l'IP d'un pod porte l'en-tête `Host: 10.42.x.x:8000`. Cette adresse ne figure pas dans `ALLOWED_HOSTS`, et Django rejette la requête en **400 `DisallowedHost`**, avant même d'atteindre la vue. Reproduit sous gunicorn avec la configuration de production. Prometheus refuse de surcharger l'en-tête `Host`, et l'IP d'un pod change à chaque redémarrage.

La parade tient dans la surcouche de production (`patch-django-metriques.yaml`). L'IP du pod est lue par l'API descendante (`POD_IP`, `status.podIP`), puis ajoutée à la liste existante : `DJANGO_ALLOWED_HOSTS: "$(DJANGO_ALLOWED_HOSTS),$(POD_IP)"`. Le kubelet résout la référence avec la valeur venue du ConfigMap, ce qui a été vérifié dans son code source, `makeEnvironmentVariables`. La liste des domaines reste définie à un seul endroit. Les deux cibles sont `up` en production.

La protection avait pourtant été vérifiée dans les deux sens, comme le demande le critère 9 de la [Definition of Done](../definition-of-done.md) : les tests montrent un accès interne autorisé et un accès par l'Ingress refusé. Mais ils passent par le client de test de Django, dont l'en-tête `Host` est toujours accepté. Le sens « laisse passer » était éprouvé, pas par le chemin qu'emprunte réellement la collecte.

### Des métriques fausses, et plausibles

Gunicorn lance 3 workers, chacun avec ses propres compteurs en mémoire. Sans réglage, un appel à `/metrics` ne rend que les compteurs du worker qui répond. Après 12 requêtes, les relevés successifs donnaient **3, 3, 4, 5** au lieu de 12.

Rien ne signalait l'erreur : chaque valeur était un nombre de requêtes crédible, le format était valide, et Prometheus l'aurait collecté sans broncher. Le défaut n'apparaît qu'en comparant un relevé à un trafic connu. Il n'a d'ailleurs été vu qu'en testant sous un vrai gunicorn : le serveur de développement de Django n'a qu'un processus.

Correction : `PROMETHEUS_MULTIPROC_DIR` sur un `emptyDir`, qui agrège les mesures des workers, soit 12, 12, 12. Un second défaut de même nature a suivi : les jauges étaient rendues une fois par identifiant de processus, corrigé par `multiprocess_mode="livesum"`.

### L'expéditeur non validé bloquait aussi les courriels de commande

Les premiers envois d'alerte ont échoué : l'expéditeur `contact@dilane-shop.store` n'était pas validé chez Brevo. Or c'est aussi l'adresse d'expédition de l'application. Les **courriels de confirmation de commande étaient donc bloqués de la même façon**, sans que rien ne le montre, parce que ce chemin n'avait jamais été exercé en production. La rétrospective du Sprint 13 le comptait parmi les vérifications restantes : « l'email de confirmation part ».

Le domaine a été authentifié chez Brevo ; c'est un réglage du compte, pas du dépôt. Un envoi depuis la production a ensuite été vérifié le 28/09, courriel reçu en boîte principale.

Une fonction de supervision a ainsi révélé une panne silencieuse d'une fonction métier.

### Un port-forward fantôme bloquait le tunnel

L'accès à Grafana passe par un double tunnel : `kubectl port-forward` sur le serveur, relayé par SSH. Un processus `kubectl port-forward` d'une session précédente, resté orphelin, bloquait l'ouverture du tunnel suivant. Il a fallu retrouver ce processus et l'arrêter. Le double tunnel a ce coût : quand il échoue, la cause peut se trouver à chacune de ses deux extrémités.

---

## 5. Les tests de charge : ce qu'ils disent, et ce qu'ils ne disent pas

Deux charges modérées ont été lancées contre la production, avec le mode `charge` de `catalogue.js`, plafonné à 8 utilisateurs virtuels. Résultat consigné à la fermeture de la PR #102 : environ 6 000 requêtes, sans erreur, avec un p95 vu du client inférieur à 75 ms.

Seule la première a été relevée en détail dans le dépôt (`docs/observabilite.md`) : 5 912 requêtes, 0 échec, p95 de 74,86 ms. Elle suivait l'ancien parcours du script, dont la recherche `item-name=livre` ne trouvait aucun produit : elle rendait une liste vide, moins coûteuse qu'une recherche fructueuse, et aucune fiche produit n'était ouverte. Le parcours a été corrigé ensuite (`44373af`) : accueil, recherche qui trouve un produit, fiche.

**Ces tests ne mesurent pas la capacité maximale du site.** Chaque utilisateur virtuel attend sa réponse avant d'envoyer la requête suivante : au plus 8 requêtes sont en cours à la fois, pour 6 workers gunicorn, et le débit baisse de lui-même si le site ralentit. Ils montrent que le site tient cette charge modérée. Ils ne disent pas où il cesserait de la tenir. Avec un p95 client sous 75 ms, loin du seuil d'une seconde, la règle d'alerte « Latence p95 élevée » n'avait pas de raison de se déclencher.

---

## 6. Reporté

### #47 — Traçage distribué : écarté, par décision

Le traçage distribué suit une requête à travers plusieurs services, en reliant les intervalles de temps que chacun enregistre. L'application est un monolithe modulaire, choix acté par l'[ADR-003](../adr/003-monolithe-modulaire.md) : une seule image, un seul processus par requête, une seule base. Il n'y a pas de frontière entre services à traverser, donc rien à relier.

L'issue évoquait la répartition du temps entre Django, PostgreSQL et l'API Stripe. C'est une question de profilage à l'intérieur d'un même processus, pas de traçage distribué : si elle se pose, une mesure dans Django y répond sans déployer de collecteur de traces.

Ce n'est donc pas une dette. La question se rouvrirait si l'architecture changeait, par exemple si un service était un jour extrait du monolithe. L'issue le rattachait à un module de la certification : ce module ne sera pas illustré par ce projet, faute d'objet réel. L'issue reste à fermer avec cette justification.

### #46 — Agrégation des journaux : reportée au sprint du test d'intrusion

Les journaux restent lisibles pod par pod (`kubectl logs`). Leur agrégation est reportée au sprint du test d'intrusion : la détection des attaques par l'équipe bleue (#95, prévue au Sprint 17) repose explicitement sur des journaux centralisés, et les deux travaux seront définis ensemble. La collecte des violations de la politique de sécurité du contenu (#88), dont #95 dépend aussi, suivra le même chemin.

### Le test de capacité — PR #102, fermée

Un test de capacité a été préparé, puis reporté : environnement séparé `capacite.dilane-shop.store` sur un second VPS de même gamme, script k6 à débit imposé et par paliers, garde-fous qui refusent de viser la production. La PR #102 a été fermée sans fusion le 28/09, par décision de ne pas engager un second VPS pour l'instant. Le travail est conservé sur sa branche, pour réutilisation. En l'état, la capacité maximale du site n'est pas mesurée, ce qui est acceptable pour l'usage actuel.

### Ajustements de la supervision

- **Échelles du tableau de bord** (#98, ouverte le 27/09) : le panneau des erreurs monte jusqu'à 10 000 % lors des pics transitoires à faible trafic ; à borner à 100 %.
- **Un second canal d'alerte** : le courriel est le seul canal. Si Brevo ou la boîte de réception est indisponible, l'alerte n'arrive pas, et rien ne le signale. Placé en attente.

### Éléments hérités, toujours ouverts

| Issue | Élément | Origine |
|---|---|---|
| #83 | Sauvegardes hors du serveur, alerte en cas d'échec de la sauvegarde | Sprint 13 |
| #72 | Médias téléversés stockés dans les pods | Sprint 13 |
| #49 | Découpage de `shop` en apps Django distinctes | ADR-003 |
| #39 | Gestion des secrets hors base64 | Sprint 12 |
| #86 | Versions des outils de sécurité suivies par Dependabot | Sprint 12 |
| #67, #68, #69 | Webhook sous appels simultanés, survente masquée, taux de TVA invalide | Sprint 11 |
| #93, #94, #95 | `.coveragerc` dans l'image, test d'intrusion, détection dans les journaux | Sprint 12 |

Les alertes de #48 surveillent Django, pas le CronJob de sauvegarde : l'échec d'une sauvegarde reste silencieux, et #83 conserve cette réserve.

---

## 7. État en fin de sprint

| Élément | État |
|---|---|
| Métriques | Quatre signaux d'or sur `/metrics`, agrégés entre les 3 workers ; 404 depuis Internet |
| Collecte | Prometheus v3.13.3, 2 cibles `up`, rétention 7 jours |
| Visualisation | Grafana 12.4.11, tableau de bord provisionné, accès par tunnel SSH uniquement |
| Mémoire de la supervision | Environ 140 Mo mesurés, limites 128 Mi et 192 Mi |
| Alertes | 3 règles, courriel par Brevo ; envoi vérifié en production, cycle complet vérifié hors production |
| Courriels de l'application | Expéditeur authentifié chez Brevo ; envoi de production vérifié le 28/09 |
| Charge | Environ 6 000 requêtes, 0 erreur, p95 client inférieur à 75 ms ; capacité maximale non mesurée |
| Image déployée | Figée sur `5df4ad5` |
| Tests | 79, tous verts |
| Couverture, branches incluses | 76,9 %, seuil `fail_under` à 76 |
| CI | Verte sur les 9 commits du sprint |
| Journaux | Lisibles pod par pod, non agrégés |

---

## 8. Prochaines échéances

- **Fermer #47** avec la décision de la section 6, en citant l'ADR-003.
- **Consigner le paiement de bout en bout** : un paiement complet en production, webhook et courriel de confirmation compris, n'est enregistré comme vérifié ni dans le dépôt ni dans les issues. Maintenant que les courriels peuvent partir, c'est la vérification que la rétrospective du Sprint 13 laissait ouverte.
- **Réduire ce qui reste manuel** : correctif `hostPort`, installation des composants, déploiement (point hérité du Sprint 13).
- **Sprint du test d'intrusion** : #94 et #95, avec l'agrégation des journaux (#46) et la collecte des violations CSP (#88).
- **Issues ouvertes** — #98, #83, #72, #39, #49, #86, #93.
