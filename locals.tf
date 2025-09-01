locals {
  metadata = var.metadata

  common_name = join("-", [
    local.metadata.key.company,
    local.metadata.key.env
  ])

  common_tags = {
    "company"     = local.metadata.key.company
    "provisioner" = "terraform"
    "environment" = local.metadata.environment
    "created-by"  = "GoCloud.la"
  }

  service_scheduler_enable = lookup(var.service_scheduler_parameters, "enable", false) ? 1 : 0

  power_on_schedule_enable  = try(var.service_scheduler_parameters.power_on_schedule, null)
  power_off_schedule_enable = try(var.service_scheduler_parameters.power_off_schedule, null)

  lambda_service_scheduler_allowed_triggers = merge(
    local.power_on_schedule_enable != null ? {
      "power-on" = {
        principal  = "events.amazonaws.com"
        source_arn = try(module.event_bridge_service_scheduler[0].eventbridge_rule_arns["power-on"], null)
      }
    } : {},
    local.power_off_schedule_enable != null ? {
      "power-off" = {
        principal  = "events.amazonaws.com"
        source_arn = try(module.event_bridge_service_scheduler[0].eventbridge_rule_arns["power-off"], null)
      }
    } : {}
  )

  event_bridge_service_scheduler_rules = merge(
    local.power_on_schedule_enable != null ? {
      "power-on" = {
        description         = "Service Scheduler (power-on)"
        schedule_expression = local.power_on_schedule_enable
      }
    } : {},
    local.power_off_schedule_enable != null ? {
      "power-off" = {
        description         = "Service Scheduler (power-off)"
        schedule_expression = local.power_off_schedule_enable
      }
    } : {}
  )

  event_bridge_service_scheduler_targets = merge(
    local.power_on_schedule_enable != null ? {
      "power-on" = [
        {
          name  = "power-on"
          arn   = try(module.lambda_service_scheduler[0].lambda_function_arn, "")
          input = jsonencode({ "action" : "power-on" })
        }
      ]
    } : {},
    local.power_off_schedule_enable != null ? {
      "power-off" = [
        {
          name  = "power-off"
          arn   = try(module.lambda_service_scheduler[0].lambda_function_arn, "")
          input = jsonencode({ "action" : "power-off" })
        }
      ]
    } : {}
  )
}
