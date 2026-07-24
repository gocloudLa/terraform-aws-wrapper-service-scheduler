import boto3
import logging
import os
import time
from datetime import datetime

# Configuración del logging
log_level = os.getenv('LOG_LEVEL', 'INFO')
logger = logging.getLogger()
logger.setLevel(getattr(logging, log_level, logging.INFO))

default_selection_mode = os.getenv('DEFAULT_SELECTION_MODE', 'include').lower()

enable_scheduler_ecs = os.getenv('ENABLE_SCHEDULER_ECS', 'true').lower() == 'true'
enable_scheduler_rds = os.getenv('ENABLE_SCHEDULER_RDS', 'true').lower() == 'true'
enable_scheduler_ec2 = os.getenv('ENABLE_SCHEDULER_EC2', 'true').lower() == 'true'
enable_scheduler_asg = os.getenv('ENABLE_SCHEDULER_ASG', 'true').lower() == 'true'

ecs_client = boto3.client('ecs')
rds_client = boto3.client('rds')
application_autoscaling_client = boto3.client('application-autoscaling')
dynamodb_client = boto3.resource('dynamodb')
autoscaling_client = boto3.client("autoscaling")
ec2_client = boto3.client("ec2")

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

    logger.info(f"Lambda invoked with action '{action}' and dry_run={dry_run}")

    if not can_execute_action(action):
        logger.error(f"Cannot execute action '{action}'.")
        return {"status": "action not allowed"}

    if action != 'rds-re-stop':
        record_action_status('scheduler', action, dry_run, 'begin')

    try:
        if action == 'power-off':
            general_power_off(dry_run)
        elif action == 'power-on':
            general_power_on(dry_run)
        elif action == 'rds-re-stop':
            rds_re_stop(event, dry_run)
        else:
            logger.error(f"Unsupported action: {action}")
            raise ValueError("Unsupported action")
    
        if action != 'rds-re-stop':
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

            if action == 'rds-re-stop' and last_action != 'power-off':
                logger.info(f"Cannot execute rds-re-stop: last action was '{last_action}', expected 'power-off'.")
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
    asg_power_off(dry_run)
    
    logger.info("General power-off process completed.")

def general_power_on(dry_run):
    """Initiates a general power-on of resources."""
    logger.info("Initiating general power-on of resources.")
    
    ecs_power_on(dry_run)
    rds_power_on(dry_run)
    ec2_power_on(dry_run)
    asg_power_on(dry_run)
    
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
        FilterExpression=boto3.dynamodb.conditions.Attr('resource_type').eq('ECS')
    )
    
    latest_timestamp = max((item['timestamp'] for item in response['Items']), default=None)
    if not latest_timestamp:
        logger.error("Error. No recent timestamp found.")
        return False

    services_with_latest_timestamp = dynamo_table.scan(
        FilterExpression=(
            boto3.dynamodb.conditions.Attr('timestamp').eq(latest_timestamp) &
            boto3.dynamodb.conditions.Attr('resource_type').eq('ECS')
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
    """Powers off RDS instances and clusters."""
    if not enable_scheduler_rds:
        logger.info("RDS scheduler is disabled. Skipping...")
        return None
    logger.info("Starting RDS services power-off.")

    timestamp = datetime.utcnow().isoformat()

    try:
        paginator = rds_client.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for db_instance in page.get("DBInstances", []):
                db_instance_id = db_instance["DBInstanceIdentifier"]
                db_status = db_instance["DBInstanceStatus"]

                if db_instance.get("DBClusterIdentifier"):
                    logger.debug(f"Skipping RDS instance {db_instance_id} (part of cluster {db_instance['DBClusterIdentifier']}).")
                    continue

                if db_status != "available":
                    logger.info(f"Skipping RDS instance {db_instance_id} (status: {db_status}).")
                    continue

                tags_response = rds_client.list_tags_for_resource(ResourceName=db_instance["DBInstanceArn"])
                tags = {tag["Key"]: tag["Value"].lower() for tag in tags_response.get("TagList", [])}
                auto_scheduler_tag = tags.get("automaticscheduler", tags.get("AutomaticScheduler"))

                should_power_off = (
                    (default_selection_mode == "include" and auto_scheduler_tag != "false") or
                    (default_selection_mode == "exclude" and auto_scheduler_tag == "true")
                )
                if not should_power_off:
                    logger.info(f"Skipping RDS instance {db_instance_id} due to 'AutomaticScheduler' tag and selection mode.")
                    continue

                if dry_run:
                    logger.info(f"[dry-run] Simulating RDS instance {db_instance_id} powered off.")
                    continue

                try:
                    dynamo_table.put_item(Item={
                        "resource_id": db_instance_id,
                        "resource_type": "RDS",
                        "rds_type": "instance",
                        "timestamp": timestamp
                    })
                    logger.debug(f"Saved state for RDS instance {db_instance_id} in DynamoDB.")

                    rds_client.stop_db_instance(DBInstanceIdentifier=db_instance_id)
                    logger.info(f"RDS instance {db_instance_id} powered off.")
                except Exception as e:
                    logger.error(f"Error stopping RDS instance {db_instance_id}: {e}")

    except Exception as e:
        logger.error(f"Error processing RDS instances: {e}")

    try:
        paginator = rds_client.get_paginator("describe_db_clusters")
        for page in paginator.paginate():
            for db_cluster in page.get("DBClusters", []):
                db_cluster_id = db_cluster["DBClusterIdentifier"]
                cluster_status = db_cluster["Status"]

                if db_cluster.get("MultiAZ") and not db_cluster.get("Engine", "").startswith("aurora"):
                    logger.info(f"Skipping RDS cluster {db_cluster_id} (Multi-AZ DB cluster, stop not supported).")
                    continue

                if cluster_status != "available":
                    logger.info(f"Skipping RDS cluster {db_cluster_id} (status: {cluster_status}).")
                    continue

                tags_response = rds_client.list_tags_for_resource(ResourceName=db_cluster["DBClusterArn"])
                tags = {tag["Key"]: tag["Value"].lower() for tag in tags_response.get("TagList", [])}
                auto_scheduler_tag = tags.get("automaticscheduler", tags.get("AutomaticScheduler"))

                should_power_off = (
                    (default_selection_mode == "include" and auto_scheduler_tag != "false") or
                    (default_selection_mode == "exclude" and auto_scheduler_tag == "true")
                )
                if not should_power_off:
                    logger.info(f"Skipping RDS cluster {db_cluster_id} due to 'AutomaticScheduler' tag and selection mode.")
                    continue

                if dry_run:
                    logger.info(f"[dry-run] Simulating RDS cluster {db_cluster_id} powered off.")
                    continue

                try:
                    dynamo_table.put_item(Item={
                        "resource_id": db_cluster_id,
                        "resource_type": "RDS",
                        "rds_type": "cluster",
                        "timestamp": timestamp
                    })
                    logger.debug(f"Saved state for RDS cluster {db_cluster_id} in DynamoDB.")

                    rds_client.stop_db_cluster(DBClusterIdentifier=db_cluster_id)
                    logger.info(f"RDS cluster {db_cluster_id} powered off.")
                except Exception as e:
                    logger.error(f"Error stopping RDS cluster {db_cluster_id}: {e}")

    except Exception as e:
        logger.error(f"Error processing RDS clusters: {e}")

    logger.info("Completed RDS services power-off.")

def rds_power_on(dry_run):
    """Powers on RDS instances and clusters."""
    if not enable_scheduler_rds:
        logger.info("RDS scheduler is disabled. Skipping...")
        return None
    logger.info("Starting RDS services power-on.")

    response = dynamo_table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr('resource_type').eq('RDS')
    )

    latest_timestamp = max((item['timestamp'] for item in response['Items']), default=None)
    if not latest_timestamp:
        logger.error("Error. No recent RDS timestamp found.")
        return False

    rds_with_latest_timestamp = dynamo_table.scan(
        FilterExpression=(
            boto3.dynamodb.conditions.Attr('timestamp').eq(latest_timestamp) &
            boto3.dynamodb.conditions.Attr('resource_type').eq('RDS')
        )
    ).get('Items', [])

    if not rds_with_latest_timestamp:
        logger.error("No RDS records found with the latest timestamp.")
        return False

    logger.info(f"Total RDS records with the latest timestamp: {len(rds_with_latest_timestamp)}")

    for record in rds_with_latest_timestamp:
        resource_id = record["resource_id"]
        rds_type = record.get("rds_type", "instance")

        if dry_run:
            logger.info(f"[dry-run] Simulating RDS {rds_type} {resource_id} power-on.")
            continue

        try:
            if rds_type == "cluster":
                rds_client.start_db_cluster(DBClusterIdentifier=resource_id)
                logger.info(f"RDS cluster {resource_id} powered on.")
            else:
                rds_client.start_db_instance(DBInstanceIdentifier=resource_id)
                logger.info(f"RDS instance {resource_id} powered on.")
        except Exception as e:
            logger.error(f"Error starting RDS {rds_type} {resource_id}: {e}")

    logger.info("Completed RDS services power-on.")

def wait_for_cluster_available(cluster_id, max_wait=270, interval=30):
    """Waits until the cluster and all its instances are in 'available' state."""
    elapsed = 0

    while elapsed < max_wait:
        try:
            cluster_info = rds_client.describe_db_clusters(
                DBClusterIdentifier=cluster_id
            )["DBClusters"][0]

            cluster_status = cluster_info.get("Status")
            if cluster_status != "available":
                logger.info(f"Cluster '{cluster_id}' is '{cluster_status}'. Waiting ({elapsed}s/{max_wait}s)...")
                time.sleep(interval)
                elapsed += interval
                continue

            all_available = True
            cluster_members = cluster_info.get("DBClusterMembers", [])
            for member in cluster_members:
                member_id = member["DBInstanceIdentifier"]
                member_info = rds_client.describe_db_instances(
                    DBInstanceIdentifier=member_id
                )["DBInstances"][0]
                member_status = member_info["DBInstanceStatus"]

                if member_status != "available":
                    logger.info(f"Instance '{member_id}' of cluster '{cluster_id}' is '{member_status}'. Waiting ({elapsed}s/{max_wait}s)...")
                    all_available = False
                    break

            if all_available:
                logger.info(f"Cluster '{cluster_id}' and all instances are available.")
                return True

            time.sleep(interval)
            elapsed += interval

        except Exception as e:
            logger.error(f"Error checking cluster '{cluster_id}' status: {e}")
            return False

    logger.error(f"Cluster '{cluster_id}' did not become fully available within {max_wait}s.")
    return False

def rds_re_stop(event, dry_run):
    """Re-stops a specific RDS instance/cluster that AWS auto-started after 7 days."""
    if not enable_scheduler_rds:
        logger.info("RDS scheduler is disabled. Skipping rds-re-stop...")
        return None

    rds_identifier = event.get("rds_identifier")
    rds_source_type = event.get("rds_source_type", "").lower()

    if not rds_identifier:
        logger.error("No rds_identifier in event. Cannot process rds-re-stop.")
        return None

    logger.info(f"Processing rds-re-stop for {rds_source_type} '{rds_identifier}'.")

    lookup_identifier = rds_identifier
    rds_type = "instance"

    if rds_source_type in ("db-instance", "db_instance"):
        try:
            instance_info = rds_client.describe_db_instances(
                DBInstanceIdentifier=rds_identifier
            )["DBInstances"][0]
            cluster_id = instance_info.get("DBClusterIdentifier")

            if cluster_id:
                logger.info(f"Instance '{rds_identifier}' belongs to cluster '{cluster_id}'. Skipping, cluster event will handle it.")
                return None
        except Exception as e:
            logger.error(f"Error describing instance {rds_identifier}: {e}")
            return None
    elif rds_source_type in ("db-cluster", "cluster"):
        if not wait_for_cluster_available(rds_identifier):
            return None
        rds_type = "cluster"

    response = dynamo_table.query(
        KeyConditionExpression='resource_id = :id',
        ExpressionAttributeValues={':id': lookup_identifier},
        Limit=1,
        ScanIndexForward=False
    )

    items = response.get('Items', [])
    if not items:
        logger.info(f"No records found in DynamoDB for '{lookup_identifier}'. Not managed by scheduler. Skipping.")
        return None

    last_record = items[0]
    if last_record.get('resource_type') != 'RDS':
        logger.info(f"Last record for '{lookup_identifier}' is not RDS type. Skipping.")
        return None

    logger.info(f"Found record for '{lookup_identifier}' (last stopped at {last_record.get('timestamp')}). Re-stopping.")

    timestamp = datetime.utcnow().isoformat()

    if dry_run:
        logger.info(f"[dry-run] Simulating RDS {rds_type} {lookup_identifier} re-stop.")
        return None

    try:
        if rds_type == "cluster":
            rds_client.stop_db_cluster(DBClusterIdentifier=lookup_identifier)
            logger.info(f"RDS cluster {lookup_identifier} re-stopped.")
        else:
            rds_client.stop_db_instance(DBInstanceIdentifier=lookup_identifier)
            logger.info(f"RDS instance {lookup_identifier} re-stopped.")

        dynamo_table.put_item(Item={
            "resource_id": lookup_identifier,
            "resource_type": "RDS",
            "rds_type": rds_type,
            "timestamp": timestamp
        })
        logger.debug(f"Updated DynamoDB record for {lookup_identifier}.")

    except rds_client.exceptions.DBInstanceNotFoundFault:
        logger.warning(f"RDS instance {lookup_identifier} not found. May have been deleted.")
    except rds_client.exceptions.DBClusterNotFoundFault:
        logger.warning(f"RDS cluster {lookup_identifier} not found. May have been deleted.")
    except Exception as e:
        logger.error(f"Error re-stopping RDS {rds_type} {lookup_identifier}: {e}")

def ec2_power_off(dry_run):
    """Powers off EC2 Instances."""
    if not enable_scheduler_ec2:
        logger.info("EC2 scheduler is disabled. Skipping...")
        return None
    logger.info("Starting EC2 Instances power-off.")

    timestamp = datetime.utcnow().isoformat()

    try:
        paginator = ec2_client.get_paginator("describe_instances")
        for page in paginator.paginate(Filters=[{"Name": "instance-state-name", "Values": ["running"]}]):
            
            all_instances = [
                instance
                for reservation in page.get("Reservations", [])
                for instance in reservation.get("Instances", [])
            ]

            non_asg_instances = [
                instance 
                for instance in all_instances
                if not any(tag["Key"] == "aws:autoscaling:groupName" for tag in instance.get("Tags", []))
            ]        

            for instance in non_asg_instances:
                instance_id = instance["InstanceId"]
                tags = {tag["Key"]: tag["Value"].lower() for tag in instance.get("Tags", [])}
                auto_scheduler_tag = tags.get("AutomaticScheduler")

                should_power_off = (
                    (default_selection_mode == "include" and auto_scheduler_tag != "false") or
                    (default_selection_mode == "exclude" and auto_scheduler_tag == "true")
                )
                if not should_power_off:
                    logger.info(f"Skipping EC2 {instance_id} due to 'AutomaticScheduler' tag and selection mode.")
                    continue

                if dry_run:
                    logger.info(f"[dry-run] Simulating EC2 {instance_id} powered off.")
                else:
                    dynamo_table.put_item(Item={
                        "resource_id": instance_id,
                        "resource_type": "EC2",
                        "timestamp": timestamp
                    })
                    logger.debug(f"Saved state for EC2 {instance_id} in DynamoDB.")

                    ec2_client.stop_instances(InstanceIds=[instance_id])
                    logger.info(f"EC2 {instance_id} powered off.")

    except Exception as e:
        logger.error(f"Error processing EC2 instances: {e}")

    logger.info("Completed EC2 instances power-off.")

def ec2_power_on(dry_run):
    """Powers on EC2 Instances."""
    if not enable_scheduler_ec2:
        logger.info("EC2 scheduler is disabled. Skipping...")
        return None
    logger.info("Starting EC2 Instances power-on.")

    response = dynamo_table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr('resource_type').eq('EC2')
    )

    latest_timestamp = max((item['timestamp'] for item in response['Items']), default=None)
    if not latest_timestamp:
        logger.error("Error. No recent timestamp found.")
        return False

    instances_with_latest_timestamp = dynamo_table.scan(
        FilterExpression=(
            boto3.dynamodb.conditions.Attr('timestamp').eq(latest_timestamp) &
            boto3.dynamodb.conditions.Attr('resource_type').eq('EC2')
        )
    ).get('Items', [])

    if not instances_with_latest_timestamp:
        logger.error("No EC2 records found with the latest timestamp.")
        return False

    logger.info(f"Total EC2 instances with the latest timestamp: {len(instances_with_latest_timestamp)}")

    paginator = ec2_client.get_paginator("describe_instances")
    for page in paginator.paginate(Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]):
        
        all_instances = [
            instance
            for reservation in page.get("Reservations", [])
            for instance in reservation.get("Instances", [])
        ]

        non_asg_instances = [
            instance 
            for instance in all_instances
            if not any(tag["Key"] == "aws:autoscaling:groupName" for tag in instance.get("Tags", []))
        ]                
        
        for instance in non_asg_instances:
            instance_id = instance["InstanceId"]
            tags = {tag["Key"]: tag["Value"].lower() for tag in instance.get("Tags", [])}
            asg_tag = tags.get("aws:autoscaling:groupName")


            record = next((item for item in instances_with_latest_timestamp if item["resource_id"] == instance_id), None)
            if not record:
                logger.warning(f"No previous state found in DynamoDB for EC2 {instance_id}. Skipping.")
                continue

            if dry_run:
                logger.info(f"[dry-run] Simulating EC2 {instance_id} start.")
            else:
                try:
                    ec2_client.start_instances(InstanceIds=[instance_id])
                    logger.info(f"EC2 {instance_id} powered on.")
                except Exception as e:
                    logger.error(f"Error starting EC2 {instance_id}: {e}")

    logger.info("Completed EC2 Instances power-on.")

def asg_power_off(dry_run):
    """Powers off Auto Scaling Group instances."""
    if not enable_scheduler_asg:
        logger.info("ASG scheduler is disabled. Skipping...")
        return None
    logger.info("Starting ASG instances power-off.")

    timestamp = datetime.utcnow().isoformat()

    asg_names = []
    asgs_info = {}
    paginator = autoscaling_client.get_paginator("describe_auto_scaling_groups")
    for page in paginator.paginate():
        for asg in page.get("AutoScalingGroups", []):
            asg_name = asg["AutoScalingGroupName"]
            asg_names.append(asg_name)
            asgs_info[asg_name] = asg
    logger.debug(f"Found ASGs: {asg_names}")

    for asg_name in asg_names:
        asg = asgs_info[asg_name]
        tags = {tag["Key"]: tag["Value"].lower() for tag in asg.get("Tags", [])}
        auto_scheduler_tag = tags.get("AutomaticScheduler")

        should_power_off = (
            (default_selection_mode == "include" and auto_scheduler_tag != "false") or
            (default_selection_mode == "exclude" and auto_scheduler_tag == "true")
        )
        if not should_power_off:
            logger.info(f"Skipping ASG {asg_name} due to 'AutomaticScheduler' tag and selection mode.")
            continue

        prev_state = {
            "MinSize": asg["MinSize"],
            "MaxSize": asg["MaxSize"],
            "DesiredCapacity": asg["DesiredCapacity"]
        }
        logger.info(f"ASG {asg_name} previous state: {prev_state}")

        if dry_run:
            logger.info(f"[dry-run] Simulating ASG {asg_name} powered off (Min=0, Max=0, Desired=0).")
            continue

        try:
            dynamo_table.put_item(Item={
                "resource_id": asg_name,
                "resource_type": "ASG",
                "previous_state": prev_state,
                "timestamp": timestamp
            })
            logger.debug(f"Saved state for ASG {asg_name} in DynamoDB.")

            autoscaling_client.update_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                MinSize=0,
                MaxSize=0,
                DesiredCapacity=0
            )
            logger.info(f"ASG {asg_name} powered off (Min=0, Max=0, Desired=0).")
        except Exception as e:
            logger.error(f"Error updating ASG {asg_name}: {e}")

    logger.info("Completed ASG instances power-off.")

def asg_power_on(dry_run):
    """Powers on Auto Scaling Groups instances."""
    if not enable_scheduler_asg:
        logger.info("ASG scheduler is disabled. Skipping...")
        return None
    logger.info("Starting ASG power-on process.")

    response = dynamo_table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr('resource_type').eq('ASG')
    )

    latest_timestamp = max((item['timestamp'] for item in response['Items']), default=None)
    if not latest_timestamp:
        logger.error("No recent timestamp found.")
        return False

    asg_with_latest_timestamp = dynamo_table.scan(
        FilterExpression=(
            boto3.dynamodb.conditions.Attr('timestamp').eq(latest_timestamp) &
            boto3.dynamodb.conditions.Attr('resource_type').eq('ASG')
        )
    ).get('Items', [])

    if not asg_with_latest_timestamp:
        logger.error("No ASG records found with the latest timestamp.")
        return False

    logger.info(f"Total ASG records with the latest timestamp: {len(asg_with_latest_timestamp)}")

    paginator = autoscaling_client.get_paginator("describe_auto_scaling_groups")
    for page in paginator.paginate():
        for asg in page.get("AutoScalingGroups", []):
            asg_name = asg["AutoScalingGroupName"]
            tags = {tag["Key"]: tag["Value"].lower() for tag in asg.get("Tags", [])}
            auto_scheduler_tag = tags.get("AutomaticScheduler")

            should_power_on = (
                (default_selection_mode == "include" and auto_scheduler_tag != "false") or
                (default_selection_mode == "exclude" and auto_scheduler_tag == "true")
            )
            if not should_power_on:
                logger.info(f"Skipping ASG {asg_name} due to 'AutomaticScheduler' tag and selection mode.")
                continue

            record = next((item for item in asg_with_latest_timestamp if item["resource_id"] == asg_name), None)
            if not record:
                logger.warning(f"No previous state found in DynamoDB for ASG {asg_name}. Skipping.")
                continue

            previous_state = record.get("previous_state", {})
            min_size = int(previous_state.get("MinSize", asg["MinSize"]))
            max_size = int(previous_state.get("MaxSize", asg["MaxSize"]))
            desired_capacity = int(previous_state.get("DesiredCapacity", asg["DesiredCapacity"]))

            if dry_run:
                logger.info(f"[dry-run] Simulating ASG {asg_name} power-on (Min={min_size}, Max={max_size}, Desired={desired_capacity}).")
                continue

            try:
                autoscaling_client.update_auto_scaling_group(
                    AutoScalingGroupName=asg_name,
                    MinSize=min_size,
                    MaxSize=max_size,
                    DesiredCapacity=desired_capacity
                )
                logger.info(f"ASG {asg_name} powered on (Min={min_size}, Max={max_size}, Desired={desired_capacity}).")
            except Exception as e:
                logger.error(f"Error powering on ASG {asg_name}: {e}")

    logger.info("Completed ASG power-on process.")