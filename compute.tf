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

  # Appends the CI deploy key to ec2-user's authorized_keys at boot, via
  # cloud-init, so the CI key survives future instance replacement
  # automatically (a prior manual SSH step to add it was what originally
  # broke a deploy — this is the durable fix). Loaded from a template file
  # for readability rather than an inline heredoc.
  user_data = templatefile("${path.module}/templates/user_data.sh.tpl", {
    ci_ssh_public_key = var.ci_ssh_public_key
  })

  # Critical: cloud-init only ever runs user-data ONCE per instance ID.
  # Without this, the AWS provider applies a user_data change by stopping,
  # modifying, and restarting the SAME instance (same instance ID, same
  # disk) rather than replacing it — so cloud-init sees "already ran for
  # this instance" and silently skips the script forever, even though the
  # attribute genuinely changed. This forces a real destroy+recreate on any
  # user_data change, guaranteeing cloud-init actually executes it.
  user_data_replace_on_change = true

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
