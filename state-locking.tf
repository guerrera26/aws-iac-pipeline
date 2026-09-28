# tfsec:ignore:aws-dynamodb-table-customer-key -- the AWS-owned default
# key is sufficient for a lock table that only ever holds lock-id metadata,
# never application data.
resource "aws_dynamodb_table" "terraform_locks" {
  name         = "${var.project_name}-tf-locks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "${var.project_name}-tf-locks"
  }
}
