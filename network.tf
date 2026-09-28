data "aws_availability_zones" "available" {
  state = "available"
}

# Flow logs add ongoing CloudWatch/S3 cost and operational noise that isn't
# warranted for a single-instance personal project; would add this for a
# production VPC.
# tfsec:ignore:aws-ec2-require-vpc-flow-logs-for-all-vpcs
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.project_name}-vpc"
  }
}

# Intentional: no NAT gateway in this project (NAT gateways cost money
# around the clock even when idle, which doesn't make sense for a single
# free-tier learning instance), so the web instance needs a public IP to
# reach the internet directly.
# tfsec:ignore:aws-ec2-no-public-ip-subnet
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-subnet"
  }
}

resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-igw"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }

  tags = {
    Name = "${var.project_name}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "web" {
  name        = "${var.project_name}-sg"
  description = "Allow SSH from my IP and HTTP from anywhere"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "SSH from my IP only"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.my_ip]
  }

  # Intentional: this is a public-facing web app on a single free-tier
  # instance with no load balancer, so port 80 has to be open to the
  # internet.
  # tfsec:ignore:aws-ec2-no-public-ingress-sgr
  ingress {
    description = "HTTP from anywhere (for later web-server demo)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Intentional: the instance needs outbound internet access for OS/package
  # updates, pulling the app from git, and calling AWS APIs (SSM, etc.) via
  # the public endpoints.
  # tfsec:ignore:aws-ec2-no-public-egress-sgr
  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-sg"
  }
}

# Second subnet in a different AZ — RDS requires a subnet group spanning
# at least two AZs, even for a single-AZ database instance.
resource "aws_subnet" "db" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = data.aws_availability_zones.available.names[1]

  tags = {
    Name = "${var.project_name}-db-subnet"
  }
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = [aws_subnet.public.id, aws_subnet.db.id]

  tags = {
    Name = "${var.project_name}-db-subnet-group"
  }
}

# Database security group: only reachable from the web instance's
# security group — never exposed to the internet.
resource "aws_security_group" "db" {
  name        = "${var.project_name}-db-sg"
  description = "Allow Postgres only from the web security group"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Postgres from web instance only"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.web.id]
  }

  # Egress narrowed to the VPC itself — the database never needs to reach
  # the public internet.
  egress {
    description = "Allow outbound traffic within the VPC only"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }

  tags = {
    Name = "${var.project_name}-db-sg"
  }
}
