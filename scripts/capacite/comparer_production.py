#!/usr/bin/env python3
"""Vérifie que la surcouche de capacité reproduit la production.

Construit les deux surcouches avec `kubectl kustomize`, sans contacter aucun
cluster, puis compare, pour chaque charge de travail de la production
(Deployment, StatefulSet, Job, CronJob) :

- le nombre de replicas et la stratégie de mise à jour ;
- la classe de priorité ;
- pour chaque conteneur, y compris d'initialisation : image, politique de
  téléchargement, requêtes et limites de ressources ;

ainsi que la taille demandée par chaque PersistentVolumeClaim.

Les écarts voulus (domaine, Secrets, commande du Job de migration,
sauvegarde suspendue, Grafana sans SMTP) ne portent sur aucun de ces
champs : ils ne sont pas signalés. Tout autre écart l'est, et le script
sort alors avec le code 1.

Usage, depuis la racine du dépôt :
    python3 scripts/capacite/comparer_production.py
"""
import subprocess
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML est requis : python3 -m pip install pyyaml")

PRODUCTION = "k8s/overlays/production"
CAPACITE = "k8s/overlays/capacite"
CHARGES = {"Deployment", "StatefulSet", "Job", "CronJob"}


def rendre(surcouche):
    sortie = subprocess.run(
        ["kubectl", "kustomize", surcouche],
        check=True, capture_output=True, text=True,
    ).stdout
    return {
        (d["kind"], d["metadata"].get("namespace", ""), d["metadata"]["name"]): d
        for d in yaml.safe_load_all(sortie)
        if d
    }


def gabarit(objet):
    """Spécification du pod, quel que soit le type de charge."""
    spec = objet["spec"]
    if objet["kind"] == "CronJob":
        spec = spec["jobTemplate"]["spec"]
    return spec["template"]["spec"]


def empreinte(objet):
    """Champs qui doivent être identiques entre production et capacité."""
    if objet["kind"] == "PersistentVolumeClaim":
        return {"stockage": objet["spec"]["resources"]["requests"]["storage"]}
    pod = gabarit(objet)
    conteneurs = {}
    for groupe in ("initContainers", "containers"):
        for c in pod.get(groupe, []):
            conteneurs[f"{groupe}/{c['name']}"] = {
                "image": c.get("image"),
                "imagePullPolicy": c.get("imagePullPolicy"),
                "resources": c.get("resources"),
            }
    return {
        "replicas": objet["spec"].get("replicas"),
        "strategy": objet["spec"].get("strategy") or objet["spec"].get("updateStrategy"),
        "priorityClassName": pod.get("priorityClassName"),
        "conteneurs": conteneurs,
    }


def main():
    production, capacite = rendre(PRODUCTION), rendre(CAPACITE)
    ecarts = 0
    compares = 0
    for cle, objet in sorted(production.items()):
        if cle[0] not in CHARGES | {"PersistentVolumeClaim"}:
            continue
        nom = "/".join(filter(None, cle))
        if cle not in capacite:
            print(f"ABSENT de la capacité : {nom}")
            ecarts += 1
            continue
        compares += 1
        attendu, obtenu = empreinte(objet), empreinte(capacite[cle])
        if attendu != obtenu:
            ecarts += 1
            print(f"ÉCART : {nom}")
            print(f"  production : {attendu}")
            print(f"  capacité   : {obtenu}")
    if ecarts:
        print(f"{ecarts} écart(s) sur {compares} objet(s) comparé(s).")
        sys.exit(1)
    print(f"Identique à la production : {compares} objets comparés "
          "(replicas, stratégie, priorité, images, ressources, volumes).")


if __name__ == "__main__":
    main()
