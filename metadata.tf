locals {
  metadata = var.metadata

  common_name_prefix = try(local.metadata.common_name, local.default_common_name)
  common_name        = try(local.metadata.common_name, local.default_common_name)
  common_tags        = try(local.metadata.common_tags, local.default_common_tags)

  default_common_name = join("-", [
    local.metadata.key.company,
    local.metadata.key.env
  ])

  default_common_tags = {
    "company"     = local.metadata.key.company
    "provisioner" = "terraform"
    "environment" = local.metadata.environment
    "created-by"  = "GoCloud.la"
  }

  default_vpc_name            = local.common_name_prefix
  default_subnet_name         = "${local.common_name_prefix}-private*"
  default_subnet_private_name = "${local.common_name_prefix}-private*"
  default_subnet_public_name  = "${local.common_name_prefix}-public*"
  default_security_group      = "${local.common_name_prefix}-default"
  default_sns_topic_name      = "${local.common_name_prefix}-alerts"
  default_event_bus_name      = "default"
}
