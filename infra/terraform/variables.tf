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
