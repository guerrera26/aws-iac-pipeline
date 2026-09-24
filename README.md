# AWS DevOps Project

A small but complete infrastructure-as-code pipeline: **Terraform** provisions AWS infrastructure, **Ansible** configures the resulting server, and **GitHub Actions** automates the whole thing on every push.

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │              AWS (us-east-1)             │
                    │                                           │
                    │   VPC (10.0.0.0/16)                       │
                    │   └── Public Subnet (10.0.1.0/24)         │
                    │        └── EC2 (t3.micro, Amazon Linux)   │
                    │             └── nginx (via Ansible)       │
                    │                                           │
                    │   S3 bucket  ── Terraform remote state    │
                    │   DynamoDB   ── Terraform state locking   │
                    └─────────────────────────────────────────┘
                              ▲
                              │ plan / apply
                    ┌─────────────────────┐
                    │  GitHub Actions CI   │  (on push to main)
                    └─────────────────────┘
```

## Structure

| File | Purpose |
|---|---|
| `providers.tf` | AWS + random provider configuration |
| `variables.tf` | Input variables (region, instance type, SSH key, allowed IP) |
| `network.tf` | VPC, subnet, internet gateway, routing, security group |
| `compute.tf` | AMI lookup, SSH key pair, EC2 instance |
| `storage.tf` | S3 bucket (public access blocked) |
| `state-locking.tf` | DynamoDB table for Terraform state locking |
| `backend.tf` | Remote state configuration (S3 + DynamoDB) |
| `outputs.tf` | Instance IP, ID, bucket name, SSH command |
| `ansible/` | Playbook + inventory that installs and configures nginx |
| `.github/workflows/terraform.yml` | CI/CD: format check, validate, plan on every push/PR, apply on merge to `main` |

## Running it locally

1. Install [Terraform](https://developer.hashicorp.com/terraform/downloads) and the [AWS CLI](https://aws.amazon.com/cli/)
2. `aws configure` with an IAM user's access key (scoped to `PowerUserAccess`, not root)
3. Copy `terraform.tfvars.example` to `terraform.tfvars` and fill in your SSH public key and IP
4. `terraform init && terraform plan && terraform apply`
5. Configure the resulting instance: `cd ansible && ansible-playbook playbook.yml`

## CI/CD

Every push to `main` runs `terraform fmt -check`, `validate`, and `plan` automatically; a clean plan on `main` proceeds to `apply`. Pull requests run format/validate/plan only, so changes can be reviewed before anything touches real infrastructure. AWS credentials and the SSH public key are injected via GitHub Secrets/Variables — never committed to the repo.

## Design notes

- **Remote state (S3 + DynamoDB):** keeps local and CI runs consistent and prevents concurrent-apply conflicts. Terraform 1.10+ offers a newer native S3-locking mechanism (`use_lockfile`) as an alternative to DynamoDB; this project uses the DynamoDB approach since it's still the more common pattern in production Terraform today.
- **SSH restricted to a single IP; HTTP open to `0.0.0.0/0`** — least-privilege access for administration, public access for the actual service.
- **`t3.micro` / on-demand DynamoDB** — chosen to stay within AWS free-tier limits for a personal learning project.

## Teardown

```
terraform destroy
```
Removes all AWS resources (except the S3 state bucket/DynamoDB table need a second `destroy` pass or manual cleanup, since Terraform can't delete the backend it's actively using in the same run).
