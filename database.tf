# Auto-generated master password — never typed by a human, never committed,
# never passed through CI logs. Stored only in Terraform state (S3, encrypted)
# and in SSM Parameter Store (encrypted), fetched by the instance at runtime
# via its IAM role.
resource "random_password" "db_password" {
  length  = 24
  special = false # keep it simple for the connection string; still 24 random chars
}

resource "aws_ssm_parameter" "db_password" {
  name  = "/app/${var.project_name}/db_password"
  type  = "SecureString"
  value = random_password.db_password.result

  tags = {
    Name = "${var.project_name}-db-password"
  }
}

# tfsec:ignore:aws-rds-enable-iam-auth -- IAM database authentication
# would require reworking the app's connection code to fetch a short-lived
# auth token instead of a password; noted as a real future improvement,
# not implemented here given the time-boxed scope of this project.
# tfsec:ignore:aws-rds-enable-deletion-protection -- intentionally left
# off: this is a personal/learning environment that needs to be easy to
# `terraform destroy` in full, not a production database.
# tfsec:ignore:aws-rds-enable-performance-insights -- Performance Insights
# is a production-scale monitoring feature; not needed to observe a single
# low-traffic personal-project database.
resource "aws_db_instance" "postgres" {
  identifier     = "${var.project_name}-db"
  engine         = "postgres"
  engine_version = "16"
  instance_class = "db.t3.micro" # free-tier eligible

  allocated_storage = 20 # free-tier max
  storage_type      = "gp2"
  storage_encrypted = true

  db_name  = "appdb"
  username = "appadmin"
  password = random_password.db_password.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false

  # Keep at least one day of automated backups (free-tier eligible, and a
  # real, worthwhile safeguard even for a learning project).
  backup_retention_period = 1

  # Learning-project settings — a production database would keep
  # deletion protection on and take a final snapshot.
  skip_final_snapshot = true
  deletion_protection = false
  multi_az            = false

  tags = {
    Name = "${var.project_name}-db"
  }
}
