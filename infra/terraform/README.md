Terraform starter for AWS EC2 deployment

What this provisions:

- 1 Ubuntu 24.04 EC2 instance
- 1 security group (SSH restricted + HTTP/HTTPS public)
- 1 Elastic IP attached to the instance

Important:

- This creates NEW infrastructure. It does not automatically import your existing EC2.
- Use this first in a sandbox account or workspace.

Prerequisites:

1. Terraform >= 1.6
2. AWS credentials configured (aws configure or environment variables)
3. Existing EC2 key pair in AWS (key pair name, not local pem path)

Usage:

1. cd infra/terraform
2. cp terraform.tfvars.example terraform.tfvars
3. Edit terraform.tfvars
4. terraform init
5. terraform plan
6. terraform apply

After apply:

- Read output public_ip
- Point DNS A record to that IP
- Deploy app as usual (or automate with Ansible later)

Destroy (careful):

- terraform destroy

Suggested next steps:

- Add Route53 records in Terraform
- Add S3 backend + DynamoDB lock for team-safe state
- Add AWS RDS Postgres instead of local Postgres on EC2
