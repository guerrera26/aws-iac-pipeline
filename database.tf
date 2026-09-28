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

  # Learning-project settings — a production database would keep
  # deletion protection on and take a final snapshot.
  skip_final_snapshot = true
  deletion_protection = false
  multi_az            = false

  tags = {
    Name = "${var.project_name}-db"
  }
}
