import boto3
import logging
import os
import time

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    logger.info("Received event: %s", event)

    # Retrieve parameters from environment variables
    ssm_parameter_name = os.environ.get('SSM_PARAMETER_NAME', '/tme/sc/failover/primary_instance_id')
    service_name = os.environ.get('SNAPCENTER_SERVICE_NAME', 'SnapCenter SMCore Service')
    target_lambda_function_name = os.environ.get('SNAPCENTER_FAILOVER_LAMBDA_NAME', 'snapcenter-failover-lambda')

    try:
        # Initialize a session using Amazon SSM, Lambda
        ssm = boto3.client('ssm')
        lambda_client = boto3.client('lambda')
        
        # Retrieve the instance ID from SSM Parameter Store
        response = ssm.get_parameter(Name=ssm_parameter_name, WithDecryption=True)
        instance_id = response['Parameter']['Value']
        
        logger.info(f"Checking if {service_name} service is running on Instance %s", instance_id)

        # Command to check if the SSM Agent is running
        command = f"Get-Service -Name \'{service_name}\'  | Select-Object -ExpandProperty Status"

        # Send command to the EC2 instance
        response = ssm.send_command(
            InstanceIds=[instance_id],
            DocumentName="AWS-RunPowerShellScript",
            Parameters={'commands': [command]}
        )

        # Get the command ID
        command_id = response['Command']['CommandId']
        logger.info("Sent command with Command ID: %s", command_id)

        # Wait for the command to complete
        time.sleep(10)

        # Get the command output
        output = ssm.get_command_invocation(
            CommandId=command_id,
            InstanceId=instance_id
        )

        # Log the full output for debugging
        logger.info("Command output: %s", output)

        # Check the status of the SSM Agent
        service_status = output['StandardOutputContent'].strip()
        logger.info(f"{service_name} status: %s", service_status)
    
        if service_status == 'Running':
            return {
                'statusCode': 200,
                'body': f'The service {service_name} is running.'
            }
        else:
            logger.info(f'Invoking {target_lambda_function_name} lambda function')
            try:
                # Invoke another Lambda function
                invoke_response = lambda_client.invoke(
                    FunctionName=target_lambda_function_name,
                    InvocationType='Event',  # 'Event' for asynchronous invocation
                    Payload=b'{}'  # You can pass any payload if needed
                )
                logger.info(f'The service {service_name} is not running. Status: {service_status}. Invoked Lambda function: {target_lambda_function_name}')
                return {
                    'statusCode': 200,
                    'body': f'The service {service_name} is not running. Status: {service_status}. Invoked Lambda function: {target_lambda_function_name}'
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