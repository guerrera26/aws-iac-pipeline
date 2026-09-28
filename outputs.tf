output "instance_public_ip" {
  description = "Public IP of the EC2 instance"
  value       = aws_instance.web.public_ip
}

output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.web.id
}

output "s3_bucket_name" {
  description = "Name of the S3 bucket"
  value       = aws_s3_bucket.project_bucket.bucket
}

output "ssh_command" {
  description = "Command to SSH into the instance (swap in your private key path)"
  value       = "ssh -i <path-to-your-private-key> ec2-user@${aws_instance.web.public_ip}"
}

output "security_group_id" {
  description = "ID of the security group, used by CI to temporarily open SSH for deployment"
  value       = aws_security_group.web.id
}

output "db_host" {
  description = "RDS Postgres endpoint (host only, no port)"
  value       = aws_db_instance.postgres.address
}

output "db_port" {
  description = "RDS Postgres port"
  value       = aws_db_instance.postgres.port
}

output "db_name" {
  description = "Database name"
  value       = aws_db_instance.postgres.db_name
}

output "db_user" {
  description = "Database master username"
  value       = aws_db_instance.postgres.username
}

output "db_password_ssm_param" {
  description = "SSM Parameter Store name holding the DB password (the app fetches it via IAM role at runtime)"
  value       = aws_ssm_parameter.db_password.name
}
