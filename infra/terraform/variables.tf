variable "project_name" {
  description = "Project prefix used for naming AWS resources"
  type        = string
  default     = "dilane-shop"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-3"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"
}

variable "root_volume_size" {
  description = "Root EBS volume size in GiB"
  type        = number
  default     = 8
}

variable "ssh_key_name" {
  description = "Existing EC2 Key Pair name (not .pem file path)"
  type        = string
}

variable "ssh_allowed_cidr" {
  description = "CIDR allowed to access SSH port 22"
  type        = string
}

variable "vpc_id" {
  description = "Optional VPC ID. Leave null to use default VPC"
  type        = string
  default     = null
}

variable "subnet_id" {
  description = "Optional subnet ID. Leave null to use first default subnet"
  type        = string
  default     = null
}

variable "git_repo_url" {
  description = "Git repository URL for the Django application"
  type        = string
  default     = "https://github.com/wankamdypuedilane/e-commerce.git"
}

variable "django_secret_key" {
  description = "Django SECRET_KEY for application security"
  type        = string
  sensitive   = true
}

variable "database_url" {
  description = "PostgreSQL connection string (postgresql://user:pass@host:5432/dbname)"
  type        = string
  sensitive   = true
}

variable "stripe_public_key" {
  description = "Stripe public key for payment processing"
  type        = string
  sensitive   = true
}

variable "stripe_secret_key" {
  description = "Stripe secret key for payment processing"
  type        = string
  sensitive   = true
}

variable "brevo_smtp_login" {
  description = "Brevo SMTP login for email sending"
  type        = string
  sensitive   = true
}

variable "brevo_smtp_key" {
  description = "Brevo SMTP password/key for email sending"
  type        = string
  sensitive   = true
}

variable "email_from" {
  description = "Email address for sending transactional emails"
  type        = string
}

variable "allowed_hosts" {
  description = "Comma-separated list of allowed hosts for Django"
  type        = string
}
