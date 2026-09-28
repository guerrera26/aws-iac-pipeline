resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# Access logging would add another bucket and ongoing storage cost that's
# disproportionate to this bucket's actual risk (it only holds
# Terraform-related project artifacts, fully blocked from public access
# below).
# tfsec:ignore:aws-s3-enable-bucket-logging
resource "aws_s3_bucket" "project_bucket" {
  bucket = "${var.project_name}-${random_id.bucket_suffix.hex}"

  tags = {
    Name = "${var.project_name}-bucket"
  }
}

resource "aws_s3_bucket_public_access_block" "project_bucket" {
  bucket = aws_s3_bucket.project_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "project_bucket" {
  bucket = aws_s3_bucket.project_bucket.id

  versioning_configuration {
    status = "Enabled"
  }
}

# SSE-S3 (AES256) is sufficient here; a customer-managed KMS key adds cost
# and rotation overhead this project's data doesn't need.
# tfsec:ignore:aws-s3-encryption-customer-key
resource "aws_s3_bucket_server_side_encryption_configuration" "project_bucket" {
  bucket = aws_s3_bucket.project_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
