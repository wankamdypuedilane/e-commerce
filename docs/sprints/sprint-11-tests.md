# Sprint 11 — Tests

**Période :** 21/09/2026, 22h58 → 23/09/2026, 12h28
**Commits :** 6 sur `main` (`3e1de5e`, `6f177e9`, `94a0c70`, `e06abc2`, `6c67a6a`, `215bac9`)
**Issues fermées :** #66 (en ouverture), #32, #33, #34
**Issues ouvertes pendant le sprint :** #67, #68, #69
**Fichiers de tests produits :** `shop/test_webhook.py`, `shop/test_tva.py`, `shop/test_auth.py`, `shop/test_stripe_session.py`

---

## 1. Objectif du sprint

Protéger par des tests le code qui touche à l'argent et au stock.

Le projet comptait 9 tests, tous dans `shop/tests.py`. Aucun ne couvrait le webhook Stripe, seul code qui décrémente le stock en production, ni le calcul de la TVA, ni la construction de la session de paiement envoyée à Stripe. Le Sprint 9 avait annoncé les tests comme prérequis du découpage en apps ; ils n'avaient pas été entamés au Sprint 10.

Un préalable s'imposait : la CI était rouge. Des tests ajoutés à une CI qui échoue déjà ne signalent rien. L'issue #66 a donc été traitée en ouverture, avant tout nouveau test.

---

## 2. Issues traitées

| # | Intitulé | Résultat |
|---|---|---|
| 66 | CI rouge depuis l'ajout de WhiteNoise | **Fermée**, en ouverture de sprint. |
| 32 | Tester le webhook Stripe | **Fermée.** 8 tests, un bug corrigé. |
| 33 | Tester `services.py`, `backends.py` et `forms.py` | **Fermée.** 29 tests, deux bugs corrigés. |
| 34 | Mesurer la couverture de tests | **Fermée.** 69,9 %, cliquet à 69. |

### Détail

**#66 — CI.** La CI testait un environnement distinct de l'image déployée : Python installé sur le runner, sans PostgreSQL, sans `collectstatic`. Elle construit désormais l'image, démarre PostgreSQL par Compose et exécute `check`, les tests et `check --deploy` à l'intérieur de l'image. Le fichier `.env` est reconstruit à chaque exécution à partir de `.env.example`, avec des valeurs aléatoires : un modèle incomplet fait maintenant échouer la CI. Le runner est figé sur `ubuntu-24.04`, `ubuntu-latest` devant passer à Ubuntu 26 le 19/10/2026.

La CI a été vérifiée dans les deux sens : verte sur `3e1de5e`, puis rouge sur un test volontairement en échec (`e26c609`, branche `verif-echec-ci`, déclenchement manuel). Une CI qui ne peut pas échouer ne vérifie rien.

**#32 — Webhook Stripe.** 8 tests d'intégration dans `shop/test_webhook.py`. La vérification de signature est réelle : les requêtes sont signées avec un secret de test, et seul l'appel réseau à l'API Stripe est simulé. Sont couverts : secret absent et signature invalide rejetés, paiement confirmé qui décrémente le stock, événement reçu deux fois qui ne décrémente qu'une fois, email de confirmation envoyé une seule fois, paiement non confirmé sans effet sur le stock, session expirée qui annule la commande. Le huitième test a mis au jour le premier bug du sprint (section 3).

**#33 — Services, authentification, formulaires.** Trois fichiers.

- `shop/test_tva.py` — 10 tests unitaires du calcul de TVA. Ils fixent l'usage de `Decimal` (une entrée `float` lève `TypeError`), l'arrondi au centime et le mode `ROUND_HALF_UP` : 0,045 doit donner 0,05, là où `ROUND_HALF_EVEN` donnerait 0,04. Un test documente un comportement discutable sans l'entériner : un taux invalide retombe silencieusement sur 20 % (issue #69).
- `shop/test_auth.py` — 13 tests du backend de connexion par email et des formulaires d'inscription et de connexion, dont l'email obligatoire à l'inscription. Deux ont été écrits rouges avant leur correction (section 3).
- `shop/test_stripe_session.py` — 6 tests de la session de paiement Stripe. Le test central fixe un invariant : la somme des lignes envoyées à Stripe, en centimes, est égale au total TTC de la commande. Il utilise un taux réduit de 5,5 % et plusieurs quantités, cas où l'arrondi dérive en premier.

**#34 — Couverture.** Mesurée avec les branches (`branch = True` dans `.coveragerc`) : un `if` dont seul le cas vrai est testé n'est pas compté comme couvert. Niveau atteint : **69,9 %**. Le seuil `fail_under` est fixé à 69, juste en dessous, comme un cliquet : la couverture ne peut plus baisser sans faire échouer la CI, et le seuil se relève à mesure que des tests s'ajoutent. Le cliquet a été vérifié dans les deux sens : code de sortie 0 au seuil réel, 2 avec un seuil de 75.

---

## 3. Trois bugs trouvés par les tests

Chacun a été trouvé par un test écrit d'abord, constaté rouge, puis passé au vert par la correction. L'ordre compte : un test écrit après la correction peut passer pour de mauvaises raisons, et rien ne prouve alors qu'il aurait détecté le défaut.

### Le webhook répondait 200 sur une panne

En cas d'erreur pendant le traitement d'un événement, le webhook répondait **200**. Stripe considérait l'événement comme livré et ne le renvoyait jamais : le paiement était encaissé chez Stripe et perdu côté boutique, commande non confirmée et stock non décrémenté.

Il répond désormais **500** (`6f177e9`), et Stripe réessaie. Ce renvoi est sans danger : la transaction est annulée en cas d'erreur, et le drapeau `stock_deducted`, lu sous verrou, empêche une double décrémentation.

### Énumération des comptes par chronométrage

Pour un email inconnu, le backend de connexion répondait immédiatement ; pour un email existant, il calculait un hachage de mot de passe de plusieurs centaines de millisecondes. Chronométrer les réponses suffisait à savoir quels emails étaient inscrits (dette 3.4 de l'audit).

Le backend hache désormais un mot de passe jetable lorsque l'email est inconnu, comme le fait le `ModelBackend` de Django (`shop/backends.py`, `e06abc2`). Le test vérifie l'appel au hachage plutôt que de mesurer un temps de réponse : une mesure de durée dépendrait de la charge de la machine et échouerait de façon aléatoire.

### Message d'erreur sans accents

Le formulaire d'inscription affichait « Cet email est deja utilise. » Le message est corrigé en « Cet email est déjà utilisé. » (`shop/forms.py`). Le défaut est mineur ; il est cité parce qu'il a été trouvé de la même façon que les deux autres, par un test qui compare le texte exact affiché à l'utilisateur.

---

## 4. Décisions prises en cours de route

### Des tests unitaires sans base là où c'est possible

Sur les 37 tests ajoutés, 16 héritent de `SimpleTestCase` et n'ouvrent aucune connexion à la base : les 10 tests de TVA et les 6 tests de session Stripe. Les tests de TVA s'exécutent en 6 ms, contre 525 ms pour les tests d'intégration du webhook. Le calcul de TVA et la construction des lignes Stripe sont des fonctions pures ; les tester à travers la base n'aurait rien ajouté, sinon du temps.

### Le webhook testé avec une vraie signature

Simuler la vérification de signature aurait été plus simple. Elle est réelle dans les tests, parce que c'est la première barrière du webhook : un test qui la contourne ne dit rien de ce qui arrive à une requête non signée. Seul l'appel réseau à l'API Stripe est simulé.

### coverage isolé dans une étape `test` du Dockerfile

`coverage` est installé dans une étape `test` du Dockerfile, construite uniquement avec `--target test`, pour la CI. L'ordre des étapes a été choisi à dessein : `runtime` reste la **dernière**, puisque c'est celle que Docker construit sans `--target`, y compris pour Kubernetes. Placer `test` en dernier aurait livré les outils de test en production sans qu'aucune commande ne change.

Vérifié : dans l'image de production, `import coverage` échoue, et sa taille est inchangée à **233 Mo**.

### Le défaut théorique est gardé par un test, pas corrigé

La conversion en centimes tronque par `int()`. Le défaut est théorique aujourd'hui (section 5). Plutôt que de modifier un code qui fonctionne, l'invariant « somme des lignes = total TTC » est fixé par un test : il échouera si une modification future réintroduit des `float`.

### Retrait de la directive `syntax` du Dockerfile

La directive `# syntax=` obligeait chaque construction à télécharger une image depuis Docker Hub. Un incident DNS suffisait à faire échouer une construction par ailleurs entièrement en cache. Elle a été retirée (`94a0c70`).

---

## 5. Ce qui a surpris

### La CI était rouge depuis quinze commits, avec deux pannes empilées

Le dernier passage vert datait de `2f70d6b`. Les quinze commits suivants, de `7d99c1a` à `41c2537`, sur l'ensemble du Sprint 10, avaient tous échoué sans que cela arrête le travail.

Deux pannes se superposaient, toutes deux reproduites en local :

1. `manage.py check` levait `ImproperlyConfigured` depuis que `DJANGO_SECRET_KEY` était devenue obligatoire (`c87eaae`), l'étape ne la fournissant pas.
2. 4 des 9 tests échouaient sur une entrée absente du manifeste des fichiers statiques depuis l'ajout de WhiteNoise (`7d99c1a`), `collectstatic` n'étant jamais exécuté en CI.

La seconde était **masquée par la première** : `check` échouant avant, l'étape des tests ne s'exécutait pas. Corriger seulement la panne visible aurait laissé la CI rouge, pour une raison différente. La cause commune n'était ni l'une ni l'autre : la CI testait un environnement qui n'était pas celui de l'image déployée.

### Un défaut de conversion en centimes semblait réel ; il était théorique

`shop/services.py` convertit les montants en centimes par `int(Decimal(item['price']) * 100)`. `int()` tronque : sur un prix `float` tel que 19,99, la représentation binaire peut donner 1998,999… et perdre un centime.

La lecture de la vue `checkout` a montré que ce cas ne se produit pas : les prix y sont passés sous forme de chaînes construites à partir de `Decimal` (`'price': str(product.price)`), et `Decimal('19.99') * 100` vaut exactement 1999. Le défaut n'existe que si un `float` entre un jour dans cette chaîne. Il est gardé par le test d'invariant plutôt que corrigé à l'aveugle.

### L'audit décrivait mal le doublon d'email

L'audit (dette 2.7) présentait le cas de deux comptes partageant un même email comme un risque de **connexion au mauvais compte**. Le code fait autre chose : le backend sélectionne le compte le plus ancien et vérifie le mot de passe **de ce compte**. Le second titulaire, dont le mot de passe ne correspond pas, est **bloqué** : il ne peut pas se connecter par email. Personne n'entre dans le compte d'un autre.

Le comportement est documenté par un test, pas corrigé : une vraie correction suppose une contrainte d'unicité en base, donc une migration et le traitement des doublons existants. C'est la deuxième fois, après la dette 1.6 au Sprint 10, qu'une description de l'audit ne correspond pas au code. Lire le code avant d'appliquer une correction d'audit reste nécessaire.

### `/app` appartient à root, et c'est voulu

`coverage run` écrit par défaut son fichier de mesures `.coverage` dans le répertoire courant, `/app`. Dans l'image, `/app` appartient à `root` et n'est pas inscriptible par l'utilisateur `django` qui exécute l'application : l'écriture échouait.

Rendre `/app` inscriptible aurait réglé le problème, en retirant une propriété de sécurité : un processus compromis ne peut pas modifier le code qu'il exécute. La propriété a été conservée ; le fichier de mesures est écrit dans `/tmp` (`data_file = /tmp/.coverage` dans `.coveragerc`).

> **Erratum (23/09/2026).**
>
> **L'erreur.** Cette section affirme que `/app` appartient à `root` et qu'un processus compromis ne peut pas modifier le code qu'il exécute. C'était faux à la date du sprint. Seul le répertoire `/app` lui-même appartenait à `root`. Le Dockerfile copiait le code avec `COPY --chown=django:django . .` : tous les fichiers et sous-répertoires copiés (`manage.py`, `shop/`, `ecommerce/`…) appartenaient à `django`, et `staticfiles/` lui était confié par `chown -R`. Le processus applicatif pouvait donc réécrire ses vues et sa configuration. La propriété de sécurité décrite ici n'existait pas.
>
> **La cause.** La conclusion a été tirée d'une seule écriture refusée : la création de `.coverage` à la racine de `/app`. Cet échec prouvait seulement que le répertoire `/app` n'était pas inscriptible, pas que les fichiers qu'il contient ne l'étaient pas. Leur propriétaire n'a pas été vérifié. La même affirmation a été reprise dans le message de `215bac9`, dans le commentaire de `.coveragerc`, puis dans `6bf7a60`. L'erreur a été relevée pendant la synchronisation de la documentation, en tentant d'écrire dans `/app/shop` depuis l'image.
>
> **La correction.** Commit `80278b6` (issue #84) : le code est désormais copié en tant que `root`, sans `--chown`, et `staticfiles/` n'est plus confié à `django`. Tout `/app` appartient à `root` sauf `/app/media`, seul emplacement inscriptible par l'application. Deux tests de `shop/test_image.py`, exécutés dans l'image sous l'utilisateur `django`, vérifient que le code reste lisible et non modifiable. Écrits avant la correction, ils échouaient.
>
> Le contenu de cette rétrospective n'est pas modifié ; seul cet encadré a été ajouté.

### Deux fausses assurances venues d'une sortie mal lue

À deux reprises pendant le sprint, une vérification a paru réussie alors qu'elle ne prouvait rien :

- une commande dont la sortie était redirigée vers `/dev/null` : l'absence de message a été lue comme une absence d'erreur, alors que l'erreur avait simplement été jetée ;
- un code de sortie lu par `$?` après un pipeline se terminant par `tail` : `$?` rendait le code de `tail`, toujours 0, et non celui de la commande testée.

Dans les deux cas, la commande vérifiée n'était pas celle que l'on croyait. La vérification du cliquet (section 2) a été faite en lisant explicitement le code de sortie de `coverage report`, dans les deux sens, pour cette raison.

---

## 6. Reporté

### Idempotence du webhook sous appels simultanés — #67

Les tests couvrent un événement reçu deux fois **de suite**. Ils ne couvrent pas deux appels **simultanés**, que le verrou `select_for_update` est censé couvrir. Le test prévu lance deux requêtes en parallèle dans un `TransactionTestCase`, et doit s'exécuter sur PostgreSQL : SQLite ignore `select_for_update`.

### Survente masquée — #68

Dans le webhook, le stock est calculé par `max(0, stock - quantité)`. Si deux clients achètent le dernier exemplaire presque en même temps, le stock descend à 0 au lieu de −1 : aucune erreur, aucune trace, et un produit vendu deux fois sans que personne ne le sache. L'issue demande de détecter la survente, de la journaliser au niveau `ERROR`, de la signaler dans l'administration, et de décider entre remboursement automatique et traitement manuel.

### Taux de TVA invalide — #69

Un taux mal configuré (`TAX_RATE_PERCENT`) retombe silencieusement sur 20 %. Ce comportement est fixé par un test de `shop/test_tva.py` pour qu'il ne change pas sans qu'on le voie, pas parce qu'il est jugé correct. L'issue demande de refuser la configuration invalide.

### Couverture de `shop/views.py` : 54 %

C'est le fichier le moins couvert, et le plus volumineux (267 instructions, 112 non couvertes). La moyenne de 69,9 % est portée par les services, les modèles et les formulaires, tous au-dessus de 85 %. Le cliquet empêche la couverture de baisser ; il ne dit rien de sa répartition. Le découpage en apps prévu au Sprint 12 déplacera l'essentiel de ce fichier : le couvrir avant le découpage est ce qui permettra de vérifier que le découpage ne change rien.

### Éléments hérités, toujours ouverts

| Dette | Élément | Origine |
|---|---|---|
| 2.5 | Aucune sauvegarde active de la base | Sprint 7 |
| 4.4 | Deux champs d'image concurrents sur `Product` (`image`, `image_file`) | Sprint 9 |
| 2.7 | Unicité d'email sans contrainte en base : second titulaire bloqué | Audit ; comportement précisé au Sprint 11 |

---

## 7. État en fin de sprint

| Élément | État |
|---|---|
| Tests | 46 (9 au départ), tous verts |
| Tests unitaires sans base | 16 (`SimpleTestCase`) |
| Couverture, branches incluses | 69,9 % |
| Seuil `fail_under` | 69 |
| `shop/views.py` | 54,0 % |
| CI | Verte sur les 6 commits du sprint, exécutée dans l'image contre PostgreSQL |
| Image de production | 233 Mo, sans `coverage` |
| Job CI `deploy` (EC2) | Toujours neutralisé par `if: false` |

---

## 8. Prochaines échéances

- **Sprint 12** — Découpage en six apps Django, conformément à l'[ADR-003](../adr/003-monolithe-modulaire.md). Relever d'abord la couverture de `shop/views.py`.
- **Issues ouvertes** — #67, #68, #69.
- **Hors sprint** — domaine `dilane-shop.store` (#30), VM Azure, registre d'images, sauvegarde automatisée.
