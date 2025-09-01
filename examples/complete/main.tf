module "wrapper_service_scheduler" {
  source = "../../"

  metadata = local.metadata

  service_scheduler_parameters = {
    enable = true # Default: false

    power_on_schedule  = "cron(0 11 * * ? *)" # 8AM UTC-3 / null or commented to disable
    power_off_schedule = "cron(0 23 * * ? *)" # 8PM UTC-3 / null or commented to disable
    # include_default_tag = false
    # recursive_loop = "Allow"
    # ipv6_allowed_for_dual_stack = true
    # default_selection_mode = "include"
    # enable_scheduler_ecs   = true   # Default: true
    # enable_scheduler_rds   = true   # Default: true
    # enable_scheduler_ec2   = true   # Default: true
    # cloudwatch_logs_retention_in_days = 14
    # log_level = "INFO"

  }

  service_scheduler_defaults = var.service_scheduler_defaults
}