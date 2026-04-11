locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

data "aws_vpc" "selected" {
  count   = var.vpc_id == null ? 1 : 0
  default = true
}

locals {
  selected_vpc_id = var.vpc_id == null ? data.aws_vpc.selected[0].id : var.vpc_id
}

data "aws_subnets" "default_in_vpc" {
  count = var.subnet_id == null ? 1 : 0

  filter {
    name   = "vpc-id"
    values = [local.selected_vpc_id]
  }
}

locals {
  selected_subnet_id = var.subnet_id == null ? data.aws_subnets.default_in_vpc[0].ids[0] : var.subnet_id
}

data "aws_ami" "ubuntu_2404" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_security_group" "web" {
  name        = "${local.name_prefix}-sg"
  description = "SSH from admin IP, HTTP/HTTPS from internet"
  vpc_id      = local.selected_vpc_id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${local.name_prefix}-sg"
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_instance" "app" {
  ami                         = data.aws_ami.ubuntu_2404.id
  instance_type               = var.instance_type
  subnet_id                   = local.selected_subnet_id
  vpc_security_group_ids      = [aws_security_group.web.id]
  key_name                    = var.ssh_key_name
  associate_public_ip_address = true

  root_block_device {
    volume_size = var.root_volume_size
    volume_type = "gp3"
  }

  user_data = base64encode(templatefile("${path.module}/bootstrap.sh", {
    git_repo_url      = var.git_repo_url
    django_secret_key = var.django_secret_key
    database_url      = var.database_url
    stripe_public_key = var.stripe_public_key
    stripe_secret_key = var.stripe_secret_key
    brevo_smtp_login  = var.brevo_smtp_login
    brevo_smtp_key    = var.brevo_smtp_key
    email_from        = var.email_from
    allowed_hosts     = var.allowed_hosts
  }))

  tags = {
    Name        = "${local.name_prefix}-ec2"
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_eip" "app" {
  domain   = "vpc"
  instance = aws_instance.app.id

  tags = {
    Name        = "${local.name_prefix}-eip"
    Project     = var.project_name
    Environment = var.environment
  }
}
