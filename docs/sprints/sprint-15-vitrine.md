# Sprint 15 — Vitrine visible

**Période :** 29/09/2026, 05h48 → 29/09/2026, 09h16
**Commits :** 6 sur `main` (`2413de7`, `6fd56f0`, `b5079c8`, `2cda549`, `32bb22c`, `d1d54e3`)
**Issues fermées :** #55, #63, #91, #90, #93 (annulée)
**Issue déplacée :** #98 (Icebox)
**Issue ouverte pendant le sprint :** #113
**Pull requests :** #109, #110, #111, #112 fusionnées ; #114 fusionnée puis annulée par revert (`d1d54e3`)
**Gabarits produits :** `templates/404.html`, `templates/500.html`
**Migration produite :** `shop/migrations/0016_alter_orderitem_options_alter_product_options.py`
**Document de pilotage :** `docs/ROADMAP.md` (`d4ee4d5`, PR #108, fusionnée à l'ouverture du sprint)

---

## 1. Objectif du sprint

Rendre le site et le dépôt « finis » pour un recruteur, avant les gros chantiers.

Les sprints 13 et 14 avaient mis l'application en production puis sous surveillance. Restaient des finitions visibles, relevées au fil des sprints précédents sans jamais être traitées : pages d'erreur brutes de Django, une icône qui ne s'affichait pas, une administration à moitié en anglais, un avertissement dans l'onglet Issues de Chrome. Chacune est petite ; ensemble, elles donnent l'impression d'un projet inachevé à qui le parcourt.

L'objectif retenu a été de solder ces quick wins en un sprint court, avant la modularisation, l'API et l'IA, qui demanderont des sprints entiers. La contrainte était le périmètre : aucune de ces issues ne devait grossir en cours de route.

---

## 2. Issues traitées

| # | Intitulé | Résultat |
|---|---|---|
| 55 | Pages d'erreur 404 et 500 personnalisées | **Fermée** le 29/09. |
| 63 | Bootstrap Icons référencé mais jamais chargé | **Fermée** le 29/09. |
| 91 | Noms d'affichage en français pour Product et OrderItem | **Fermée** le 29/09. |
| 90 | Attributs de saisie automatique sur le formulaire de commande | **Fermée** le 29/09. |
| 93 | Exclure `.coveragerc` de l'image de production | **Annulée.** Livrée puis revertée (section 5). |
| 98 | Raffiner les échelles du tableau de bord Grafana | **Non traitée.** Déplacée en Icebox (section 6). |

### Détail

**#55 — Les pages d'erreur** (`2413de7`, PR #109). Deux gabarits à la racine de `templates/`, trouvés par les gestionnaires par défaut de Django : aucun `handler404` ni `handler500` n'a été déclaré.

Les deux pages diffèrent volontairement, parce que Django ne les rend pas avec le même contexte :

- **`404.html` hérite de `shop/base.html`.** La 404 est rendue avec un `RequestContext` : l'héritage, les balises `{% url %}` et le nonce CSP des scripts de `base.html` se résolvent. La page reste cohérente avec le reste du site.
- **`500.html` est autonome.** `server_error` rend la 500 **sans contexte**. Pas de `{% extends %}`, pas de `{% load %}`, pas de `{% url %}`, pas de `{{ csp_nonce }}`, aucun accès à la base. Une seule de ces dépendances, et c'est la page d'erreur elle-même qui planterait, au moment précis où elle doit s'afficher. Document HTML complet, style en ligne aux couleurs du site (`#2c3e50`), lien de retour écrit en dur vers `/`.

3 tests ajoutés (`shop/test_pages_erreur.py`), 82 au total. Avec `DEBUG=False`, une URL inconnue rend 404 et utilise `templates/404.html` ; `500.html` se rend sans aucun contexte ; et un test lit la source de `500.html` et échoue si l'une des dépendances interdites y apparaît. Ce dernier protège la règle contre une modification future, qui semblerait anodine à qui ne connaît pas la contrainte.

**#63 — L'icône de confirmation** (`6fd56f0`, PR #110). La page de confirmation de commande utilisait `bi bi-check-circle-fill`, mais la bibliothèque Bootstrap Icons n'était chargée nulle part : l'icône ne s'affichait pas. C'était le seul usage de `bi-*` du projet.

Charger la bibliothèque aurait tiré une centaine de kilooctets pour une seule icône. Elle a été remplacée par le SVG officiel de la même icône, écrit en ligne dans le gabarit, avec `fill="currentColor"` pour garder la couleur `text-success`, et un `aria-label` « Commande confirmée ». Zéro dépendance, zéro requête réseau. Plus aucune classe `bi-*` dans le projet.

**#91 — L'administration en français** (`b5079c8`, PR #111). L'administration affichait *Products* et *Order items* à côté de *Catégories* et *Commandes*. `verbose_name` et `verbose_name_plural` ajoutés à `Product` (« Produit ») et `OrderItem` (« Article de commande ») uniquement : `Category`, déjà en français, n'a pas été touché.

La migration `0016` ne contient que des `AlterModelOptions` : aucun changement de schéma, aucun impact sur la base. Vérifié visuellement dans `/admin/`.

**#90 — La saisie automatique** (`2cda549`, PR #112). Attribut `autocomplete` sur les 7 champs du formulaire de commande : `name`, `email`, `address-line1`, `address-line2`, `address-level2`, `country-name`, `postal-code`. Le navigateur peut désormais les remplir depuis son carnet d'adresses, et l'avertissement de l'onglet Issues de Chrome, à l'origine de l'issue, disparaît.

---

## 3. Décisions prises en cours de route

### Un périmètre strict, issue par issue

Chaque issue a été livrée dans son périmètre exact, et ce qui la dépassait a été sorti :

- pendant #90, l'idée d'une vraie autocomplétion d'adresses est apparue. L'attribut `autocomplete` ne fait que réutiliser le carnet du navigateur ; suggérer des adresses réelles pendant la frappe demande une API, un appel réseau et une ouverture de la CSP. Elle a été consignée dans une issue séparée, #113 (API Base Adresse Nationale), rangée en Icebox, au lieu d'élargir #90 ;
- pendant #91, `Category` n'a pas été retouché, alors qu'il était dans le même fichier.

Une issue qui grossit en cours de route ne se ferme plus en une PR, et le sprint court perd sa raison d'être.

### Une grille de priorisation : valeur pour le stage, contre trafic inexistant

Le backlog a été trié avec une question simple : cet élément apporte-t-il quelque chose de visible maintenant, ou suppose-t-il un trafic que le site n'a pas ? Les quick wins de ce sprint passent le filtre : ils se voient à la première visite. Le raffinement des échelles Grafana (#98) ne le passe pas (section 6). C'est la même logique que pour les reports déjà actés de #83 et #67 : ne pas durcir ni peaufiner pour un usage qui n'existe pas encore.

### La mise à plat du pilotage

Le sprint s'est ouvert sur une remise en ordre complète du suivi :

- **`docs/ROADMAP.md`** (`d4ee4d5`, PR #108) : une feuille de route unifiée, versions du produit et séquence des sprints ;
- **le tableau GitHub Projects**, aligné sur cette feuille de route : champ *Sprint* de 15 à 20, colonnes *Status* ;
- **34 issues rangées** dans ce tableau.

Le dépôt et le tableau racontent désormais la même chose.

---

## 4. Ce qui a surpris

### Trois issues fermées sans avoir été faites

Pendant le rangement du tableau, le 29/09, les cartes ont été déplacées en lot vers la colonne *Done*. Chaque déplacement a fermé l'issue correspondante, avec le motif « completed » :

- à 05h26 (03h26 UTC), **#86, #88 et #89**, alors qu'aucun travail n'avait été fait ;
- à 05h32, #90, #91 et #93, avant les PR qui allaient les livrer ou, pour #93, l'annuler.

Pour les trois premières, le dépôt ne laissait aucun doute :

| Issue | Élément | Ce que montre le dépôt |
|---|---|---|
| #86 | Versions des outils de sécurité suivies par Dependabot | Aucun `requirements-ci.txt` |
| #88 | Collecte des violations de la politique de sécurité du contenu | Aucune directive de rapport dans la CSP |
| #89 | Retrait des attributs `style=` | Toujours présents dans 3 gabarits de `shop/templates` |

Les trois issues ont été **rouvertes** le 29/09 au soir et remises en *To Do* dans leurs sprints respectifs : #86 au Sprint 18, #89 au Sprint 19, #88 au Sprint 20.

Ce n'était pas la première fois. Le 25/09, un rangement du même genre avait déjà fermé à tort #88, #90 et #93. Chacune porte encore le commentaire de sa réouverture : « Rouverte : fermée par erreur lors du rangement du tableau, le travail n'a pas été fait. »

Déplacer une carte dans *Done* ne demande aucune confirmation. Le motif « completed » qui en résulte ne dit pas si le travail a été fait, et une issue fermée disparaît des listes où l'on cherche le travail restant. Sans la vérification faite après cette rétrospective, trois chantiers de sécurité et de supervision seraient sortis du backlog sans bruit.

### Le `.coveragerc` n'était pas un fichier de développement inutile

Voir la section suivante.

### Les deux leçons de process

**Une issue ne se ferme que par la fusion de sa PR.** Jamais par un déplacement de carte, jamais par une fermeture en lot. La PR porte `Closes #n` : c'est sa fusion qui ferme l'issue. Le tableau suit l'état des issues ; il ne le décide pas. Une issue abandonnée se ferme à la main, une par une, avec le motif « not planned » et un commentaire qui dit pourquoi.

**Une PR ne se fusionne qu'une fois sa CI verte.** La PR #114 a été fusionnée avant la fin de sa CI : `main` est passé au rouge et il a fallu un revert (section 5). Même pour une ligne dans un `.dockerignore`, on attend le vert.

---

## 5. L'issue annulée : #93

### Ce qui a été fait

L'issue, relevée à la rétrospective du Sprint 12, partait d'un constat juste en apparence : `.coveragerc` sert à l'étape de test, l'image de production n'en a pas besoin. Il a été ajouté au `.dockerignore` (`32bb22c`, PR #114).

L'issue elle-même prévenait pourtant : « l'exclure du .dockerignore le retirerait des deux images ; il faudrait le copier à l'étape test uniquement. »

### Ce qui a cassé

La CI a échoué, sur la PR puis sur `main`, avec un résultat trompeur au premier regard :

```
Ran 82 tests in 6.127s
OK
Couldn't use data file '/app/.coverage': unable to open database file
```

Les 82 tests passaient. C'est la mesure de couverture qui échouait, après eux.

### Pourquoi

Dans l'image durcie, `/app` appartient à root et reste non inscriptible par l'utilisateur `django` : c'est voulu en production. `.coveragerc` contient la ligne qui contourne cette contrainte pour les tests :

```
data_file = /tmp/.coverage
```

Sans le fichier, coverage revient à son chemin par défaut, `/app/.coverage`, qu'il ne peut pas créer. Le fichier jugé « inutile » portait une dépendance cachée entre la configuration de la couverture et le durcissement de l'image.

### Comment ça s'est terminé

La dépendance a été révélée par l'échec de la CI, comprise en lisant ses journaux, et corrigée par un revert (`d1d54e3`), six minutes après la fusion. CI de nouveau verte sur `d1d54e3`. L'étape de publication vers GHCR n'étant atteinte qu'après les tests, aucune image sans `.coveragerc` n'a été publiée.

La PR #114 a été fusionnée 58 secondes après son ouverture, avant la fin de sa propre CI, qui s'est terminée en échec 27 secondes plus tard. Attendre le résultat de la CI de la PR aurait évité le commit rouge sur `main`.

L'issue reste fermée : l'exclusion est annulée, non reportée. Son motif de fermeture sur GitHub est resté « completed », hérité de la fermeture en lot de 05h32, et non « not planned ». L'écart est cosmétique et n'a pas été corrigé : c'est une dette mineure de suivi. Le gain visé, un fichier texte de moins dans l'image, ne justifie pas de séparer la configuration de coverage entre les deux étapes du Dockerfile.

---

## 6. Reporté

### #98 — Échelles du tableau de bord Grafana : en Icebox

Le panneau des erreurs monte jusqu'à 10 000 % lors des pics transitoires à faible trafic. Le borner à 100 % est facile ; le raffiner utilement ne l'est pas sans trafic réel : régler des échelles sur des courbes plates n'a pas de sens. L'issue attendra que le site ait des visiteurs. Même logique de report que #83 et #67.

### #113 — Autocomplétion d'adresses : en Icebox

Ouverte pendant #90 (section 3). Elle demande l'ajout de `api-adresse.data.gouv.fr` à `connect-src` dans la CSP, et une dégradation propre si l'API ne répond pas.

### Éléments hérités, toujours ouverts

| Issue | Élément | Origine |
|---|---|---|
| #83 | Sauvegardes hors du serveur, alerte en cas d'échec de la sauvegarde | Sprint 13 |
| #72 | Médias téléversés stockés dans les pods | Sprint 13 |
| #46 | Agrégation des journaux | Sprint 14 |
| #49 | Découpage de `shop` en apps Django distinctes | ADR-003 |
| #39 | Gestion des secrets hors base64 | Sprint 12 |
| #67, #68, #69 | Webhook sous appels simultanés, survente masquée, taux de TVA invalide | Sprint 11 |
| #94, #95 | Test d'intrusion, détection dans les journaux | Sprint 12 |
| #86, #88, #89 | Outils de sécurité suivis par Dependabot, violations CSP, attributs `style=` ; rouvertes le 29/09 (section 4) | Sprint 12 |

---

## 7. État en fin de sprint

| Élément | État |
|---|---|
| Pages d'erreur | 404 intégrée au site, 500 autonome ; règle de la 500 protégée par un test |
| Icônes | SVG en ligne, aucune bibliothèque d'icônes, plus aucune classe `bi-*` |
| Administration | Tous les modèles libellés en français |
| Formulaire de commande | 7 champs avec `autocomplete` |
| Migrations | `0016`, options de modèles uniquement, sans changement de schéma |
| Image déployée | Figée sur `5df4ad5` dans la surcouche de production : les livraisons du sprint n'y sont pas encore |
| Tests | 82, tous verts |
| Couverture, branches incluses | Seuil `fail_under` inchangé à 76, tenu |
| CI | Verte sur 5 des 6 commits du sprint ; rouge sur `32bb22c`, verte à nouveau après le revert |
| Pull requests ouvertes | 0 |
| Pilotage | `ROADMAP.md` unifié, tableau Projects aligné, champ *Sprint* de 15 à 20 |

Sprint 15 clos : 4 issues livrées, 1 annulée, 1 reportée.

---

## 8. Prochaines échéances

- **Déployer** : repointer `newTag` de la surcouche de production sur un commit du Sprint 15, pour que les pages d'erreur, l'icône et la saisie automatique soient visibles sur `dilane-shop.store`. C'était l'objectif du sprint.
- **Vérifier la 500 en production** : les tests la rendent sans contexte, mais son affichage derrière ingress-nginx, sur une vraie erreur, n'a pas été observé.
- **Ne fermer une issue que par la fusion de sa PR**, jamais par un déplacement de carte ni en lot (section 4).
- **Attendre la CI de la PR avant de fusionner**, même pour une modification d'une ligne (section 5).
- **Dette mineure** : le motif de fermeture de #93 est « completed » au lieu de « not planned ».
- **Sprint 16 — Modularisation & API** : #49, #50, puis #56.
- **#86 au Sprint 18, #89 au Sprint 19, #88 au Sprint 20**, rouvertes le 29/09.
- **Issues ouvertes** — #98, #113, #83, #72, #46, #39, #49, #67, #68, #69, #86, #88, #89, #94, #95.
