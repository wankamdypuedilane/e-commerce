# Déploiement en production — du serveur nu au site en HTTPS

Procédure complète et rejouable du déploiement de Dilane Shop sur un VPS. Elle décrit ce qui a été réellement exécuté le **26/09/2026**, dans l'ordre, et suffit à reconstruire l'installation depuis un serveur neuf si le VPS est perdu.

Chaque bloc de commandes est marqué **PORTABLE** ou **SERVEUR** selon la machine où il s'exécute.

## Ce qui tourne aujourd'hui

| Élément | Valeur |
|---|---|
| Hébergeur | OVH, formule VPS-1 — 2 vCPU, 4 Go de mémoire, Gravelines, environ 5,39 € par mois |
| Système | Ubuntu 24.04, architecture `amd64` |
| Kubernetes | k3s v1.36.4+k3s1, sans Traefik |
| Entrée HTTP | ingress-nginx v1.15.1, variante `baremetal`, corrigé en `hostPort` |
| Certificats | cert-manager v1.16.2, Let's Encrypt |
| Image | `ghcr.io/wankamdypuedilane/dilane-shop`, paquet public, déployée par empreinte de commit |
| Domaine | `dilane-shop.store`, chez Amen |
| Sauvegarde | CronJob `sauvegarde-postgres`, `pg_dump` quotidien à 03h00, 7 sauvegardes, sur le disque du VPS |
| Supervision | Prometheus et Grafana, namespace `observabilite`, alertes par courriel — voir [observabilite.md](observabilite.md) |

### Variables utilisées dans ce document

Les commandes reprennent ces variables plutôt que les valeurs en dur. Définissez-les dans chaque terminal, ou remplacez-les à la lecture.

**PORTABLE**

```bash
IP_VPS=146.59.153.81          # adresse publique du VPS, change si le VPS est recréé
DOMAINE=dilane-shop.store
HOTE_SSH=dilane-shop          # alias défini dans ~/.ssh/config à l'étape 2
UTILISATEUR=ubuntu            # compte non-root du VPS
```

---

## 1. Prérequis

### Comptes et accès

- un compte OVH permettant de commander un VPS ;
- le domaine `dilane-shop.store`, enregistré chez Amen, avec accès à sa zone DNS ;
- le dépôt `wankamdypuedilane/e-commerce` sur GitHub. Il est **public** : aucun jeton n'est nécessaire pour le cloner, ni pour tirer l'image depuis GHCR.

### Outils sur le portable

**PORTABLE**

```bash
kubectl version --client       # série 1.37 utilisée ici
sops --version                # v3.13.3
age --version                 # v1.3.2
git --version
```

L'installation de sops et age est décrite dans le README, section « Secrets (SOPS et age) ».

### La clé age

Le déchiffrement des secrets exige la clé privée age, dans `~/.config/sops/age/keys.txt`. **Elle ne va jamais sur le serveur** : voir l'étape 6 et les points de vigilance.

Vérifiez qu'elle est en place et qu'elle correspond bien au destinataire déclaré dans `.sops.yaml` :

```bash
age-keygen -y ~/.config/sops/age/keys.txt
grep 'age:' .sops.yaml
```

Les deux doivent afficher la même clé publique. Si la clé a été perdue, restaurez-la depuis une sauvegarde avant d'aller plus loin : sans elle, aucun secret ne peut être appliqué et la procédure s'arrête à l'étape 6. La restauration est décrite dans le README.

### La clé SSH

Une paire Ed25519 dédiée au projet. Si elle n'existe pas encore :

**PORTABLE**

```bash
ssh-keygen -t ed25519 -f ~/.ssh/dilane-shop-vps -C "dilane-shop-vps"
```

La clé publique `~/.ssh/dilane-shop-vps.pub` sera déposée sur le VPS à la commande, ou ajoutée ensuite.

---

## 2. Provisionnement et durcissement du VPS

### 2.1 Commander le VPS

Dans l'espace client OVH : formule **VPS-1**, image **Ubuntu 24.04**, centre de données **Gravelines**, et la clé publique `dilane-shop-vps.pub` déposée à la création. OVH crée un compte `ubuntu` disposant de `sudo`, et communique l'adresse publique de la machine.

Reportez cette adresse dans `IP_VPS`.

### 2.2 Première connexion

**PORTABLE**

```bash
ssh -i ~/.ssh/dilane-shop-vps $UTILISATEUR@$IP_VPS
```

Créez ensuite un alias pour ne plus répéter la clé ni l'adresse :

**PORTABLE** — dans `~/.ssh/config`

```text
Host dilane-shop
    HostName 146.59.153.81
    User ubuntu
    IdentityFile ~/.ssh/dilane-shop-vps
    IdentitiesOnly yes
```

```bash
ssh $HOTE_SSH "hostname; lsb_release -ds; uname -m"
```

Attendu : le nom de la machine, `Ubuntu 24.04...`, et `x86_64`.

### 2.3 Mettre le système à jour

**SERVEUR**

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo reboot
```

### 2.4 Durcir l'accès SSH

Deux fichiers sont en jeu, et l'ordre de lecture est le piège principal de cette étape.

`/etc/ssh/sshd_config` commence par une directive `Include /etc/ssh/sshd_config.d/*.conf`. Les fichiers de ce répertoire sont lus **par ordre alphabétique**, et dans la configuration de sshd **la première valeur rencontrée pour une option l'emporte**. L'image Ubuntu d'OVH fournit `50-cloud-init.conf`, qui contient `PasswordAuthentication yes` : un fichier `99-durcissement.conf` ajouté ensuite serait lu **après**, donc ignoré pour cette option. Il faut donc corriger le fichier de cloud-init en plus d'écrire le sien.

**SERVEUR** — écrire le fichier de durcissement

```bash
sudo tee /etc/ssh/sshd_config.d/99-durcissement.conf >/dev/null <<'EOF'
# Durcissement SSH — voir docs/deploiement-production.md
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
PermitEmptyPasswords no
X11Forwarding no
MaxAuthTries 3
EOF
```

**SERVEUR** — neutraliser la directive contraire de cloud-init

```bash
sudo grep -n PasswordAuthentication /etc/ssh/sshd_config.d/50-cloud-init.conf
sudo sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' \
  /etc/ssh/sshd_config.d/50-cloud-init.conf
```

**SERVEUR** — vérifier avant de redémarrer le service

```bash
sudo sshd -t && echo "configuration valide"
sudo sshd -T | grep -E '^(permitrootlogin|passwordauthentication|pubkeyauthentication)'
```

Attendu : `permitrootlogin no`, `passwordauthentication no`, `pubkeyauthentication yes`. `sshd -T` affiche la configuration **effective**, après résolution de l'ordre des fichiers : c'est elle qui compte, pas le contenu des fichiers pris séparément.

```bash
sudo systemctl restart ssh
```

> **Gardez la session en cours ouverte** et vérifiez une nouvelle connexion depuis un autre terminal avant de la fermer. Une erreur de configuration SSH sur un serveur distant se répare autrement que par SSH.

**PORTABLE** — depuis un second terminal

```bash
ssh $HOTE_SSH "echo connexion par clé opérationnelle"
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no $HOTE_SSH true
```

La première commande doit réussir, la seconde échouer avec `Permission denied`.

---

## 3. Installation de k3s

**SERVEUR**

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable traefik --write-kubeconfig-mode 644" sh -
```

Les deux options sont délibérées :

- `--disable traefik` : k3s installe Traefik par défaut. Les manifestes du dépôt déclarent `ingressClassName: nginx` et des annotations `nginx.ingress.kubernetes.io/*`, que Traefik ignore. C'est ingress-nginx qui est installé à l'étape 4.
- `--write-kubeconfig-mode 644` : rend `/etc/rancher/k3s/k3s.yaml` lisible par le compte `ubuntu`, sans `sudo`.

**SERVEUR** — vérifier

```bash
sudo systemctl is-active k3s
sudo k3s kubectl get nodes
sudo k3s kubectl version --short
```

Attendu : `active`, un nœud `Ready`, et la version `v1.36.4+k3s1`.

### 3.1 Rendre kubectl utilisable, y compris par SSH non interactif

k3s installe `kubectl`, mais celui-ci lit `~/.kube/config` par défaut, pas le fichier de k3s. Copier le kubeconfig dans l'emplacement standard est préférable à un `export KUBECONFIG` dans `~/.bashrc` : **une commande lancée par `ssh hôte "commande"` ouvre un shell non interactif, qui n'exécute pas `~/.bashrc`**. Sans cette copie, l'injection des secrets de l'étape 6 échouerait sur un « connection refused ».

**SERVEUR**

```bash
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown "$USER:$USER" ~/.kube/config
chmod 600 ~/.kube/config
```

**PORTABLE** — vérifier le cas qui compte

```bash
ssh $HOTE_SSH "kubectl get nodes"
```

Cette commande doit répondre. C'est le prérequis exact de l'étape 6.

---

## 4. Entrée HTTP et certificats

### 4.1 ingress-nginx, variante baremetal

**SERVEUR**

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.15.1/deploy/static/provider/baremetal/deploy.yaml
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=180s
```

### 4.2 Le correctif `hostPort` — point critique

**C'est le réglage le plus important de cette procédure, et le seul qui ne soit pas versionné dans le dépôt.** Sans lui, le site ne répond pas, alors que tous les pods sont `Running`.

La variante `baremetal` crée un Service de type **NodePort** et son Deployment ne déclare **aucun** `hostPort` : le contrôleur n'écoute que sur des ports attribués dans la plage 30000-32767. Rien n'écoute sur les ports 80 et 443 de l'interface publique du VPS. Ce manifeste suppose un équilibreur de charge externe, qui n'existe pas ici.

Le correctif attache les ports 80 et 443 du nœud directement au pod du contrôleur :

**SERVEUR**

```bash
kubectl patch deployment ingress-nginx-controller -n ingress-nginx --type=strategic -p \
'{"spec":{"template":{"spec":{"containers":[{"name":"controller","ports":[
  {"containerPort":80,"hostPort":80,"name":"http","protocol":"TCP"},
  {"containerPort":443,"hostPort":443,"name":"https","protocol":"TCP"}
]}]}}}}'

kubectl rollout status deployment ingress-nginx-controller -n ingress-nginx --timeout=180s
```

Le correctif de fusion utilise `containerPort` comme clé : il ajoute `hostPort` aux deux ports existants sans toucher au port 8443 du webhook d'admission. Le nom `controller` est celui du conteneur dans le manifeste `baremetal` : s'il changeait dans une version ultérieure, le correctif ajouterait un second conteneur au lieu de modifier celui-ci.

Conséquence à connaître : un port du nœud ne peut être pris que par un pod à la fois. Le contrôleur reste donc à un seul exemplaire par nœud — c'est ce que déclare le manifeste `baremetal`, qui ne fixe pas de nombre de répliques et s'en tient donc à une. Augmenter ce nombre sur un cluster à un nœud laisserait le second pod en attente, faute de port libre.

**SERVEUR** — vérifier que le nœud écoute bien

```bash
kubectl get deployment ingress-nginx-controller -n ingress-nginx \
  -o jsonpath='{.spec.template.spec.containers[0].ports}'; echo
sudo ss -tlnp | grep -E ':(80|443)\s'
```

Attendu : `hostPort: 80` et `hostPort: 443` dans le premier retour, et deux lignes en écoute dans le second.

> Ce correctif est appliqué à une ressource installée depuis une URL externe : **il est perdu à chaque réinstallation du contrôleur** et doit être rejoué. Voir « Ce qui reste manuel ».

### 4.3 cert-manager

**SERVEUR**

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml
kubectl wait --namespace cert-manager \
  --for=condition=available deployment --all --timeout=180s
```

cert-manager doit être installé **avant** la surcouche de production : celle-ci déclare un `Certificate` et deux `ClusterIssuer`, types qui n'existent pas tant que cert-manager n'a pas enregistré ses définitions de ressources.

---

## 5. DNS

Chez Amen, dans la zone de `dilane-shop.store` :

| Type | Nom | Valeur |
|---|---|---|
| `A` | `dilane-shop.store` (racine, parfois notée `@`) | l'adresse publique du VPS, soit `IP_VPS` |
| `CNAME` | `www` | `dilane-shop.store.` |

**PORTABLE** — vérifier la propagation avant de demander un certificat

```bash
getent hosts $DOMAINE
curl -sS -o /dev/null -w "%{http_code}\n" http://$DOMAINE/ --max-time 20
```

La résolution doit renvoyer `IP_VPS`. Tant que le nom ne résout pas vers le VPS, la validation HTTP01 de Let's Encrypt échouera à l'étape 7.

> **Le sous-domaine `www` n'est pas servi.** L'enregistrement existe et résout, mais l'Ingress ne déclare que `dilane-shop.store`, le certificat ne couvre que ce nom, et `DJANGO_ALLOWED_HOSTS` ne contient pas `www.dilane-shop.store`. Une visite de `https://www.dilane-shop.store/` obtient le certificat par défaut du contrôleur, donc un avertissement du navigateur. Voir les points à décider.

---

## 6. Déploiement de l'application

### 6.1 Récupérer le dépôt sur le serveur

`kubectl apply -k` a besoin des fichiers du dépôt. Le dépôt étant public, un clone suffit ; il ne contient aucun secret en clair.

**SERVEUR**

```bash
git clone https://github.com/wankamdypuedilane/e-commerce.git ~/e-commerce
cd ~/e-commerce
git rev-parse --short HEAD
```

Pour rejouer une version précise plutôt que la dernière : `git checkout <empreinte>`. L'étiquette de l'image déployée est figée dans `k8s/overlays/production/kustomization.yaml`, donc solidaire du commit sorti.

### 6.2 Le namespace

Il doit exister avant le Secret.

**SERVEUR**

```bash
kubectl apply -f ~/e-commerce/k8s/base/00-namespace.yaml
```

### 6.3 Les secrets — déchiffrés sur le portable, injectés par SSH

**La clé privée age ne quitte jamais le portable.** Le fichier est déchiffré localement et le résultat est transmis à `kubectl` sur le serveur à travers le tunnel SSH, sans jamais toucher un disque : ni copie en clair sur le portable, ni clé de déchiffrement sur le serveur.

Si le VPS était compromis, l'attaquant obtiendrait les secrets du cluster — ils y sont de toute façon, encodés en base64 — mais **pas la clé qui déchiffre tous les secrets du dépôt, présents et passés**. Installer la clé age sur le serveur pour y lancer `sops` aurait échangé cette garantie contre une commande plus courte.

**PORTABLE** — depuis la racine du dépôt

```bash
sops --decrypt k8s/overlays/production/secrets.sops.yaml | ssh $HOTE_SSH "kubectl apply -f -"
```

Attendu : `secret/dilane-shop-secrets created`.

**SERVEUR** — vérifier les huit clés, sans afficher les valeurs

```bash
kubectl get secret dilane-shop-secrets -n dilane-shop \
  -o jsonpath='{range $k,$v := .data}{$k}{"\n"}{end}'
```

### 6.4 Appliquer la surcouche de production

**SERVEUR**

```bash
cd ~/e-commerce
kubectl apply -k k8s/overlays/production
```

Une seule commande applique la configuration, PostgreSQL, le Job de migration, Django, l'Ingress, les deux `ClusterIssuer` et le `Certificate`. Pour voir ce qui sera appliqué sans rien envoyer : `kubectl kustomize k8s/overlays/production`.

**SERVEUR** — suivre le démarrage

```bash
kubectl wait -n dilane-shop --for=condition=ready pod \
  -l app.kubernetes.io/name=postgres --timeout=300s
kubectl wait -n dilane-shop --for=condition=complete job/django-migrate --timeout=300s
kubectl rollout status -n dilane-shop deploy/django --timeout=300s
kubectl get pods -n dilane-shop
```

> **L'ordre de démarrage n'est pas garanti.** `apply -k` envoie tous les objets d'un bloc : le Job de migration démarre avant que PostgreSQL ne réponde, et repose sur son `backoffLimit: 3`, soit quatre tentatives, pour y parvenir. Sur un volume neuf, PostgreSQL doit s'initialiser, ce qui peut dépasser ce délai. Si le Job a échoué :
>
> ```bash
> kubectl logs -n dilane-shop job/django-migrate
> kubectl delete job django-migrate -n dilane-shop --ignore-not-found
> kubectl apply -k k8s/overlays/production
> ```
>
> Le `spec.template` d'un Job est immuable : supprimez-le toujours avant de le réappliquer.

---

## 7. Certificat Let's Encrypt

La surcouche déclare deux `ClusterIssuer` : `letsencrypt-test`, qui interroge l'environnement de test de Let's Encrypt, et `letsencrypt-production`. L'environnement de production limite fortement le nombre de tentatives échouées par domaine et par semaine ; celui de test n'a pas cette limite, mais son certificat n'est pas reconnu par les navigateurs.

### 7.1 Valider la chaîne avec l'environnement de test

Sur une installation neuve, mettez d'abord l'`issuerRef` du `Certificate` sur `letsencrypt-test`, dans `k8s/overlays/production/tls.yaml`, puis appliquez. Cette étape éprouve tout le chemin — DNS, port 80, `hostPort`, solveur HTTP01, Ingress — sans consommer de quota.

**SERVEUR**

```bash
kubectl get certificate -n dilane-shop
kubectl describe certificate dilane-shop-tls -n dilane-shop | tail -20
```

`READY` doit passer à `True`, en une à deux minutes. En cas de blocage, l'objet `Challenge` porte la raison :

```bash
kubectl get challenges -n dilane-shop
kubectl describe challenge -n dilane-shop
```

Vérifiez ensuite que le site répond en HTTPS, en acceptant le certificat de test :

**PORTABLE**

```bash
curl -k -sS -o /dev/null -w "%{http_code}\n" https://$DOMAINE/
```

### 7.2 Basculer sur l'environnement de production

Une émission de test réussie constatée, changez l'`issuerRef` du `Certificate` — c'est l'état actuel du dépôt, `letsencrypt-production` — puis forcez une nouvelle demande en supprimant le Secret existant :

**SERVEUR**

```bash
kubectl apply -k k8s/overlays/production
kubectl delete secret tls-dilane-shop -n dilane-shop
kubectl get certificate -n dilane-shop -w      # Ctrl+C quand READY vaut True
```

**PORTABLE** — vérifier l'émetteur

```bash
echo | openssl s_client -connect $DOMAINE:443 -servername $DOMAINE 2>/dev/null \
  | openssl x509 -noout -issuer -subject -dates
```

Attendu : un `issuer` mentionnant `O=Let's Encrypt` **sans** la mention `(STAGING)`, le `subject` `CN=dilane-shop.store`, et une validité de 90 jours. Relevé le 26/09/2026 : valable jusqu'au 25/12/2026.

---

## 8. Données

### 8.1 Le catalogue de démonstration

**SERVEUR**

```bash
kubectl exec -n dilane-shop deploy/django -- \
  python manage.py loaddata fixtures/demo-catalogue.json
```

Attendu : `Installed 30 object(s) from 1 fixture(s)` — 5 catégories et 25 produits. La fixture est embarquée dans l'image.

### 8.2 Le compte administrateur

Cette commande est interactive et demande un TTY, d'où `-it`.

**SERVEUR**

```bash
kubectl exec -it -n dilane-shop deploy/django -- python manage.py createsuperuser
```

Aucun compte n'est créé automatiquement : après une réinstallation, l'administration reste inaccessible jusqu'à cette étape.

---

## 9. Vérifications finales

**PORTABLE**

```bash
# 1. HTTP redirige vers HTTPS
curl -sS -o /dev/null -w "HTTP  : %{http_code} -> %{redirect_url}\n" http://$DOMAINE/

# 2. HTTPS répond, certificat reconnu sans -k
curl -sS -o /dev/null -w "HTTPS : %{http_code}\n" https://$DOMAINE/

# 3. L'application joint sa base
curl -sS https://$DOMAINE/healthz/; echo

# 4. Émetteur et validité du certificat
echo | openssl s_client -connect $DOMAINE:443 -servername $DOMAINE 2>/dev/null \
  | openssl x509 -noout -issuer -dates
```

Résultats attendus, tels que relevés le 26/09/2026 :

| Vérification | Attendu |
|---|---|
| HTTP | `308` vers `https://dilane-shop.store/` |
| HTTPS | `200`, sans `-k` |
| `/healthz/` | `{"status": "ok", "database": "reachable"}` |
| Émetteur | `O=Let's Encrypt`, sans `(STAGING)` |

**SERVEUR** — état du cluster

```bash
kubectl get pods,svc,ingress,certificate -n dilane-shop
kubectl get pods -n ingress-nginx
kubectl logs -n dilane-shop deploy/django --tail=20
```

Attendu : deux pods `django` en `Running` et `1/1`, un pod `postgres-0`, le Job de migration terminé ou déjà supprimé par son `ttlSecondsAfterFinished`, et le certificat `READY=True`.

---

## 10. Points de vigilance

### Le correctif `hostPort` n'est pas versionné

C'est la fragilité principale de cette installation. Le correctif de l'étape 4.2 est appliqué à un Deployment installé depuis une URL externe : il ne figure nulle part dans le dépôt et **disparaît à chaque réinstallation ou mise à jour d'ingress-nginx**. Le symptôme est déroutant : tous les pods sont `Running`, et le site ne répond plus. Le réflexe à avoir :

```bash
kubectl get deployment ingress-nginx-controller -n ingress-nginx \
  -o jsonpath='{.spec.template.spec.containers[0].ports}'; echo
```

Si `hostPort` n'y figure pas, rejouez l'étape 4.2.

### La clé age reste hors du serveur

Aucune étape n'installe sops ni la clé age sur le VPS, et c'est voulu. Toute procédure future touchant aux secrets doit conserver cette propriété : déchiffrer sur le portable, transmettre par SSH. La perte de la clé, elle, rend illisibles tous les secrets chiffrés du dépôt : deux sauvegardes hors du poste, et la restauration décrite dans le README.

### L'ordre des migrations n'est pas garanti

Rappel de l'étape 6.4 : `apply -k` n'ordonne pas les objets. Après chaque changement de schéma, supprimez le Job avant de le réappliquer, et lisez ses journaux plutôt que de supposer sa réussite.

### Renouvellement du certificat

cert-manager renouvelle automatiquement, `renewBefore` étant fixé à 360 heures, soit 15 jours avant l'expiration. Rien n'est à faire tant que trois conditions tiennent : le `A` pointe toujours vers le VPS, le port 80 reste joignable depuis Internet — donc le correctif `hostPort` en place — et cert-manager tourne. Un renouvellement échoué est silencieux du point de vue du visiteur jusqu'à l'expiration.

Contrôle ponctuel :

```bash
kubectl get certificate -n dilane-shop
kubectl get certificaterequests -n dilane-shop
```

Let's Encrypt envoie par ailleurs un avertissement à l'adresse déclarée dans les `ClusterIssuer`.

### Les sauvegardes restent sur le VPS

PostgreSQL écrit dans un volume fourni par la classe de stockage par défaut de k3s, `local-path`, c'est-à-dire **sur le disque du VPS**. Depuis le 27/09/2026 (`0fba9d2`), un CronJob sauvegarde la base chaque nuit (`k8s/base/09-backup-cronjob.yaml`) : `pg_dump` à 03h00, heure de Paris, 7 sauvegardes conservées. Mais ces sauvegardes sont écrites, elles aussi, par `local-path` sur le disque du VPS : elles protègent d'une erreur logique, pas de la perte de la machine, qui emporterait la base et ses sauvegardes. Un échec de sauvegarde ne déclenche aucune alerte. C'est la dette 2.5 de l'audit, suivie par l'issue #83.

### Changer `DB_PASSWORD` ne suffit pas

PostgreSQL ne lit `POSTGRES_PASSWORD` qu'à l'initialisation d'un volume vide. Modifier la valeur dans le Secret d'un cluster déjà en service ne change pas le mot de passe de la base : Django ne pourra plus s'y connecter tant que le changement n'est pas fait aussi dans PostgreSQL.

### Les variables d'environnement sont lues au démarrage

Après un changement de configuration ou de secret, redémarrez les pods concernés :

```bash
kubectl rollout restart -n dilane-shop deploy/django
```

---

## Mettre à jour l'application

Le cycle courant, une fois l'installation en place.

**PORTABLE**

```bash
git log --oneline -1 origin/main        # empreinte à déployer
```

Reportez-la dans `newTag` de `k8s/overlays/production/kustomization.yaml`, commitez, poussez — la CI publie l'image sous cette empreinte.

**SERVEUR**

```bash
cd ~/e-commerce && git pull --ff-only
kubectl delete job django-migrate -n dilane-shop --ignore-not-found
kubectl apply -k k8s/overlays/production
kubectl wait -n dilane-shop --for=condition=complete job/django-migrate --timeout=300s
kubectl rollout status -n dilane-shop deploy/django
```

Revenir en arrière consiste à remettre l'empreinte précédente et à rejouer ces commandes. C'est ce que l'étiquetage par empreinte de commit, plutôt que `latest`, rend possible.

---

## Ce qui reste manuel, et mériterait d'être automatisé

| Élément | Situation | Piste |
|---|---|---|
| **Correctif `hostPort`** | Réglage manuel, hors dépôt, perdu à chaque réinstallation du contrôleur | Le versionner comme les autres manifestes, à l'image de `k8s/overlays/local/07-ingress-controller-patch.yaml`. Ou passer par `ServiceLB`, l'équilibreur intégré de k3s, qui expose un Service de type `LoadBalancer` sur les ports du nœud sans correctif — à éprouver, c'est un changement de mécanisme. |
| **Installation de k3s, ingress-nginx, cert-manager** | Trois commandes manuelles, avec des versions écrites à la main | Un script d'installation versionné, ou Terraform, ce qui reprendrait la démarche du Sprint 6 sans son défaut : un script relu et exécuté à l'identique. |
| **Durcissement SSH** | Deux fichiers édités à la main, dont un fichier de cloud-init à corriger | `cloud-init` à la création du VPS, ou Ansible |
| **Déploiement** | `git pull` puis `apply -k` à la main sur le serveur | Un workflow de déploiement, issue #43 — qui suppose de décider où vit la clé du cluster |
| **Provisionnement du VPS** | Commande manuelle dans l'espace client OVH | Terraform, fournisseur OVH |
| **Sauvegarde de la base** | CronJob quotidien, sauvegardes sur le disque du VPS | Les sortir du serveur, alerter en cas d'échec : issue #83 |
| **Pare-feu** | Non configuré dans cette procédure | À décider : voir ci-dessous |

---

## Points à vérifier ou à décider

1. **Pare-feu.** Aucune règle n'est posée par cette procédure. Un VPS exposé le justifierait, mais k3s a besoin de ports internes — 6443 pour l'API, 10250 pour les kubelets, 8472 en UDP pour le réseau Flannel — et une règle `ufw` mal posée coupe le cluster ou l'accès SSH. À traiter comme une étape à part entière, éprouvée.
2. **Le sous-domaine `www`.** Le `CNAME` existe et résout vers le VPS, mais rien ne le sert : le visiteur obtient le certificat par défaut du contrôleur et un avertissement. Trois choix : l'ajouter à l'Ingress, au `Certificate` et à `DJANGO_ALLOWED_HOSTS` ; poser une redirection vers le domaine racine ; ou retirer l'enregistrement DNS.
3. **L'accès `kubectl` depuis le portable.** Cette procédure exécute `kubectl` sur le serveur, avec le dépôt cloné dessus. Une variante évite ce clone en générant les manifestes localement : `kubectl kustomize k8s/overlays/production | ssh dilane-shop "kubectl apply -f -"`, sur le modèle de l'injection des secrets. À arbitrer selon que vous préférez tenir un clone à jour sur le serveur, ou tout piloter depuis le portable.
4. **Les commentaires de `k8s/overlays/production/tls.yaml`** décrivent encore l'état antérieur à la bascule : ils annoncent un email à remplir et une bascule à effectuer, tous deux faits. À rafraîchir.
5. **L'adresse dans `~/.ssh/config`.** Le bloc de l'étape 2.2 porte l'adresse actuelle en dur. Si le VPS est recréé, elle change : c'est le premier endroit à corriger.
6. **La date de reprise de ce document.** Les versions y sont écrites en dur : k3s v1.36.4+k3s1, ingress-nginx v1.15.1, cert-manager v1.16.2. Rejouer la procédure des mois plus tard installera peut-être autre chose ; les URLs sont épinglées, donc reproductibles, mais à confronter aux versions alors prises en charge.
7. **Le compte administrateur** créé à l'étape 8.2 n'est pas inventorié. Décidez où sa trace est conservée — pas dans ce dépôt.

## Pare-feu — fermeture de l'API Kubernetes (26/09/2026)

Par défaut, k3s expose son API (6443) et le kubelet (10250) sur toutes les
interfaces, donc sur Internet. Le cluster étant piloté depuis le serveur ou
par SSH, ces ports n'ont aucune raison d'être joignables de l'extérieur.

Deux règles iptables les bloquent sur l'interface publique (ens3), sans
toucher au trafic interne de k3s ni au port SSH. ufw est écarté : il entre
en conflit avec le réseau de k3s. Les règles sont rendues permanentes par
iptables-persistent (qui désinstalle ufw au passage).

```bash
# SERVEUR — interface publique = ens3 (vérifier avec : ip route get 1.1.1.1)
sudo iptables -I INPUT -i ens3 -p tcp --dport 6443 -j DROP
sudo iptables -I INPUT -i ens3 -p tcp --dport 10250 -j DROP
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent
sudo netfilter-persistent save
```

Vérification, depuis un poste extérieur :
- `6443` doit être injoignable (connexion refusée ou expirée).
- SSH (22) et le site (80/443) doivent répondre normalement.

k3s n'écoute pas ces ports en IPv6 : aucune règle ip6tables n'est nécessaire.
