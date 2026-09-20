# ADR-003 — Monolithe modulaire plutôt que microservices

## Statut

Accepté — 20/09/2026. Décision actée ; implémentation prévue au **Sprint 12**, après la mise en place des tests du Sprint 11. Issue #14.

---

## Contexte

La question de l'architecture applicative se pose maintenant, avant le travail Kubernetes du Sprint 10, parce que le choix conditionne le nombre d'images à construire, de pipelines à maintenir et de bases à administrer.

### Situation de l'équipe et de la charge

- **Un seul développeur.** Aucune répartition du travail entre équipes ne justifie de séparer le code en unités déployables indépendamment.
- **Aucune contrainte de charge.** L'application sert un catalogue de 25 produits et 5 catégories (`fixtures/demo-catalogue.json`). Il n'existe pas de composant dont le profil de charge diverge au point d'exiger une montée en charge séparée.
- **Un souhait d'évolutivité exprimé.** Le projet doit pouvoir accueillir de nouvelles fonctionnalités sans que chaque ajout augmente le coût du suivant.
- **Une API REST et une application mobile sont envisagées.** Elles devront exposer le catalogue, le panier et les commandes à un client qui n'est pas un navigateur rendant des gabarits Django.

### Situation du code

L'app `shop` porte aujourd'hui la totalité du domaine : catalogue, commandes, paiement Stripe, emails transactionnels et authentification par email. `docs/ARCHITECTURE.md` constate l'absence de découpage en sous-apps.

Le code n'est pas pour autant sans structure. Le commit `bab2c4c` a extrait `shop/services.py`, qui regroupe huit fonctions sans dépendance à HTTP : `stripe_is_configured`, `get_tax_rate_percent`, `calculate_tax_totals`, `build_order_items_payload`, `send_order_confirmation_email`, `build_stripe_line_items`, `create_stripe_checkout_session`, `sync_commande_payment_from_stripe`. Les vues orchestrent la requête ; le module de services porte les règles.

Cette séparation est le point d'appui de la décision : elle montre que les frontières fonctionnelles existent déjà en pratique, sans être matérialisées par des modules distincts.

---

## Décision

Conserver un **monolithe modulaire** : un seul dépôt, une seule image, une seule base de données, un seul cycle de déploiement — mais un découpage interne en apps Django aux frontières explicites.

### Découpage cible

Six apps remplaceront l'app `shop` unique :

| App | Périmètre |
|---|---|
| `catalog` | Catégories, produits, stock, recherche. Modèles `Category` et `Product`. |
| `cart` | Panier. Aujourd'hui entièrement côté navigateur, en `localStorage` ; l'app accueillera sa contrepartie serveur lorsque l'API REST l'exigera. |
| `orders` | Commandes et lignes de commande. Modèles `Commande` et `OrderItem`, règles de validation du checkout. |
| `payments` | Intégration Stripe : création de session, webhook, synchronisation des statuts de paiement. |
| `accounts` | Inscription, authentification par email ou identifiant, réinitialisation de mot de passe. Contenu actuel de `forms.py` et `backends.py`. |
| `notifications` | Emails transactionnels et leurs gabarits. |

### Règle de frontière

Les apps ne s'appellent pas par accès direct aux modèles ou aux gestionnaires d'une autre app. Chaque app expose un module `services.py` dont les fonctions constituent son contrat ; les autres apps n'utilisent que ces fonctions.

Concrètement : `payments` ne modifie pas `Commande.stock_deducted` en manipulant l'ORM d'`orders`, mais appelle une fonction de service exposée par `orders`. Les importations croisées de modèles sont proscrites en dehors des clés étrangères déclarées.

Cette règle est ce qui distingue un monolithe modulaire d'un monolithe ordinaire : elle rend le couplage visible dans les signatures de fonctions plutôt que diffus dans les requêtes.

### Rapport avec l'API REST envisagée

Les fonctions de service ne dépendent pas du protocole. Une vue Django et un point d'entrée d'API REST peuvent appeler la même fonction. L'ajout ultérieur d'une couche API consistera donc à écrire des sérialiseurs et des routes au-dessus des services existants, sans réécrire les règles métier — et sans que l'application mobile impose un choix d'architecture différent du site web.

---

## Alternatives considérées

### Microservices

Découper le domaine en services déployés indépendamment — typiquement un service catalogue, un service commandes, un service paiement — chacun avec sa base, son image, son pipeline et son cycle de publication.

**Écartée.** Le coût est réel et immédiat ; le bénéfice supposerait des contraintes que le projet n'a pas.

**Transactions distribuées.** C'est le point décisif. La cohérence entre le stock et le paiement repose aujourd'hui sur des garanties que donne une base unique. La vue `checkout` ouvre un `transaction.atomic()`, verrouille les produits avec `select_for_update()`, vérifie le stock, crée la commande et ses lignes. Le webhook Stripe décrémente le stock dans une transaction qui verrouille à la fois la commande et chaque produit, sous le contrôle du drapeau `stock_deducted`.

Si `catalog` et `orders` étaient deux services avec deux bases, ces garanties disparaîtraient. Il faudrait les reconstruire applicativement : réservation de stock en deux phases, compensation en cas d'échec de paiement, gestion de l'arrivée d'un webhook avant la fin de la transaction de commande, et traitement des cas où la compensation elle-même échoue. Un verrou de ligne posé par la base serait remplacé par un protocole distribué à écrire, à tester et à déboguer.

**Traçage distribué.** Une commande traverserait trois services. Diagnostiquer un échec de paiement supposerait de corréler des journaux issus de trois sources : identifiants de corrélation propagés de bout en bout, collecteur, interface de consultation. Aujourd'hui, une commande produit une trace unique dans un seul processus.

**Plusieurs pipelines.** Chaque service exige sa propre construction, ses tests, sa publication d'image et son déploiement. Le Sprint 9 a montré qu'un pipeline unique demandait déjà une attention réelle : le job de déploiement EC2 échouait à chaque poussée et a dû être neutralisé (issue #23). Multiplier les pipelines par trois avec un seul développeur multiplierait cette charge.

**Plusieurs bases.** Trois instances PostgreSQL à provisionner, sauvegarder, restaurer, mettre à jour et surveiller, alors que les procédures de sauvegarde existantes ne sont pas encore fiabilisées.

**Coût d'hébergement multiplié.** Chaque service demande au minimum un pod et une base. Le coût d'infrastructure suit le nombre de services, non le trafic — qui, lui, ne le justifie pas.

**Principe retenu : *monolith first*.** Formulé par Martin Fowler, il énonce que les frontières d'un système ne sont pas connues avec certitude avant de l'avoir construit et exploité, et qu'un découpage en microservices décidé trop tôt fige de mauvaises frontières, plus coûteuses à corriger qu'un monolithe bien structuré. La démarche recommandée consiste à construire d'abord un monolithe, à observer où les frontières apparaissent réellement, puis à extraire si le besoin se manifeste. Le découpage en six apps décrit ci-dessus est précisément la préparation de cette extraction éventuelle : il place les frontières là où elles semblent être, sans en payer le coût distribué tant que rien ne l'impose.

### Statu quo — conserver l'app `shop` unique

**Écartée**, mais sans urgence. L'app unique fonctionne. Son défaut est qu'aucune frontière n'y est vérifiable : rien n'empêche une vue de paiement de modifier directement un produit. Plus le code grossit, plus l'extraction ultérieure devient coûteuse. Le découpage est donc engagé maintenant, tant que le volume reste faible.

---

## Critères de révision

Cette décision sera réexaminée si l'une des conditions suivantes est constatée — pas avant, et aucune n'est remplie aujourd'hui :

1. **Plusieurs équipes travaillent sur le produit.** Lorsque des personnes distinctes se gênent sur le même dépôt, le coût de coordination peut dépasser le coût distribué. C'est la justification historique des microservices, et elle est organisationnelle avant d'être technique.

2. **Les besoins de scalabilité divergent.** Si un composant identifié — par exemple la recherche de produits, ou le traitement des webhooks — exige une montée en charge propre alors que le reste de l'application reste stable, l'extraire devient défendable. Tant que tout monte en charge ensemble, répliquer le monolithe suffit.

3. **Les cycles de publication deviennent incompatibles.** Si une partie du domaine doit être publiée plusieurs fois par jour pendant qu'une autre exige une validation longue, le déploiement unique devient contraignant.

La révision portera alors sur un périmètre précis, pas sur l'architecture entière : l'extraction se fera app par app, en commençant par celle dont la frontière aura le moins d'appels de service entrants.

---

## Conséquences

### Positives

- Une base unique : les garanties transactionnelles sur le couple stock/paiement sont conservées telles quelles.
- Une image, un pipeline, un déploiement — cohérent avec l'[ADR-001](001-conteneurisation.md).
- Les frontières deviennent explicites et vérifiables par relecture, ce qui prépare une extraction ultérieure sans l'imposer.
- L'API REST et l'application mobile pourront réutiliser les fonctions de service sans duplication des règles métier.

### Négatives

- Le découpage est une contrainte de discipline, non une contrainte technique : rien dans Django n'empêche d'importer le modèle d'une autre app. Le respect des frontières repose sur la relecture.
- L'opération touche les imports, les migrations (`migrations.SeparateDatabaseAndState` sera nécessaire pour déplacer les modèles sans recréer les tables) et les chemins de gabarits. Elle représente un travail de refactorisation à risque sur un code aujourd'hui couvert par 9 tests seulement.
- C'est la raison pour laquelle l'implémentation est placée au **Sprint 12, après le Sprint 11 consacré aux tests** : déplacer des modèles entre apps sans filet de tests exposerait à des régressions silencieuses, notamment sur le webhook Stripe, qui n'est aujourd'hui couvert par aucun test.

---

## Liens

- Issue #14 — ADR-003 : monolithe modulaire plutôt que microservices
- [ADR-001 — Conteneurisation de l'application](001-conteneurisation.md)
- ADR-002 — Kubernetes plutôt qu'un serveur unique : à rédiger, issue #22, Sprint 10
- [docs/ARCHITECTURE.md](../ARCHITECTURE.md) — état actuel du découpage
- [docs/AUDIT.md](../AUDIT.md) — couverture de tests constatée
- Martin Fowler, *MonolithFirst* (2015) — <https://martinfowler.com/bliki/MonolithFirst.html>
