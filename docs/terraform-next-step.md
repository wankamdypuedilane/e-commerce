> **Document obsolète — ne pas suivre.**
>
> Cette liste de tâches prépare une infrastructure AWS qui n'existe plus :
> le compte AWS est fermé, l'instance EC2 est supprimée et
> `infra/terraform/` n'est conservé qu'à titre d'archive. Aucune de ces
> étapes ne peut être exécutée.
>
> Le déploiement passe désormais par Kubernetes (`k8s/`, voir
> `docs/adr/002-kubernetes.md`). La cible d'hébergement est une VM Azure
> avec k3s (issues #40 et #41).
>
> Conservé à titre documentaire. Voir la section 5 de `docs/ARCHITECTURE.md`.

---

Terraform next step checklist

1. Validate locally

- cd infra/terraform
- terraform init
- terraform plan

2. Apply in sandbox first

- terraform apply
- verify security group, EC2, and Elastic IP

3. Decide migration strategy

- Keep current manual EC2 and create a parallel new one with Terraform
- Or import existing resources into Terraform state (advanced)

4. Production hardening after first apply

- Use S3 backend + DynamoDB lock
- Add Route53 records
- Add CloudWatch alarms
- Add RDS PostgreSQL
