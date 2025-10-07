module "lambda_service_scheduler" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "8.1.0"

  count = local.service_scheduler_enable

  function_name = "${local.common_name}-service_scheduler"
  description   = "Lambda function for service_scheduler"
  handler       = "index.lambda_handler"
  runtime       = "python3.9"
  timeout       = 300

  # attach_policy = true
  # policy        = "arn:aws:iam::aws:policy/AdministratorAccess"

  attach_policy_statements = true
  policy_statements = {
    dynamodb = {
      effect = "Allow",
      actions = [
        "dynamodb:BatchWriteItem",
        "dynamodb:DeleteItem",
        "dynamodb:PartiQLInsert",
        "dynamodb:PartiQLUpdate",
        "dynamodb:UpdateItem",
        "dynamodb:PutItem",
        "dynamodb:BatchGetItem",
        "dynamodb:Describe*",
        "dynamodb:List*",
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:PartiQLSelect"
      ],
      resources = [aws_dynamodb_table.this[0].arn]
    }
    # Permisos para ECS
    ecs = {
      effect = "Allow",
      actions = [
        "ecs:ListClusters",
        "ecs:DescribeClusters",
        "ecs:ListServices",
        "ecs:DescribeServices",
        "ecs:UpdateService",
        "ecs:ListTagsForResource"
      ],
      resources = ["*"]
    },

    # Permisos para Auto Scaling (para modificar políticas de escalado)
    autoscaling = {
      effect = "Allow",
      actions = [
        "application-autoscaling:DescribeScalableTargets",
        "application-autoscaling:RegisterScalableTarget",
        "application-autoscaling:DeregisterScalableTarget",
        "application-autoscaling:DescribeScalingPolicies",
        "application-autoscaling:PutScalingPolicy",
        "application-autoscaling:DeleteScalingPolicy"
      ],
      resources = ["*"]
    }
  }
  source_path = "${path.module}/lambdas/service-scheduler"

  cloudwatch_logs_retention_in_days = try(var.service_scheduler_parameters.cloudwatch_logs_retention_in_days, 14)

  environment_variables = {
    "DYNAMO_TABLE_NAME" : aws_dynamodb_table.this[0].name
    "LOG_LEVEL" : try(var.service_scheduler_parameters.log_level, "INFO")
    "DEFAULT_SELECTION_MODE" : try(var.service_scheduler_parameters.default_selection_mode, "include")
    "ENABLE_SCHEDULER_ECS" : try(var.service_scheduler_parameters.enable_scheduler_ecs, "true")
    "ENABLE_SCHEDULER_RDS" : try(var.service_scheduler_parameters.enable_scheduler_rds, "true")
    "ENABLE_SCHEDULER_EC2" : try(var.service_scheduler_parameters.enable_scheduler_ec2, "true")
  }

  create_current_version_allowed_triggers = false

  allowed_triggers            = local.lambda_service_scheduler_allowed_triggers
  ipv6_allowed_for_dual_stack = try(var.service_scheduler_parameters.ipv6_allowed_for_dual_stack, null)
  recursive_loop              = try(var.service_scheduler_parameters.recursive_loop, null)
  include_default_tag         = try(var.service_scheduler_parameters.include_default_tag, true)

  tags = merge(local.common_tags, try(var.service_scheduler_parameters.tags, var.service_scheduler_defaults.tags, null))
}


resource "aws_dynamodb_table" "this" {
  count = local.service_scheduler_enable

  name         = "${local.common_name}-service_scheduler" # Nombre de la tabla
  billing_mode = "PAY_PER_REQUEST"                        # Modo de pago (puede ser "PROVISIONED" si deseas especificar capacidad)

  # Definición de la clave de partición (primary key)
  hash_key  = "resource_id"
  range_key = "timestamp" # Clave de ordenación para almacenar múltiples entradas por recurso


  # Atributos de la tabla (clave primaria y atributos adicionales)
  attribute {
    name = "resource_id"
    type = "S" # Tipo "S" significa String
  }

  attribute {
    name = "timestamp"
    type = "S" # Tipo String para almacenar la fecha y hora
  }

  tags = merge(local.common_tags, try(var.service_scheduler_parameters.tags, var.service_scheduler_defaults.tags, null))
}


module "event_bridge_service_scheduler" {
  source  = "terraform-aws-modules/eventbridge/aws"
  version = "4.2.0"

  count = local.service_scheduler_enable

  create_bus = false

  rules   = local.event_bridge_service_scheduler_rules
  targets = local.event_bridge_service_scheduler_targets

  tags = merge(local.common_tags, try(var.service_scheduler_parameters.tags, var.service_scheduler_defaults.tags, null))
}