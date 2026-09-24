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
