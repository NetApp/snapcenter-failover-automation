import boto3
import os
import logging
import time

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    logger.info("Received event: %s", event)

    # Initialize a session using Amazon EC2
    ec2 = boto3.client('ec2')

    # Retrieve parameters from environment variables
    route_table_id = os.environ.get('ROUTE_TABLE_ID')
    destination_cidr_block = os.environ.get('DESTINATION_CIDR_BLOCK')
    instance_id_01 = os.environ.get('INSTANCE_ID_01')
    instance_id_02 = os.environ.get('INSTANCE_ID_02')
    
    
    ssm_parameter_name = os.environ.get('SSM_PARAMETER_NAME', '/snapcenter/ha/primary_instance_id')

    # Check if all required environment variables are set
    if not route_table_id or not destination_cidr_block or not instance_id_01 or not instance_id_02:
        error_message = "Missing required environment variables: ROUTE_TABLE_ID, DESTINATION_CIDR_BLOCK, INSTANCE_ID_01, INSTANCE_ID_02"
        logger.error(error_message)
        return {
            'statusCode': 400,
            'body': error_message
        }

    try:
        # Initialize a session using Amazon SSM
        ssm = boto3.client('ssm')

        # Retrieve the instance ID from SSM Parameter Store
        response = ssm.get_parameter(Name=ssm_parameter_name, WithDecryption=True)
        primary_instance_id = response['Parameter']['Value']
        
        logger.info("Current primary instance %s", primary_instance_id)
        
        instance_id = instance_id_01 if primary_instance_id == instance_id_02 else instance_id_02

        start_time = time.time()
        logger.info("Starting to replace route in route table %s for destination %s to instance %s", route_table_id, destination_cidr_block, instance_id)

        # Initialize a session using Amazon EC2
        ec2 = boto3.client('ec2')

        # Replace the route in the specified route table
        response = ec2.replace_route(
            RouteTableId=route_table_id,
            DestinationCidrBlock=destination_cidr_block,
            InstanceId=instance_id
        )

        end_time = time.time()
        logger.info("Successfully updated route: %s", response)
        logger.info("Time taken to replace route: %s seconds", end_time - start_time)
        
        # Update the SSM parameter with the new instance ID or any other value
        ssm.put_parameter(
            Name=ssm_parameter_name,
            Value=instance_id,
            Type='String',
            Overwrite=True
        )
        logger.info("Successfully updated SSM parameter %s with value %s", ssm_parameter_name, instance_id)

        return {
            'statusCode': 200,
            'body': f'Successfully updated route in route table {route_table_id} to point to instance {instance_id}'
        }
    except Exception as e:
        logger.error("Error updating route: %s", str(e))
        return {
            'statusCode': 500,
            'body': f'Error updating route: {str(e)}'
        }