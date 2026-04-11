output "instance_id" {
  value       = aws_instance.app.id
  description = "EC2 instance ID"
}

output "public_ip" {
  value       = aws_eip.app.public_ip
  description = "Public IP to use for SSH and DNS A record"
}

output "public_dns" {
  value       = aws_instance.app.public_dns
  description = "Public DNS name of EC2"
}

output "security_group_id" {
  value       = aws_security_group.web.id
  description = "Security group ID"
}
