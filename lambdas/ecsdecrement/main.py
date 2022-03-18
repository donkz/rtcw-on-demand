import boto3
import logging
import json
import os

log_level = logging.INFO
logging.basicConfig(format='%(name)s:%(levelname)s:%(message)s')
logger = logging.getLogger('ecsdecrement')
logger.setLevel(log_level)
max_count = 1

def handler(event, context):
    """Decrement service based on a region."""

    logger.debug("Processing event " + json.dumps(event))
   
    try:
        region = "us-east-1"
        if event.get("detail-type", "Unknown") == "Scheduled Event":
            logger.info("Event type: decrement via schedule.")
            region = event["region"]
            
        pro_service = os.environ['ECS_SERVICE_NAME']
        rtcw_cluster = os.environ['ECS_CLUSTER_NAME']

        ecs = boto3.client('ecs', region_name=region)
        current_services= ecs.describe_services(cluster=rtcw_cluster, services = [pro_service])
        desired_count = current_services["services"][0]["desiredCount"]

        response = ecs.update_service(cluster=rtcw_cluster, service=pro_service, desiredCount=0)
        message = "Server is being taken down by a scheduled event."
        logger.debug(response)
    except Exception as ex:
        template = "An exception of type {0} occurred. Arguments:\n{1!r}"
        error_msg = template.format(type(ex).__name__, ex.args)
        message = "Failed to add a server\n" + error_msg        
    
    logger.info(message)
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'text/plain'
        },
        'body': message
    }


if __name__ == "__main__":
    event_stop = { "version": "0",
        "id": "53dc4d37-cffa-4f76-80c9-8b7d4a4d2eaa",
        "detail-type": "Scheduled Event",
        "source": "aws.events",
        "account": "123456789012",
        "time": "2015-10-08T16:53:06Z",
        "region": "us-east-1",
        "resources": [
            "arn:aws:events:us-east-1:123456789012:rule/my-scheduled-rule"
        ],
        "detail": {}
    }
    print(handler(event_stop, None))
