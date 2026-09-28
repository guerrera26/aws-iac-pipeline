data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_key_pair" "deployer" {
  key_name   = "${var.project_name}-key"
  public_key = var.ssh_public_key
}

resource "aws_instance" "web" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.web.id]
  key_name               = aws_key_pair.deployer.key_name
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name

  # Appends the CI deploy key to ec2-user's authorized_keys at every boot.
  # This runs via cloud-init on first boot, so the CI key survives any
  # future instance replacement automatically — no manual SSH step needed
  # ever again (that manual step is what broke the last deploy).
  user_data = <<-EOF
    #!/bin/bash
    set -e
    mkdir -p /home/ec2-user/.ssh
    chmod 700 /home/ec2-user/.ssh
    CI_KEY='${var.ci_ssh_public_key}'
    if [ -n "$CI_KEY" ]; then
      echo "$CI_KEY" >> /home/ec2-user/.ssh/authorized_keys
      chown ec2-user:ec2-user /home/ec2-user/.ssh/authorized_keys
      chmod 600 /home/ec2-user/.ssh/authorized_keys
    fi
  EOF

  # Enforce IMDSv2 (mitigates SSRF-based credential theft)
  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
  }

  # Encrypt the root volume at rest
  root_block_device {
    encrypted = true
  }

  tags = {
    Name = "${var.project_name}-web"
  }
}
