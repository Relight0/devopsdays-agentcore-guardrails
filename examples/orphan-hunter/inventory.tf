locals {
  catalog = { for r in local.scenario.inventory : r.name => r }

  seeds = {
    for pair in setproduct(local.scenario.batches, keys(local.catalog)) :
    "${pair[0]}/${pair[1]}" => merge(local.catalog[pair[1]], { batch = pair[0] })
  }

  seed_tags = {
    for key, r in local.seeds : key => merge(
      { for k, v in r.tags : k => v if v != null },
      { Name = r.name, notes = r.notes, demo_batch = r.batch },
    )
  }

  seeds_by_type = {
    for t in ["volume", "snapshot", "elastic-ip", "security-group", "network-interface"] :
    t => { for key, r in local.seeds : key => r if r.type == t }
  }
}

resource "aws_vpc" "demo" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "${var.project_name}-vpc" }
}

resource "aws_subnet" "demo" {
  vpc_id            = aws_vpc.demo.id
  cidr_block        = "10.42.1.0/24"
  availability_zone = local.az
  tags              = { Name = "${var.project_name}-subnet" }
}

resource "aws_default_security_group" "demo" {
  vpc_id = aws_vpc.demo.id
  tags   = { Name = "${var.project_name}-default-locked" }
}

resource "aws_ebs_volume" "seed" {
  for_each = local.seeds_by_type["volume"]

  availability_zone = local.az
  size              = 1
  type              = "gp3"
  encrypted         = true
  tags              = local.seed_tags[each.key]
}

resource "aws_ebs_volume" "snapshot_source" {
  for_each = local.seeds_by_type["snapshot"]

  availability_zone = local.az
  size              = 1
  type              = "gp3"
  encrypted         = true

  tags = { Name = "${var.project_name}-src-${replace(each.key, "/", "-")}", demo_role = "snapshot-source" }
}

resource "aws_ebs_snapshot" "seed" {
  for_each = local.seeds_by_type["snapshot"]

  volume_id = aws_ebs_volume.snapshot_source[each.key].id
  # Cambiar la descripcion reemplaza el recurso; las notas van en el tag `notes`.
  description = "Recurso de demo ${var.project_name}"
  tags        = local.seed_tags[each.key]
}

resource "aws_eip" "seed" {
  for_each = local.seeds_by_type["elastic-ip"]

  domain = "vpc"
  tags   = local.seed_tags[each.key]
}

resource "aws_security_group" "seed" {
  for_each = local.seeds_by_type["security-group"]

  name        = "${var.project_name}-${replace(each.key, "/", "-")}"
  description = "Recurso de demo ${var.project_name}" # fija: cambiarla reemplaza el SG
  vpc_id      = aws_vpc.demo.id
  tags        = local.seed_tags[each.key]
}

resource "aws_network_interface" "seed" {
  for_each = local.seeds_by_type["network-interface"]

  subnet_id       = aws_subnet.demo.id
  security_groups = [aws_default_security_group.demo.id]
  description     = "Recurso de demo ${var.project_name}"
  tags            = local.seed_tags[each.key]
}

resource "aws_ssm_parameter" "active_batch" {
  name        = "/${var.project_name}/active-batch"
  description = "Lote de recursos visible para las herramientas del agente."
  type        = "String"
  value       = local.scenario.batches[0]

  lifecycle {
    ignore_changes = [value] # lo cambia scripts/reset_batch.py
  }
}

resource "aws_sns_topic" "notify" {
  name              = "${var.project_name}-owner-notifications"
  kms_master_key_id = "alias/aws/sns"
}

resource "aws_sns_topic_subscription" "email" {
  count = var.notify_email == null ? 0 : 1

  topic_arn = aws_sns_topic.notify.arn
  protocol  = "email"
  endpoint  = var.notify_email
}
