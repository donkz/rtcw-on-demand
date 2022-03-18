import boto3
import logging
import json
import os
from datetime import datetime

log_level = logging.INFO
logging.basicConfig(format='%(name)s:%(levelname)s:%(message)s')
logger = logging.getLogger('ecsguy')
logger.setLevel(log_level)
max_count = 1

def handler(event, context):
    """Increment service based on a region."""

    logger.info("Processing event " + json.dumps(event))
   
    try:
        increment = False

        if event.get("resource", "Unknown") == "/start/{region}":
            logger.info("Event type: increment via API.")
            increment = True
            if "region" in event["pathParameters"]:
                region = event["pathParameters"]["region"]
                logger.info("Incrementing in region: " + region)
        elif event.get("event", "increment"):
            region = event["region"]
            logger.info("Event type: incrementing via invoke in " + region)
        else:
            raise ValueError('Uknown invocation event!')

        pro_service = os.environ['ECS_SERVICE_NAME']
        rtcw_cluster = os.environ['ECS_CLUSTER_NAME']

        ecs = boto3.client('ecs', region_name=region)
        current_services= ecs.describe_services(cluster=rtcw_cluster, services = [pro_service])
        desired_count = current_services["services"][0]["desiredCount"]

        if desired_count < max_count:
            desired_count +=1
            response = ecs.update_service(cluster=rtcw_cluster, service=pro_service, desiredCount=desired_count)
            logger.debug(response)
            message = "Server requested. Takes about 2 minutes."
            logger.info(message)
        else:
            message = "Maximum number of servers is already in flight for this region."
            logger.info(message)

    except Exception as ex:
        template = "An exception of type {0} occurred. Arguments:\n{1!r}"
        error_msg = template.format(type(ex).__name__, ex.args)
        err_message = "Failed to add a server\n" + error_msg   
        logger.error(err_message)
        now = datetime.now()
        message = "Failed to add a server. UTC time: " + now.strftime("%d/%m/%Y %H:%M:%S")  
       
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'text/plain'
        },
        'body': message
    }


if __name__ == "__main__":
    
    # Local testing only #
    event_invoke = {"region": "us-east-1", "event": "increment"}
    
    event_api = {
        "resource": "/start/{region}",
        "pathParameters": {
            "region": "us-east-1"
            }
        }
    print(handler(event_api, None))
