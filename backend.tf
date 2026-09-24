terraform {
  backend "s3" {
    bucket         = "aws-devops-project-125b3d32"
    key            = "terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "aws-devops-project-tf-locks"
  }
}
