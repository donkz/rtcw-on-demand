import logging
import boto3
import json
import time as _time
import os

log_level = logging.INFO
logging.basicConfig(format='%(name)s:%(levelname)s:%(message)s')
logger = logging.getLogger("queue_handler")
logger.setLevel(log_level)

r53 = boto3.client('route53')

def handler(event, context):
    lastStatus = event["detail"]["lastStatus"]
    desiredStatus = event["detail"]["desiredStatus"]
    region = event["region"]
    
    if region == "us-east-1":
        url_prefix = "na"
    elif region == "sa-east-1":
        url_prefix = "sa"
    elif region == "eu-west-2":
        url_prefix = "eu"
    else:
        logger.error("Unknown region.")
        raise
    url = url_prefix + "." + os.environ["DNS_HOSTED_ZONE_NAME"]
    
    if lastStatus == "RUNNING" and desiredStatus == "RUNNING":
        logger.info("Making a record.")
        
        attachment_details = event["detail"]["attachments"][0]["details"]
        for keypair in attachment_details:
            if keypair["name"] == "networkInterfaceId":
                eni = keypair["value"]

        ec2 = boto3.client('ec2')
        try:
            response = ec2.describe_network_interfaces(NetworkInterfaceIds=[eni])
        except:
            logger.error("Could not describe eni " + eni)
            raise
            
        ip = response['NetworkInterfaces'][0]['Association']['PublicIp']
        change_my_r53("UPSERT", url, ip)

    if desiredStatus == "STOPPED":
        logger.info("Deleting a record")
        change_my_r53("UPSERT", url, "192.168.1.1")  #hack to change the record without looking up ip
        change_my_r53("DELETE", url, "192.168.1.1")  
    

def change_my_r53(action, url, ip):
    try:
        response = r53.change_resource_record_sets(
            ChangeBatch={
                'Changes': [
                    {
                        'Action': action,
                        'ResourceRecordSet': {
                            'Name': url,
                            'ResourceRecords': [
                                {
                                    'Value': ip,
                                },
                            ],
                            'TTL': 60,
                            'Type': 'A',
                        },
                    },
                ],
                'Comment': 'RTCW server',
            },
            HostedZoneId=os.environ["DNS_HOSTED_ZONE"]
        )
    except r53.exceptions.InvalidChangeBatch as err:
        if action == "DELETE" and "but it was not found" in str(err):
            logger.info("Record was already deleted.")
        elif action == "CREATE" and "but it already exists" in str(err):
            logger.info("Record already exists.")
        else:
            logger.error(err)
    else:
        if response["ResponseMetadata"]["HTTPStatusCode"] != 200:
            logger.error("Route53 update bad http code:")
            logger.error(response)
        else:
            logger.info("Successfully changed a record: " + action + " " + url + " " + ip)
        
        
if __name__ == "__main__":
    event_str_stopped = '{"version":"0","id":"a","detail-type":"ECS Task State Change","source":"aws.ecs","account":"123","time":"2021-07-07T19:44:16Z","region":"us-east-1","resources":["arn:aws:ecs:us-east-1:123:task/RTCWCluster/abc"],"detail":{"attachments":[{"id":"7b5d0e17-3563-4263-b42f-4b26afd8f477","type":"eni","status":"DELETED","details":[{"name":"subnetId","value":"subnet-123"},{"name":"networkInterfaceId","value":"eni-0e0750b47eb5d7062"},{"name":"macAddress","value":"12:1a:ce:9f:13:2f"},{"name":"privateDnsName","value":"ip-172-31-82-109.ec2.internal"},{"name":"privateIPv4Address","value":"172.31.82.109"}]}],"availabilityZone":"us-east-1b","clusterArn":"arn:aws:ecs:us-east-1:123:cluster/RTCWCluster","connectivity":"CONNECTED","connectivityAt":"2021-07-07T19:37:35.733Z","containers":[{"containerArn":"arn:aws:ecs:us-east-1:123:container/RTCWCluster/abc/2ee86259-6758-4dd9-9f4b-5efee171489a","exitCode":0,"lastStatus":"STOPPED","name":"msh100pro","image":"msh100/rtcw","runtimeId":"8d102278d0c04bbea006ba330c490e1b-2600574453","taskArn":"arn:aws:ecs:us-east-1:123:task/RTCWCluster/abc","networkInterfaces":[{"attachmentId":"7b5d0e17-3563-4263-b42f-4b26afd8f477","privateIpv4Address":"172.31.82.109"}],"cpu":"0","memory":"512"}],"cpu":"256","createdAt":"2021-07-07T19:37:27.169Z","desiredStatus":"STOPPED","enableExecuteCommand":false,"ephemeralStorage":{"sizeInGiB":20},"executionStoppedAt":"2021-07-07T19:43:43.263Z","group":"service:pro","launchType":"FARGATE","lastStatus":"STOPPED","memory":"512","overrides":{"containerOverrides":[{"name":"msh100pro"}]},"platformVersion":"1.4.0","pullStartedAt":"2021-07-07T19:37:55.488Z","pullStoppedAt":"2021-07-07T19:38:20.229Z","startedAt":"2021-07-07T19:38:27.321Z","startedBy":"ecs-svc/5229653580561241327","stoppingAt":"2021-07-07T19:43:31.156Z","stoppedAt":"2021-07-07T19:44:16.522Z","stoppedReason":"Scaling activity initiated by (deployment ecs-svc/5229653580561241327)","stopCode":"ServiceSchedulerInitiated","taskArn":"arn:aws:ecs:us-east-1:123:task/RTCWCluster/abc","taskDefinitionArn":"arn:aws:ecs:us-east-1:123:task-definition/msh100pro:3","updatedAt":"2021-07-07T19:44:16.522Z","version":7}}'
    event_str_started = '{"version":"0","id":"a","detail-type":"ECS Task State Change","source":"aws.ecs","account":"123","time":"2021-07-07T19:38:27Z","region":"us-east-1","resources":["arn:aws:ecs:us-east-1:123:task/RTCWCluster/abc"],"detail":{"attachments":[{"id":"7b5d0e17-3563-4263-b42f-4b26afd8f477","type":"eni","status":"ATTACHED","details":[{"name":"subnetId","value":"subnet-123"},{"name":"networkInterfaceId","value":"eni-0e0750b47eb5d7062"},{"name":"macAddress","value":"12:1a:ce:9f:13:2f"},{"name":"privateDnsName","value":"ip-172-31-82-109.ec2.internal"},{"name":"privateIPv4Address","value":"172.31.82.109"}]}],"availabilityZone":"us-east-1b","clusterArn":"arn:aws:ecs:us-east-1:123:cluster/RTCWCluster","connectivity":"CONNECTED","connectivityAt":"2021-07-07T19:37:35.733Z","containers":[{"containerArn":"arn:aws:ecs:us-east-1:123:container/RTCWCluster/abc/2ee86259-6758-4dd9-9f4b-5efee171489a","lastStatus":"RUNNING","name":"msh100pro","image":"msh100/rtcw","runtimeId":"8d102278d0c04bbea006ba330c490e1b-2600574453","taskArn":"arn:aws:ecs:us-east-1:123:task/RTCWCluster/abc","networkInterfaces":[{"attachmentId":"7b5d0e17-3563-4263-b42f-4b26afd8f477","privateIpv4Address":"172.31.82.109"}],"cpu":"0","memory":"512"}],"cpu":"256","createdAt":"2021-07-07T19:37:27.169Z","desiredStatus":"RUNNING","enableExecuteCommand":false,"ephemeralStorage":{"sizeInGiB":20},"group":"service:pro","launchType":"FARGATE","lastStatus":"RUNNING","memory":"512","overrides":{"containerOverrides":[{"name":"msh100pro"}]},"platformVersion":"1.4.0","pullStartedAt":"2021-07-07T19:37:55.488Z","pullStoppedAt":"2021-07-07T19:38:20.229Z","startedAt":"2021-07-07T19:38:27.321Z","startedBy":"ecs-svc/5229653580561241327","taskArn":"arn:aws:ecs:us-east-1:123:task/RTCWCluster/abc","taskDefinitionArn":"arn:aws:ecs:us-east-1:123:task-definition/msh100pro:3","updatedAt":"2021-07-07T19:38:27.321Z","version":4}}'
    event = json.loads(event_str_started)
    handler(event, None)
