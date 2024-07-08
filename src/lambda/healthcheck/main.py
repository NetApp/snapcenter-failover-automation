import boto3
import logging
import os
import time

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def check_service_status(ssm, instance_id, snapcenter_service_name, mysql_service_name):
    # Command to check if the services are running
    first_command = f"Get-Service -Name '{snapcenter_service_name}' | Select-Object -ExpandProperty Status"
    second_command = f"Get-Service -Name '{mysql_service_name}' | Select-Object -ExpandProperty Status"

    # Send command to the EC2 instance
    response = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunPowerShellScript",
        Parameters={'commands': [first_command, second_command]}
    )

    # Get the command ID
    command_id = response['Command']['CommandId']
    logger.info("Sent command with Command ID: %s", command_id)

    # Wait for the command to complete
    time.sleep(15)

    # Get the command output
    output = ssm.get_command_invocation(
        CommandId=command_id,
        InstanceId=instance_id
    )

    # Log the full output for debugging
    logger.info("Command output: %s", output)

    # Check the status of the services
    snapcenter_service_status = output['StandardOutputContent'].splitlines()[0].strip()
    mysql_service_status = output['StandardOutputContent'].splitlines()[1].strip()
    logger.info(f"{snapcenter_service_name} status: {snapcenter_service_status}")
    logger.info(f"{mysql_service_name} status: {mysql_service_status}")

    return snapcenter_service_status, mysql_service_status

def lambda_handler(event, context):
    logger.info("Received event: %s", event)

    # Retrieve parameters from environment variables
    ssm_parameter_name = os.environ.get('SSM_PARAMETER_NAME', '/snapcenter/ha/primary_instance_id')
    snapcenter_service_name = os.environ.get('SNAPCENTER_SERVICE_NAME', 'SnapCenter SMCore Service')
    mysql_service_name = os.environ.get('MYSQL_SERVICE_NAME', 'MySQL57')
    target_lambda_function_name = os.environ.get('SNAPCENTER_FAILOVER_LAMBDA_NAME', 'snapcenter-failover-lambda')

    try:
        # Initialize a session using Amazon SSM, Lambda
        ssm = boto3.client('ssm')
        lambda_client = boto3.client('lambda')

        # Retrieve the instance ID from SSM Parameter Store
        response = ssm.get_parameter(Name=ssm_parameter_name, WithDecryption=True)
        instance_id = response['Parameter']['Value']

        logger.info(f"Checking if {snapcenter_service_name} and {mysql_service_name} services are running on Instance %s", instance_id)

        # Retry mechanism
        max_retries = 3
        for attempt in range(max_retries):
            snapcenter_service_status, mysql_service_status = check_service_status(ssm, instance_id, snapcenter_service_name, mysql_service_name)

            if snapcenter_service_status == 'Running' and mysql_service_status == 'Running':
                return {
                    'statusCode': 200,
                    'body': f'Both services {snapcenter_service_name} and {mysql_service_name} are running.'
                }

            logger.info(f"Attempt {attempt + 1}/{max_retries}: One or both services are not running.")
            time.sleep(10)  # Wait before retrying

        # If services are still not running after retries, invoke the failover Lambda function
        logger.info(f'One or both services are not running after {max_retries} attempts. Invoking Lambda function: {target_lambda_function_name}')
        try:
            # Invoke another Lambda function
            invoke_response = lambda_client.invoke(
                FunctionName=target_lambda_function_name,
                InvocationType='Event',  # 'Event' for asynchronous invocation
                Payload=b'{}'  # You can pass any payload if needed
            )
            return {
                'statusCode': 200,
                'body': f'One or both services are not running after {max_retries} attempts. Invoked Lambda function: {target_lambda_function_name}'
            }
        except Exception as invoke_error:
            logger.error(f'Error invoking Lambda function: {str(invoke_error)}')
            return {
                'statusCode': 500,
                'body': f'Error invoking Lambda function: {str(invoke_error)}'
            }
    except Exception as e:
        logger.error(f'Error: {str(e)}')
        return {
            'statusCode': 500,
            'body': f'Error: {str(e)}'
        }