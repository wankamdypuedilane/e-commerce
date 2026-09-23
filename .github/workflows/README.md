# Intégration continue

Le workflow `ci.yml` s'exécute à chaque push sur `main`, sur chaque pull
request (dont celles de Dependabot) et à la demande. Il ne déploie rien.

Étapes, dans l'ordre :

1. **Scan des dépendances** avec pip-audit, avant toute construction : échec
   dès qu'une vulnérabilité connue touche l'application ou ses outils de test.
2. **Construction** de l'image de production et de l'image de test, puis
   démarrage de PostgreSQL.
3. **Vérification de configuration** : `manage.py check` dans l'image de
   production.
4. **Tests dans l'image de test**, sur PostgreSQL, avec mesure de couverture
   et seuil minimal défini dans `.coveragerc`.
5. **Vérification de déploiement** : `manage.py check --deploy
   --fail-level ERROR` dans l'image de production.
6. **Test de fumée** : démarrage du vrai conteneur de production, attente de
   `/healthz/`, échec si les journaux de démarrage contiennent une erreur.

La pile est arrêtée et ses volumes supprimés à la fin, même en cas d'échec.

Aucun secret n'est nécessaire : le fichier `.env` est reconstruit à chaque
exécution depuis `.env.example`, avec une clé et un mot de passe aléatoires.

Le déploiement vers Kubernetes fera l'objet d'un workflow distinct
(issue #43). L'ancien déploiement SSH vers EC2, désactivé depuis le
Sprint 9, a été retiré ; il reste consultable dans l'historique Git.
