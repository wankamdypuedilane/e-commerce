# Intégration continue

Le workflow `ci.yml` s'exécute à chaque push sur `main`, sur chaque pull
request (dont celles de Dependabot) et à la demande. Il ne déploie rien.

Étapes, dans l'ordre :

1. **Scan des dépendances** avec pip-audit, avant toute construction : échec
   dès qu'une vulnérabilité connue touche l'application ou ses outils de test.
2. **Analyse statique** avec Bandit, dans un conteneur jetable, sur `shop` et
   `ecommerce`, migrations et fichiers de test exclus : échec dès qu'un motif
   dangereux est détecté.
3. **Construction** de l'image de production et de l'image de test.
4. **Scan de l'image de production** avec Trivy, dans un conteneur jetable :
   paquets du système et paquets Python, échec dès qu'une faille HIGH ou
   CRITICAL disposant d'un correctif est trouvée.
5. **Démarrage de PostgreSQL**, puis **vérification de configuration** :
   `manage.py check` dans l'image de production.
6. **Tests dans l'image de test**, sur PostgreSQL, avec mesure de couverture
   et seuil minimal défini dans `.coveragerc`.
7. **Vérification de déploiement** : `manage.py check --deploy
   --fail-level ERROR` dans l'image de production.
8. **Test de fumée** : démarrage du vrai conteneur de production, attente de
   `/healthz/`, échec si les journaux de démarrage contiennent une erreur.
9. **Publication de l'image** sur `ghcr.io/wankamdypuedilane/dilane-shop`,
   seulement sur un push sur `main`, jamais depuis une pull request. Deux
   étiquettes : `latest` et l'identifiant du commit, auquel la surcouche de
   production fige l'image (issue #43).

La pile est arrêtée et ses volumes supprimés à la fin, même en cas d'échec.

Aucun secret n'est à configurer : le fichier `.env` est reconstruit à chaque
exécution depuis `.env.example`, avec une clé et un mot de passe aléatoires.
La publication s'authentifie avec le `GITHUB_TOKEN` fourni automatiquement
par GitHub (permission `packages: write`).

Le workflow publie l'image mais ne la déploie pas : le déploiement sur le
cluster de production reste manuel (voir `docs/deploiement-production.md`).
L'ancien déploiement SSH vers EC2, désactivé depuis le Sprint 9, a été
retiré ; il reste consultable dans l'historique Git.
