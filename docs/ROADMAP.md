# Feuille de route

Document de planification — état au 29/09/2026. Il unifie la séquence des sprints déjà décrite dans les rétrospectives (`docs/sprints/`) et la suite du plan. Il est **purement documentaire** : il ne crée ni ne modifie aucun jalon GitHub, aucune issue.

---

## 1. Deux niveaux de lecture

Le projet se lit à deux échelles distinctes, qu'il ne faut pas confondre :

- **Les jalons GitHub sont des versions produit.** Ils disent *ce que le produit sait faire*, pas *quand*. Trois jalons :

  | Version | Nom | Intention |
  |---|---|---|
  | v0.1 | MVP | Le socle : catalogue, panier, commande, paiement, déploiement. |
  | v0.2 | Fiabilisé | Le socle tient sous conditions réelles : bugs de commande corrigés, sauvegardes, hygiène. |
  | v1.0 | Boutique réelle | Vitrine présentable, API, sécurité éprouvée, prête pour du vrai trafic. |

  Le titre exact du jalon de fiabilisation dans GitHub est `v0.2 - Fiabilise`.

- **Les sprints sont une séquence d'exécution.** Ils disent *dans quel ordre* le travail est fait. Un sprint fait avancer une ou plusieurs versions produit, sans s'y superposer.

**Les Sprints 0 à 14 sont faits.** Leurs rétrospectives sont dans [`docs/sprints/`](sprints/) : conteneurisation (9), Kubernetes (10), tests (11), DevSecOps (12), déploiement (13), observabilité (14). Le site est en ligne sur `https://dilane-shop.store`.

---

## 2. Note de réconciliation plan / réalité

La planification initiale a divergé de ce qui a réellement été fait. Ce document acte la réalité plutôt que de réécrire l'histoire.

- **« Sprint 12 = découpage en apps » a été dépassé par la réalité.** L'[ADR-003](adr/003-monolithe-modulaire.md) annonçait le découpage de `shop` en apps distinctes pour le Sprint 12. Ce sprint, et les deux suivants, ont porté sur d'autres priorités devenues urgentes : DevSecOps (12), mise en production (13) et observabilité (14). Le découpage (**#49**) n'a pas été entamé ; il est **re-planifié au Sprint 16**.
- **Le pentest et l'équipe bleue ont glissé.** La documentation les situait vers les Sprints 16-17. Ils atterrissent aux **Sprints 19 (rouge) et 20 (bleue)**, une fois la vitrine, la modularisation et la correction des bugs faites.

---

## 3. Sprints 15 à 20

La colonne **Version** indique le cap produit que le sprint fait avancer ; c'est une intention de feuille de route, pas le jalon GitHub de chaque issue (les jalons ne sont pas modifiés ici). L'**effort** est une estimation (S = petit, M = moyen, L = important).

### Sprint 15 — Vitrine visible

Rendre la boutique présentable et corriger les finitions visibles avant d'ajouter des fonctionnalités.

| Issue | Intitulé court | Version | Effort |
|---|---|---|---|
| #55 | Pages d'erreur 404 et 500 personnalisées | v1.0 | S |
| #63 | Bootstrap Icons référencé mais jamais chargé | v1.0 | S |
| #90 | Attributs de saisie automatique sur le formulaire de commande | v1.0 | S |
| #91 | Noms d'affichage en français pour Product et OrderItem | v1.0 | S |
| #93 | Exclure `.coveragerc` de l'image de production | v0.2 | S |
| #98 | Raffiner les échelles du tableau de bord Grafana | v0.2 | S |

**Effort sprint : M** (beaucoup de petits éléments, aucun structurant).

### Sprint 16 — Modularisation & API

Le découpage reporté depuis le Sprint 12, puis l'API interne qu'il rend propre à exposer.

| Issue | Intitulé court | Version | Effort |
|---|---|---|---|
| #49 | Découper `shop` en apps Django distinctes ([ADR-003](adr/003-monolithe-modulaire.md)) | v1.0 | L |
| #50 | Nettoyer les templates morts et le JavaScript dupliqué | v0.2 | M |
| #56 | API REST interne avec Django REST Framework | v1.0 | L |

**Effort sprint : L** (refactorisation transverse, puis nouvelle couche API).

### Sprint 17 — IA vitrine

Une première fonctionnalité d'IA côté vitrine, sans engager d'infrastructure lourde.

| Issue | Intitulé court | Version | Effort |
|---|---|---|---|
| #57 | Génération de descriptions produits par IA | v1.0 | M |

**Stretch, renvoyés à l'[icebox](#5-icebox) :** #58 (recherche sémantique par embeddings) et #59 (recommandations de produits similaires) supposent une infrastructure d'embeddings ; ils ne sont pas engagés dans ce sprint.

**Effort sprint : M.**

### Sprint 18 — Correctness & hygiène

Corriger les bugs de commande restants et solder la dette d'hygiène.

| Issue | Intitulé court | Version | Effort |
|---|---|---|---|
| #51 | Compléter la machine à états des commandes | v0.2 | M |
| #52 | Unifier la gestion des images produits | v0.2 | M |
| #69 | Refuser un taux de TVA invalide au lieu de retomber sur 20 % | v0.2 | S |
| #65 | Purger `db.sqlite3` du poste de développement | v0.2 | S |
| #81 | Évaluer le passage à Python 3.14 | v0.2 | M |
| #82 | Migrer la configuration email vers `MAILERS` | v0.2 | S |
| #86 | Faire suivre les versions des outils de sécurité par Dependabot | v0.2 | S |

**Effort sprint : L** (grand nombre d'éléments, dont deux bugs métier).

### Sprint 19 — Sécurité offensive

Durcir, puis éprouver par un test d'intrusion.

| Issue | Intitulé court | Version | Effort |
|---|---|---|---|
| #39 | Gestion des secrets hors base64 | v1.0 | M |
| #85 | Évaluer Semgrep et ses règles Django | v1.0 | S |
| #89 | Retirer les attributs `style=` pour supprimer l'exception `unsafe-inline` | v1.0 | M |
| #94 | Test d'intrusion sur `dilane-shop.store` (équipe rouge) | v1.0 | L |

**Effort sprint : M** (durcissement, puis campagne offensive).

### Sprint 20 — Équipe bleue & logs

Détecter les attaques du Sprint 19, ce qui suppose d'abord des journaux exploitables.

| Issue | Intitulé court | Version | Effort |
|---|---|---|---|
| #46 | Agréger les journaux du cluster | v1.0 | L |
| #88 | Collecter les violations de la politique de sécurité du contenu | v1.0 | M |
| #95 | Détection des attaques dans les journaux (équipe bleue) | v1.0 | M |

**Effort sprint : L** (agrégation des journaux, prérequis de la détection).

---

## 4. Backlog — usage réel

Ces issues ne se traitent bien qu'avec du **vrai trafic** ou **Stripe en mode live** : leur déclencheur est l'ouverture de la boutique à de vrais clients, pas un sprint calendaire.

| Issue | Intitulé court | Déclencheur |
|---|---|---|
| #67 | Tester l'idempotence du webhook sous appels simultanés | Webhook Stripe exercé en conditions réelles |
| #68 | Détecter la survente au lieu de la masquer | Concurrence réelle sur le stock |
| #72 | Stocker les médias téléversés hors des pods Kubernetes | Vrais médias téléversés en production |
| #83 | Sauvegarde automatisée de PostgreSQL | Données réelles à protéger |

---

## 5. Icebox

Idées conservées, non planifiées. Chacune a un **déclencheur de réveil** : tant qu'il n'est pas atteint, l'issue reste dormante.

| Issue | Intitulé court | Réveil |
|---|---|---|
| #53 | Application mobile React Native | Après #56 (une API à consommer) |
| #54 | API publique de type plateforme | Après #56 (API interne d'abord) |
| #61 | Marketplace — projet client séparé consommant l'API (post-#56) | Après #56, et si un besoin marketplace se confirme |
| #58 | Recherche sémantique par embeddings | Infrastructure d'embeddings disponible |
| #59 | Recommandations de produits similaires | Infrastructure d'embeddings disponible |

> **Sur #61.** L'issue s'intitule « Évolution vers une marketplace multi-vendeurs ». Elle est reformulée ici comme un **projet client séparé consommant l'API** (une fois #56 livrée), et non comme une refonte multi-vendeurs du monolithe : l'[ADR-003](adr/003-monolithe-modulaire.md) garde le cœur monolithique. Cette reformulation est propre à ce document ; l'issue GitHub n'est pas modifiée.

---

## 6. Hors dépôt — certification

| Issue | Intitulé court | Nature |
|---|---|---|
| #92 | Exercice Vault hors projet, pour la certification | Exercice de certification, sans impact sur le code du dépôt |

---

## 7. Note sur les jalons de #67 / #68 / #72 / #83

Ces quatre issues sont rattachées au jalon **v0.2** dans GitHub (vérifié sur #67 et #83). Or elles sont différées ici dans le [backlog usage réel](#4-backlog--usage-réel), dont le déclencheur (vrai trafic, Stripe live) relève plutôt de la v1.0. Il y aurait donc lieu d'envisager leur déplacement de v0.2 vers v1.0.

**Cette décision n'est pas prise** : conformément au périmètre de ce document, aucun jalon GitHub n'est modifié ici. Le point est seulement signalé.
