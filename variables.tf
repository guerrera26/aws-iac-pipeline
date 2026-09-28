variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short name used to tag/prefix all resources"
  type        = string
  default     = "aws-devops-project"
}

variable "instance_type" {
  description = "EC2 instance type (t2.micro / t3.micro are free-tier eligible)"
  type        = string
  default     = "t3.micro"
}

variable "ssh_public_key" {
  description = "Your SSH public key content (e.g. contents of aws_devops_key.pub) — not a file path, so this works identically from a local machine or a CI runner"
  type        = string
}

variable "my_ip" {
  description = "Your public IP in CIDR notation, e.g. 71.23.45.6/32 — restricts SSH to just you"
  type        = string
}

variable "ci_ssh_public_key" {
  description = "Public half of the GitHub Actions deploy key. Baked into the instance's user_data (not the AWS key pair) so it's appended to authorized_keys on every boot — meaning it survives instance replacement automatically, unlike a one-off manual SSH step. Optional: left empty for local-only applies."
  type        = string
  default     = ""
}
