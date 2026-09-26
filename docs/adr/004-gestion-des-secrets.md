# ADR-004 — Secrets chiffrés dans le dépôt avec SOPS et age

## Statut

Accepté — 24/09/2026. Implémenté le 25/09/2026 : configuration SOPS, secrets chiffrés versionnés et procédures documentées. L'application au cluster sera exercée avec la VM Azure et k3s (issues #40 et #41). Répond en partie à l'issue #39 : voir « Réserves sur la portée ».

---

## Contexte

### Les secrets du projet

Le Secret Kubernetes `dilane-shop-secrets` porte huit clés, listées à la date de cette décision dans `k8s/02-secrets.example.yaml`, fichier supprimé depuis :

| Clé | Rôle |
|---|---|
| `DJANGO_SECRET_KEY` | Signature des sessions, des cookies et des jetons de réinitialisation de mot de passe |
| `DB_PASSWORD` | Mot de passe PostgreSQL |
| `STRIPE_PUBLIC_KEY` | Clé publique Stripe |
| `STRIPE_SECRET_KEY` | Clé d'API Stripe, qui permet de créer des paiements et de lire les transactions |
| `STRIPE_WEBHOOK_SECRET` | Vérification de la signature des webhooks Stripe |
| `BREVO_SMTP_LOGIN` | Identifiant SMTP Brevo |
| `BREVO_SMTP_KEY` | Clé SMTP Brevo, qui permet d'envoyer des emails au nom du site |
| `EMAIL_FROM` | Adresse d'expédition des emails transactionnels |

Toutes ne sont pas confidentielles au même degré : `STRIPE_PUBLIC_KEY` est destinée à être publique, et `EMAIL_FROM` est une adresse visible par chaque destinataire. Elles sont rangées dans le Secret parce qu'elles vont de pair avec les autres identifiants Stripe et Brevo, et non en raison de leur sensibilité.

Le Secret est consommé à trois endroits : par `envFrom.secretRef` dans le Deployment `django` (`k8s/base/04-django.yaml`) et dans le Job de migration (`k8s/base/05-migration-job.yaml`), et par `secretKeyRef` sur la seule clé `DB_PASSWORD` dans le StatefulSet PostgreSQL (`k8s/base/03-postgres.yaml`).

### La procédure actuelle

`k8s/02-secrets.example.yaml` est alors un modèle sans valeur. Il documente la création du Secret par une commande :

```bash
kubectl create secret generic dilane-shop-secrets \
  --namespace dilane-shop \
  --from-literal=DJANGO_SECRET_KEY="..." \
  --from-literal=DB_PASSWORD="..." \
  …
```

Le même fichier signale déjà la limite de ce dispositif : un Secret Kubernetes est encodé en base64, pas chiffré, et le chiffrement au repos doit être activé sur le cluster. L'[ADR-002](002-kubernetes.md) le montre par l'exemple : une seule commande `kubectl get secret … | base64 -d` suffit à lire une valeur en clair.

### Ce que cette procédure coûte en pratique

**Le cluster est jetable.** Le cluster `kind` du Sprint 10 se recrée à la demande à partir de `k8s/kind-cluster.yaml`, et se détruit de même. Aucun n'est actif à la date de cet ADR (`kind get clusters` ne renvoie rien). À chaque recréation, les huit valeurs sont retapées à la main dans la commande `kubectl create secret`.

**Rien ne garde trace de ce qui a été saisi.** Les valeurs n'existent que dans le Secret du cluster courant et dans la mémoire de la personne qui les tape. Rien ne permet de vérifier que le cluster recréé porte les mêmes valeurs que le précédent, ni de savoir quelle valeur de `DB_PASSWORD` correspond au volume PostgreSQL d'un environnement donné. Tapée dans un terminal, la commande laisse les valeurs en clair dans l'historique du shell. Le modèle génère en outre `DJANGO_SECRET_KEY` à la volée (`secrets.token_urlsafe(50)`) : chaque recréation produit une clé différente, ce qui invalide les sessions et les liens de réinitialisation de mot de passe émis avec la précédente.

**Le déploiement suivant change d'architecture.** Le jalon `v0.1 - MVP deploye` (issues #40 et #41) vise une VM Azure **B2pts v2**, en **ARM64**, avec k3s (issues #40 et #41). Tout outil retenu doit donc fonctionner sur `linux/amd64` pour le poste de développement et la CI, et sur `linux/arm64` pour la VM.

Le besoin est donc : des valeurs conservées et reproductibles d'un cluster à l'autre, qui ne soient lisibles en clair ni dans le dépôt ni dans l'historique du shell, sans coût et sur les deux architectures.

---

## Décision

**Versionner les secrets dans le dépôt, chiffrés avec SOPS et une clé age, et les déchiffrer au moment du déploiement.**

- **SOPS** chiffre les valeurs d'un fichier YAML en laissant ses clés lisibles. Le manifeste du Secret reste donc un manifeste Kubernetes ordinaire, dont seules les valeurs sont chiffrées : on voit quelles clés il contient, sans pouvoir les lire.
- **age** fournit la paire de clés. La clé publique, qui sert à chiffrer, peut être versionnée. La clé privée, qui sert à déchiffrer, reste hors du dépôt.
- **Au déploiement**, le fichier est déchiffré et transmis directement à `kubectl apply`, sans être écrit en clair sur le disque. Le cluster reçoit un Secret Kubernetes ordinaire : les manifestes `03`, `04` et `05` ne changent pas.

Versions de référence, vérifiées sur les pages de publication des deux projets le 24/09/2026 : **SOPS v3.13.3** et **age v1.3.2**, toutes deux publiées avec un binaire `linux/amd64` et un binaire `linux/arm64`. Les deux architectures du projet sont couvertes.

Les deux outils sont gratuits et libres. Ils s'exécutent sur le poste qui déploie : **aucun composant n'est installé dans le cluster.**

---

## Alternatives considérées

### A. Sealed Secrets

Un contrôleur installé dans le cluster détient une clé privée. Les secrets sont chiffrés avec sa clé publique, versionnés sous forme d'objets `SealedSecret`, puis déchiffrés par le contrôleur.

Écartée : c'est un contrôleur de plus à installer, à mettre à jour et à surveiller, dans un cluster qui est détruit régulièrement. Surtout, la clé de déchiffrement vit dans le cluster. Détruire le cluster détruit la clé, et les secrets chiffrés pour elle deviennent illisibles, à moins de sauvegarder cette clé hors du cluster et de la restaurer à chaque recréation. La contrainte de sauvegarde d'une clé privée demeure, et s'y ajoute un composant à maintenir.

### B. Azure Key Vault

Les secrets sont stockés dans le coffre du fournisseur cloud et lus par le cluster, par exemple au moyen d'External Secrets Operator ou du pilote CSI du coffre.

Écartée pour deux raisons. Elle crée une dépendance à un fournisseur **avant le premier déploiement** : aucune ressource Azure n'existe encore, et le cluster `kind` local devrait lui aussi s'authentifier auprès d'Azure pour lire ses propres secrets. Elle a ensuite un coût, prélevé sur le crédit étudiant de 100 USD dont dépend déjà l'arbitrage de l'ADR-002.

**À reconsidérer si le projet passe en production réelle** : une journalisation des accès et une rotation gérée par le fournisseur prendraient alors un sens qu'elles n'ont pas pour un projet sans trafic.

### C. Statu quo — secrets créés à la main par `kubectl`

Conserver la procédure actuelle.

Écartée : elle n'est pas reproductible. Chaque recréation du cluster impose de retaper les huit valeurs, sans trace de ce qui a été saisi et sans moyen de vérifier qu'elles sont les mêmes d'un cluster à l'autre. La VM du jalon `v0.1 - MVP deploye` (issues #40 et #41) ajoute un second environnement à tenir cohérent de cette manière.

### D. External Secrets Operator ou HashiCorp Vault

L'issue #39 cite ces deux solutions parmi les candidates.

Écartées pour les raisons déjà exposées, qui s'y appliquent en les cumulant. External Secrets Operator est un opérateur installé dans le cluster, comme en A, et ne stocke rien lui-même : il suppose un coffre externe, comme en B. Vault est un serveur supplémentaire à exploiter, avec son propre stockage et ses propres clés de descellement à sauvegarder, pour huit valeurs.

---

## Conséquences

### Positives

**La recréation d'un cluster devient reproductible.** Les valeurs sont dans le dépôt, sous forme chiffrée, et un déchiffrement suivi d'un `kubectl apply` reconstitue le même Secret sur n'importe quel cluster. Plus aucune valeur n'est retapée à la main.

**Les changements de secrets deviennent traçables.** Chaque modification du fichier chiffré est un commit. Le diff ne révèle pas les valeurs, mais il montre quelle clé a changé, quand, et dans quel commit.

**Aucun composant supplémentaire dans le cluster.** Le cluster reçoit un Secret Kubernetes ordinaire. Détruire ou recréer le cluster n'a aucun effet sur les secrets chiffrés ni sur leur clé.

**Les deux architectures sont couvertes** par les mêmes versions des deux outils.

### Négatives

**La clé privée age devient le secret unique à protéger.** Quiconque la détient peut lire tous les secrets du dépôt, et la perdre rend tous les secrets chiffrés illisibles. Il n'existe aucun moyen de récupération : les valeurs devraient alors être régénérées une par une auprès de Stripe, de Brevo et de PostgreSQL. La sauvegarde de cette clé doit donc être **une procédure écrite, pas une intention** : où la copie de sauvegarde est conservée, sur quel support distinct du poste de développement, et comment vérifier qu'elle permet effectivement de déchiffrer. Cette procédure fait partie de l'implémentation, et la décision n'est pas considérée comme implémentée sans elle.

**L'historique Git conserve toutes les versions chiffrées.** Retirer un secret du fichier ne le retire pas de l'historique. Si la clé privée venait à fuir, toutes les valeurs passées redeviendraient lisibles, pas seulement les valeurs actuelles. Une fuite de la clé imposerait donc de changer toutes les valeurs auprès de leurs fournisseurs, et pas seulement de chiffrer à nouveau le fichier avec une nouvelle clé.

**Le déploiement suppose deux outils sur le poste qui déploie.** SOPS et age doivent y être installés, dans les versions de référence, et la clé privée doit y être présente. Une étape manuelle disparaît, mais une dépendance d'outillage apparaît.

**Le modèle et la documentation changent de principe.** `k8s/02-secrets.example.yaml` affirmait que les secrets ne sont jamais versionnés, et le README décrivait la création du Secret par `kubectl create secret`. Traité le 25/09/2026 lors de l'implémentation : le README a été réécrit, et le fichier d'exemple supprimé, le fichier chiffré listant déjà les noms des clés.

### Réserves sur la portée

**Le chiffrement au repos du cluster reste souhaitable et complémentaire.** Cette décision protège les secrets **dans le dépôt**. Une fois déchiffrés et appliqués, ils redeviennent un Secret Kubernetes encodé en base64, conservé sans chiffrement dans le stockage du cluster (`etcd` sous kind) tant que le chiffrement au repos n'y est pas activé. Ce chiffrement répond à un autre risque, la lecture du stockage du cluster, et reste nécessaire quelle que soit la solution retenue pour le dépôt. Il fait partie des critères d'acceptation de l'issue #39 et n'est pas couvert par cet ADR.

**La rotation des secrets n'est pas traitée.** L'issue #39 demande qu'elle soit documentée. SOPS permet de chiffrer à nouveau un fichier pour une nouvelle clé, mais changer les valeurs elles-mêmes reste une opération menée auprès de chaque fournisseur.

**La CI ne déchiffre rien aujourd'hui.** Le workflow `ci.yml` n'utilise aucun secret : il reconstruit `.env` à partir de `.env.example` et génère à chaque exécution une `DJANGO_SECRET_KEY` et un `DB_PASSWORD` aléatoires. Les clés Stripe et Brevo n'y sont jamais nécessaires. Cette décision ne change rien à la CI. Si un job de déploiement y est ajouté (issue #43), il aura besoin de la clé privée age, qui deviendrait alors un secret GitHub, et donc une seconde copie de la clé à protéger.

---

## Critères de révision

Cette décision sera réexaminée si l'un des éléments suivants change :

- **Le projet passe en production réelle.** Stripe en mode live, clients réels : la journalisation des accès aux secrets et la rotation gérée par un coffre justifieraient Azure Key Vault (alternative B), et son coût.
- **Plusieurs personnes déploient.** SOPS peut chiffrer pour plusieurs clés publiques, mais chaque clé ajoutée est une clé privée de plus à protéger, et retirer l'accès d'une personne impose de changer les valeurs. Au-delà de quelques personnes, un coffre centralisé devient plus simple à gouverner.
- **Un cluster durable remplace le cluster jetable.** L'argument principal contre Sealed Secrets (alternative A) tient à la destruction régulière du cluster. Un cluster k3s stable, qui n'est plus recréé, affaiblirait cet argument.

---

## Liens

- Issues : #39 (gestion des secrets hors base64), #40 (VM Azure B2pts v2), #41 (k3s), #43 (registre d'images et job de déploiement)
- [ADR-002 — Kubernetes plutôt qu'un serveur unique](002-kubernetes.md) — conséquence négative « Les Secrets Kubernetes sont encodés en base64, pas chiffrés »
- `k8s/02-secrets.sops.yaml` et `k8s/overlays/production/secrets.sops.yaml` — les secrets chiffrés, un fichier par environnement
- `.sops.yaml` — règle de chiffrement et clé publique age
- README, section « Secrets (SOPS et age) » — installation des outils, application au cluster, restauration de la clé
- SOPS — <https://github.com/getsops/sops>
- age — <https://github.com/FiloSottile/age>

## Note sur Vault et la certification

L'issue #39 cite le module Vault d'une certification suivie en parallèle. Le besoin du projet, ne plus dépendre du seul base64, et le programme d'une formation sont deux choses distinctes : installer Vault ici reviendrait à choisir un outil pour une raison extérieure au projet. Vault suppose un serveur à déployer, sécuriser, sauvegarder et desceller après chaque redémarrage, pour huit secrets dans un cluster jetable.

L'apprentissage de Vault fait l'objet d'un exercice séparé, hors de ce dépôt.

## Addendum (26/09/2026)

Deux éléments du contexte d'origine ont changé, sans affecter la décision.

La cible d'hébergement n'est plus la VM Azure B2pts v2 en ARM64. La politique de régions du compte Azure for Students n'autorisait que cinq régions, dont aucune ne proposait de VM économique : les tailles disponibles y coûtaient environ 60 USD par mois, épuisant le crédit en six semaines. Le déploiement se fait désormais sur un VPS OVH (2 vCPU, 4 Go, datacenter en France), en architecture amd64. SOPS et age restant disponibles pour les deux architectures, le choix technique de cette décision tient sans changement ; l'argument ARM64 devient simplement sans objet.

Les secrets sont maintenant organisés par environnement, en cohérence avec la structure Kustomize (voir l'addendum de l'ADR-002) : `k8s/overlays/local/secrets.sops.yaml` pour le poste et `k8s/overlays/production/secrets.sops.yaml` pour la production. Les deux décrivent le même objet `dilane-shop-secrets`, chiffré pour la même clé age ; seules les valeurs diffèrent, la production portant de vraies clés Stripe de test et un mot de passe de base distinct. La règle `.sops.yaml` couvre les deux, son `path_regex` incluant les sous-répertoires.
