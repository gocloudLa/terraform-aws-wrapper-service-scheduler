import boto3
import logging
import os
from datetime import datetime

# Configuración del logging
log_level = os.getenv('LOG_LEVEL', 'INFO')
logger = logging.getLogger()
logger.setLevel(getattr(logging, log_level, logging.INFO))

default_selection_mode = os.getenv('DEFAULT_SELECTION_MODE', 'include').lower()

enable_scheduler_ecs = os.getenv('ENABLE_SCHEDULER_ECS', 'true').lower() == 'true'
enable_scheduler_rds = os.getenv('ENABLE_SCHEDULER_RDS', 'true').lower() == 'true'
enable_scheduler_ec2 = os.getenv('ENABLE_SCHEDULER_EC2', 'true').lower() == 'true'

ecs_client = boto3.client('ecs')
application_autoscaling_client = boto3.client('application-autoscaling')
dynamodb_client = boto3.resource('dynamodb')

DYNAMO_TABLE_NAME = os.getenv('DYNAMO_TABLE_NAME', '')
dynamo_table = dynamodb_client.Table(DYNAMO_TABLE_NAME)

# Initialize logger
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

def lambda_handler(event, context):
    """Main function to determine whether to power off or power on resources."""
    action = event.get('action', 'power-off')
    dry_run = event.get('dry_run', False)

    record_action_status('scheduler', action, dry_run, 'begin')
    logger.info(f"Lambda invoked with action '{action}' and dry_run={dry_run}")

    if not can_execute_action(action):
        logger.error(f"Cannot execute action '{action}'.")
        return {"status": "action not allowed"}

    try:
        if action == 'power-off':
            general_power_off(dry_run)
        elif action == 'power-on':
            general_power_on(dry_run)
        else:
            logger.error(f"Unsupported action: {action}")
            raise ValueError("Unsupported action")
    
        record_action_status('scheduler', action, dry_run, 'end')
        logger.info(f"Completed action '{action}' with dry_run={dry_run}")

    except Exception as e:
        logger.error(f"Error executing action '{action}': {e}")

def record_action_status(resource_id, action, dry_run, action_type):
    """Log the action status in DynamoDB."""
    timestamp = datetime.utcnow().isoformat()
    item = {
        'resource_id': resource_id,
        'action': action,
        'action_type': action_type,
        'timestamp': timestamp
    }

    if dry_run:
        logger.debug(f"[dry-run] record_action_status: {item}")
    else:
        logger.debug(f"record_action_status: {item}")
        dynamo_table.put_item(Item=item)

def can_execute_action(action):
    """Check if the action can be executed based on the last record in DynamoDB."""
    try:
        response = dynamo_table.query(
            KeyConditionExpression='resource_id = :id',
            ExpressionAttributeValues={':id': 'scheduler'},
            Limit=10,
            ScanIndexForward=False
        )

        items = response.get('Items', [])

        if not items:
            logger.info("No records in DynamoDB.")
            return action == 'power-off'

        last_non_dry_run_end_action = next(
            (item for item in items if item.get('action_type') == 'end' and not item.get('dry_run', False)), 
            None
        )

        if last_non_dry_run_end_action:
            last_action = last_non_dry_run_end_action.get('action')
            logger.debug(f"Last recorded action: {last_action} (dry_run: {last_non_dry_run_end_action.get('dry_run')})")

            if last_action == action:
                return False

        return True

    except Exception as e:
        logger.error(f"Error querying DynamoDB: {e}")
        return False

def general_power_off(dry_run):
    """Initiates a general power-off of resources."""
    logger.info("Initiating general power-off of resources.")
    
    ecs_power_off(dry_run)
    rds_power_off(dry_run)
    ec2_power_off(dry_run)
    
    logger.info("General power-off process completed.")

def general_power_on(dry_run):
    """Initiates a general power-on of resources."""
    logger.info("Initiating general power-on of resources.")
    
    ecs_power_on(dry_run)
    rds_power_on(dry_run)
    ec2_power_on(dry_run)
    
    logger.info("General power-on process completed.")

def ecs_power_off(dry_run):
    """Powers off ECS services."""
    if not enable_scheduler_ecs:
        logger.info("ECS scheduler is disabled. Skipping...")
        return None
    logger.info("Starting ECS services power-off.")

    timestamp = datetime.utcnow().isoformat()

    clusters = ecs_client.list_clusters().get('clusterArns', [])
    logger.debug(f"Found clusters: {clusters}")

    for cluster in clusters:
        services = []
        paginator = ecs_client.get_paginator('list_services')
        for page in paginator.paginate(cluster=cluster):
            services.extend(page.get('serviceArns', []))
        logger.debug(f"Total services in cluster {cluster}: {len(services)}")
        logger.debug(f"Services in cluster {cluster}: {services}")

        for service in services:
            service_info = ecs_client.describe_services(cluster=cluster, services=[service]).get('services', [])[0]
            desired_count = service_info['desiredCount']
            cluster_name = service_info['clusterArn'].split('/')[-1]
            service_name = service_info['serviceName']
            logger.debug(f"Processing ECS service {service_name} in cluster {cluster_name}")

            tags = ecs_client.list_tags_for_resource(resourceArn=service).get('tags', [])
            auto_scheduler_tag = next((tag['value'].lower() for tag in tags if tag['key'] == 'AutomaticScheduler'), None)
            should_power_off = (
                (default_selection_mode == 'include' and auto_scheduler_tag != 'false') or
                (default_selection_mode == 'exclude' and auto_scheduler_tag == 'true')
            )
            if not should_power_off:
                logger.info(f"Skipping ECS service {service_name} due to 'AutomaticScheduler' tag and selection mode.")
                continue

            try:
                scalable_targets = application_autoscaling_client.describe_scalable_targets(
                    ServiceNamespace='ecs',
                    ResourceIds=[f"service/{cluster_name}/{service_name}"],
                    ScalableDimension='ecs:service:DesiredCount'
                ).get('ScalableTargets', [])

                if scalable_targets:
                    min_capacity = scalable_targets[0]['MinCapacity']
                    max_capacity = scalable_targets[0]['MaxCapacity']
                    logger.info(f"ECS service {service_name} previous capacity (min={min_capacity}, max={max_capacity}).")

                    if dry_run:
                        logger.info(f"[dry-run] Simulating ECS service {service_name} powered off (min=0, max=0).")
                    else:
                        dynamo_table.put_item(Item={
                            'resource_id': service_info['serviceArn'],
                            'resource_type': 'ECS',
                            'cluster': cluster_name,
                            'previous_state': {'min_capacity': min_capacity, 'max_capacity': max_capacity},
                            'timestamp': timestamp
                        })
                        logger.debug(f"Saved scaling state for service {service_name} in DynamoDB.")

                        application_autoscaling_client.register_scalable_target(
                            ServiceNamespace='ecs',
                            ResourceId=f"service/{cluster_name}/{service_name}",
                            ScalableDimension='ecs:service:DesiredCount',
                            MinCapacity=0,
                            MaxCapacity=0
                        )
                        logger.info(f"ECS service {service_name} powered off (min=0, max=0).")
                else:
                    logger.info(f"ECS service {service_name} previous capacity (desired_count={desired_count}).")
  
                    if dry_run:
                        logger.info(f"[dry-run] Simulating ECS service {service_name} powered off (desired_count=0).")
                    else:
                        dynamo_table.put_item(Item={
                            'resource_id': service_info['serviceArn'],
                            'resource_type': 'ECS',
                            'cluster': cluster_name,
                            'previous_state': {'desired_count': desired_count},
                            'timestamp': timestamp
                        })
                        logger.debug(f"Saved desiredCount state for service {service_name} in DynamoDB.")

                        ecs_client.update_service(cluster=cluster, service=service, desiredCount=0)
                        logger.info(f"ECS service {service_name} powered off (desired_count=0).")

            except Exception as e:
                logger.error(f"Error adjusting scaling for ECS service {service_name}: {e}")

    logger.info("Completed ECS services power-off.")

def ecs_power_on(dry_run):
    """Powers on ECS services."""
    if not enable_scheduler_ecs:
        logger.info("ECS scheduler is disabled. Skipping...")
        return None
    logger.info("Starting ECS services power-on.")

    response = dynamo_table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr('resource_id').ne('scheduler')
    )
    
    latest_timestamp = max((item['timestamp'] for item in response['Items']), default=None)
    if not latest_timestamp:
        logger.error("Error. No recent timestamp found.")
        return False

    services_with_latest_timestamp = dynamo_table.scan(
        FilterExpression=(
            boto3.dynamodb.conditions.Attr('timestamp').eq(latest_timestamp) &
            boto3.dynamodb.conditions.Attr('resource_id').ne('scheduler')
        )
    ).get('Items', [])

    if not services_with_latest_timestamp:
        logger.error("No services found with the latest timestamp.")
        return False

    logger.info(f"Total services with the latest timestamp: {len(services_with_latest_timestamp)}")

    clusters = ecs_client.list_clusters().get('clusterArns', [])
    logger.debug(f"Found clusters: {clusters}")

    for cluster in clusters:
        services = []
        paginator = ecs_client.get_paginator('list_services')
        for page in paginator.paginate(cluster=cluster):
            services.extend(page.get('serviceArns', []))
        logger.debug(f"Total services in cluster {cluster}: {len(services)}")
        logger.debug(f"Services in cluster {cluster}: {services}")

        for service in services:
            service_info = ecs_client.describe_services(cluster=cluster, services=[service]).get('services', [])[0]
            cluster_name = service_info['clusterArn'].split('/')[-1]
            service_name = service_info['serviceName']
            logger.debug(f"Processing ECS service {service_name} in cluster {cluster_name}")

            tags = ecs_client.list_tags_for_resource(resourceArn=service).get('tags', [])
            auto_scheduler_tag = next((tag['value'].lower() for tag in tags if tag['key'] == 'AutomaticScheduler'), None)
            should_power_off = (
                (default_selection_mode == 'include' and auto_scheduler_tag != 'false') or
                (default_selection_mode == 'exclude' and auto_scheduler_tag == 'true')
            )
            if not should_power_off:
                logger.info(f"Skipping ECS service {service_name} due to 'AutomaticScheduler' tag and selection mode.")
                continue

            response = dynamo_table.get_item(Key={'resource_id': service_info['serviceArn'], 'timestamp': latest_timestamp})

            if 'Item' not in response:
                logger.warning(f"No state found in DynamoDB for service {service_info['serviceArn']}. Skipping.")
                continue

            item = response['Item']
            previous_state = item.get('previous_state', {})
            desired_count = int(previous_state.get('desired_count', service_info['desiredCount']))

            scalable_targets = application_autoscaling_client.describe_scalable_targets(
                ServiceNamespace='ecs',
                ResourceIds=[f"service/{cluster_name}/{service_name}"],
                ScalableDimension='ecs:service:DesiredCount'
            ).get('ScalableTargets', [])

            if scalable_targets:
                min_capacity = int(previous_state.get('min_capacity', 1))
                max_capacity = int(previous_state.get('max_capacity', 1))

                if dry_run:
                    logger.info(f"[dry-run] Simulating min={min_capacity}, max={max_capacity} for service {service_name}.")
                else:
                    application_autoscaling_client.register_scalable_target(
                        ServiceNamespace='ecs',
                        ResourceId=f"service/{cluster_name}/{service_name}",
                        ScalableDimension='ecs:service:DesiredCount',
                        MinCapacity=min_capacity,
                        MaxCapacity=max_capacity
                    )
                    logger.info(f"ECS service {service_name} set to min={min_capacity}, max={max_capacity} for power on.")
            else:    
                if dry_run:
                    logger.info(f"[dry-run] Simulating desired_count={desired_count} for service {service_name}.")
                else:
                    ecs_client.update_service(cluster=cluster, service=service, desiredCount=desired_count)
                    logger.info(f"ECS service {service_name} powered on (desired_count={desired_count}).")

    logger.info("Completed ECS services power-on.")

def rds_power_off(dry_run):
    """Powers off RDS services."""
    if not enable_scheduler_rds:
        logger.info("RDS scheduler is disabled. Skipping...")
        return None
    logger.info("Starting RDS services power-off.")

    logger.info("Completed RDS services power-off.")

def rds_power_on(dry_run):
    """Powers on RDS services."""
    if not enable_scheduler_rds:
        logger.info("RDS scheduler is disabled. Skipping...")
        return None
    logger.info("Starting RDS services power-on.")

    logger.info("Completed RDS services power-on.")

def ec2_power_off(dry_run):
    """Powers off EC2 Instances."""
    if not enable_scheduler_ec2:
        logger.info("EC2 scheduler is disabled. Skipping...")
        return None
    logger.info("Starting EC2 Instances power-off.")

    logger.info("Completed EC2 Instances power-off.")

def ec2_power_on(dry_run):
    """Powers on EC2 Instances."""
    if not enable_scheduler_ec2:
        logger.info("EC2 scheduler is disabled. Skipping...")
        return None
    logger.info("Starting EC2 Instances power-on.")

    logger.info("Completed EC2 Instances power-on.")