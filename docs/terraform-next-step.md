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
