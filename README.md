# AWS IaC Pipeline

![CI/CD](https://github.com/guerrera26/aws-iac-pipeline/actions/workflows/terraform.yml/badge.svg)

![Terraform](https://img.shields.io/badge/Terraform-844FBA?style=for-the-badge&logo=terraform&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-232F3E?style=for-the-badge&logo=amazonaws&logoColor=white)
![Ansible](https://img.shields.io/badge/Ansible-EE0000?style=for-the-badge&logo=ansible&logoColor=white)
![React](https://img.shields.io/badge/React-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)

A full-stack infrastructure-as-code pipeline: **Terraform** provisions AWS infrastructure — networking, a web server, and a private Postgres database — **Ansible** deploys a **React/TypeScript** frontend and a **Flask** backend onto it, and every deploy is gated by a real test suite and a security scan, all automated through **GitHub Actions**.

**Live demo:** http://ec2-32-198-46-10.compute-1.amazonaws.com *(a personal-project instance — if it's ever down, see the screenshots/architecture below, or spin it back up with `terraform apply`)*

## Contents

- [Architecture](#architecture)
- [The app](#the-app)
- [Repository structure](#repository-structure)
- [Running it locally](#running-it-locally)
- [CI/CD pipeline](#cicd-pipeline)
- [Security design notes](#security-design-notes)
- [Teardown](#teardown)

## Architecture

```
                              ┌──────────────────────────────────────────────────┐
                              │                  AWS (us-east-1)                   │
                              │                                                     │
                              │   VPC (10.0.0.0/16)                                 │
                              │   ├── Public Subnet   (10.0.1.0/24, AZ-a)           │
                              │   │    └── EC2 t3.micro — IMDSv2 enforced            │
                              │   │         ├── nginx                                │
                              │   │         │    ├── serves the React SPA (static)   │
                              │   │         │    └── reverse-proxies /api/* + /health│
                              │   │         └── gunicorn → Flask app                 │
                              │   │              (IAM role → read-only access to     │
                              │   │               its own DB password in SSM)        │
                              │   │                                                  │
                              │   └── DB Subnet       (10.0.2.0/24, AZ-b)            │
                              │        └── RDS Postgres 16 — private, only reachable │
                              │            from the web instance's security group    │
                              │                                                       │
                              │   SSM Parameter Store ── DB password (SecureString)  │
                              │   S3 bucket  ── Terraform remote state (encrypted)   │
                              │   DynamoDB   ── Terraform state locking              │
                              └──────────────────────────────────────────────────────┘
                                                    ▲
                                                    │ plan / apply / deploy
                              ┌──────────────────────────────────────────┐
                              │              GitHub Actions CI             │
                              │                                             │
                              │   test ──┐                                 │
                              │   test-frontend ──┼──▶ terraform ──▶ deploy │
                              │   security-scan ──┘     (plan/apply)  (Ansible) │
                              └──────────────────────────────────────────┘
```

## The app

**Backend** — a small Flask API:

| Route | Purpose |
|---|---|
| `GET /health` | Liveness check |
| `GET /api/status` | Hostname, uptime, version — for debugging a live deploy |
| `GET /api/visits` | Reads/writes Postgres — the app talking to a real relational database |
| `GET /api/visits/summary` | Aggregates the same visits table with `GROUP BY date_trunc('hour', ...)` — total, last-24h count, and a zero-filled 24-hour time series |

**Frontend** — a React + TypeScript single-page app (built with Vite) that calls the API above and renders it live: backend status, a running visit counter, and a visit-analytics panel with a hand-rolled SVG bar chart (no charting library — kept the bundle small for a 24-bar sparkline). Typed end-to-end with TypeScript interfaces matching the API's JSON shape.

The database password is never typed by a human, never committed, and never passed through CI logs. It's auto-generated by Terraform (`random_password`), stored in SSM Parameter Store as a `SecureString`, and fetched by the app itself at runtime using the EC2 instance's IAM role — scoped to read only that one parameter.

## Repository structure

| Path | Purpose |
|---|---|
| `providers.tf` | AWS + random provider configuration |
| `variables.tf` | Input variables (region, instance type, SSH key, allowed IP) |
| `network.tf` | VPC, subnets (public + DB), routing, security groups |
| `compute.tf` | AMI lookup, SSH key pair, EC2 instance (IMDSv2 enforced) |
| `storage.tf` | S3 bucket (encrypted, public access blocked) |
| `database.tf` | RDS Postgres instance, auto-generated password, SSM parameter |
| `iam.tf` | Least-privilege IAM role letting the instance read its own DB password |
| `state-locking.tf` | DynamoDB table for Terraform state locking |
| `backend.tf` | Remote state configuration (S3 + DynamoDB) |
| `outputs.tf` | Instance IP, DB connection details (non-secret), bucket name |
| `app/` | Flask backend + pytest test suite |
| `frontend/` | React + TypeScript frontend (Vite) + vitest test suite |
| `ansible/` | Playbook that deploys both frontend and backend under nginx/gunicorn |
| `.github/workflows/terraform.yml` | The full CI/CD pipeline |

## Running it locally

1. Install [Terraform](https://developer.hashicorp.com/terraform/downloads), the [AWS CLI](https://aws.amazon.com/cli/), [Ansible](https://docs.ansible.com/ansible/latest/installation_guide/index.html), and [Node.js](https://nodejs.org/)
2. `aws configure` with an IAM user's access key (scoped, not root)
3. Copy `terraform.tfvars.example` to `terraform.tfvars` and fill in your SSH public key and IP
4. `terraform init && terraform plan && terraform apply`
5. Build the frontend:
   ```bash
   cd frontend && npm install && npm run build
   ```
6. Deploy both frontend and backend, pulling connection details straight from Terraform's outputs:
   ```bash
   cd ansible
   ansible-playbook playbook.yml \
     --extra-vars "db_host=$(terraform -chdir=.. output -raw db_host) \
                   db_name=$(terraform -chdir=.. output -raw db_name) \
                   db_user=$(terraform -chdir=.. output -raw db_user) \
                   db_password_ssm_param=$(terraform -chdir=.. output -raw db_password_ssm_param)"
   ```

## CI/CD pipeline

Every push to `main` runs, in order:

1. **`test`** — the Flask backend's pytest suite, run against a real Postgres service container (not mocks)
2. **`test-frontend`** — the React frontend's vitest suite, plus a TypeScript build/type-check
3. **`security-scan`** — [tfsec](https://github.com/aquasecurity/tfsec) statically scans the Terraform config for misconfigurations
4. **`terraform`** — format check, validate, plan, and (on `main`) apply — gated on all three jobs above passing
5. **`deploy`** — builds the frontend, then Ansible deploys both frontend and backend onto the instance. The runner's IP is dynamically and temporarily added to the security group for the ~30 seconds SSH is needed, then removed again immediately after — even if the deploy fails.

Pull requests run stages 1–4 only (plan, not apply), so infrastructure changes are reviewed before anything touches real AWS resources.

## Security design notes

- **DB password never touches CI**: generated by Terraform, stored encrypted in SSM, read by the instance via IAM role — no secret ever passes through Ansible, GitHub Secrets, or a workflow log.
- **Database isolated from the internet**: RDS lives in its own subnet, `publicly_accessible = false`, reachable only from the web instance's security group, never from `0.0.0.0/0`, and its outbound egress is narrowed to the VPC CIDR only.
- **Least-privilege IAM**: the instance role can read exactly one SSM parameter and decrypt it with exactly one KMS key (resolved to its real key ARN, not a wildcard) — nothing else. The Terraform deploy user itself is scoped to `PowerUserAccess` plus a narrow, resource-scoped IAM policy for this project's own role/instance-profile, not admin.
- **Dynamic, time-boxed CI access**: rather than permanently opening SSH to GitHub's runner IP ranges, the workflow opens port 22 for the current runner's specific IP only, and revokes it immediately after deploying (`if: always()`, so it's revoked even on failure).
- **Encryption everywhere it's free**: EC2 root volume, RDS storage, S3 (SSE-S3), the SSM parameter, and the DynamoDB lock table are all encrypted at rest; the S3 state bucket is versioned and the DynamoDB table has point-in-time recovery enabled.
- **Static security scanning**: tfsec runs on every push and blocks the pipeline on new findings, catching misconfigurations before they reach AWS rather than after.
- **IMDSv2 enforced** on the EC2 instance, mitigating SSRF-based credential theft.
- **Remote state (S3 + DynamoDB)**: keeps local and CI runs consistent and prevents concurrent-apply conflicts.
- **Free-tier sizing** (`t3.micro` / `db.t3.micro` / on-demand DynamoDB) — appropriate for a learning project; a production version would add Multi-AZ RDS and final snapshots on destroy.
- **RDS deletion protection is on**, like a real production database — teardown is a deliberate two-step process rather than a single accidental command (see Teardown below).

### Accepted-risk findings (documented, not silently suppressed)

tfsec flags a few things that are intentional tradeoffs for a free-tier personal project rather than genuine gaps. Each is marked with a `tfsec:ignore:<check-id>` comment at the resource in question, plus a one-line reason in the code itself. Summarized here for anyone reviewing the scan results:

| Finding | Why it's accepted |
|---|---|
| Web SG allows inbound HTTP (`0.0.0.0/0`) and all outbound | It's a public-facing web app with no load balancer, and the instance needs outbound access for OS updates, pulling the app, and AWS API calls |
| Public subnet auto-assigns public IPs | No NAT gateway — one runs 24/7 and costs money even idle, which isn't worth it for a single free-tier instance |
| No VPC flow logs | Ongoing CloudWatch/S3 cost and noise not warranted at this scale |
| S3 bucket uses SSE-S3 instead of a customer-managed KMS key | AES256 is sufficient for this bucket's contents (Terraform state); a CMK adds cost/rotation overhead without a matching benefit here |
| No S3 access logging | Disproportionate complexity for a bucket that's already fully blocked from public access |
| RDS doesn't use IAM database authentication | Would require reworking the app's connection code to fetch short-lived auth tokens instead of a password — a real improvement, just out of scope for this pass |
| RDS backup retention is only 1 day | Not a choice — this AWS account is free-tier restricted, and `terraform apply` with a longer retention period fails outright with `FreeTierRestrictionError`. 1 day is the actual ceiling. |
| RDS Performance Insights is off | A production-scale monitoring feature this single low-traffic instance doesn't need |
| DynamoDB lock table uses the AWS-owned key, not a customer-managed one | The table only ever holds lock-id metadata, never application data |

## Teardown

RDS deletion protection is on, so destroying is a deliberate two-step process:

```
# 1. Turn off deletion protection: flip deletion_protection to false
#    in database.tf, then apply that one change
terraform apply

# 2. Then destroy everything
terraform destroy
```
Removes all AWS resources except the S3 state bucket/DynamoDB table, which need a second `destroy` pass or manual cleanup since Terraform can't delete the backend it's actively using in the same run.
