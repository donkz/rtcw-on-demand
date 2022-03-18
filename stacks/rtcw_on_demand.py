from aws_cdk import Stack, Duration
from constructs import Construct
import aws_cdk.aws_lambda as _lambda
import aws_cdk.aws_iam as iam
import aws_cdk.aws_ecs as ecs
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
import aws_cdk.aws_ec2 as ec2
from stacks.main_region_construct import MainRegionSetup

from aws_cdk.aws_lambda_event_sources import SqsEventSource

class RtcwOnDemandStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, settings: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        if settings["main_region"] == self.region:
            MainRegionSetup(self, "MainRegionConstruct", settings=settings, account=self.account)
        
        env_vars = settings["env_vars"]
        if self.region == "us-east-1":
            hostname_suffix = "na"
            morning_hour = 8 # UTC, about 2-3am EST
        elif self.region == "sa-east-1":
            hostname_suffix = "sa"
            morning_hour = 9 # UTC
        elif self.region == "eu-west-2":
            hostname_suffix = "eu"
            morning_hour = 3 # UTC
        else:
            print("Unknown region: " + self.region)
            raise Exception("Unknown region.")
        
        r53_lambda_role = iam.Role(self, "LambdaR53",
                                   role_name='rtcwdemand-r53-lambda-role-' + hostname_suffix,
                                   assumed_by=iam.ServicePrincipal("lambda.amazonaws.com")
                                   )
        r53_lambda_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole'))

        r53_lambda = _lambda.Function(
            self, 'r53_lambda',
            function_name='rtcwdemand-r53-lambda',
            runtime=_lambda.Runtime.PYTHON_3_8,
            code=_lambda.Code.from_asset("lambdas/r53lambda"), 
            handler='main.handler',
            role=r53_lambda_role,
            timeout=Duration.seconds(10),
            memory_size=128
        )
        
        r53_lambda.add_environment("DNS_HOSTED_ZONE", settings["dns_hosted_zone"])
        r53_lambda.add_environment("DNS_HOSTED_ZONE_NAME", settings["dns_zone_name"])
               
        policy = iam.Policy(
            self,
            "r53lambdaPolicy",
            policy_name="rtcwdemand_r53_lambda_Policy_" + hostname_suffix,
            statements=[
                iam.PolicyStatement(resources=["arn:aws:route53:::hostedzone/" + settings["dns_hosted_zone"]],
                                    sid="AllowChangeRecords",
                                    effect=iam.Effect.ALLOW,
                                    actions=["route53:ChangeResourceRecordSets"]
                ),
                iam.PolicyStatement(resources=["*"],
                                    sid="AllowDescribeENI",
                                    effect=iam.Effect.ALLOW,
                                    actions=["ec2:DescribeNetworkInterfaces"]
                )
            ]
        )

        r53_lambda_role.attach_inline_policy(policy=policy)
        
        ecsdecrement_lambda_role = iam.Role(self, "LambdaECSDecrement",
                                   role_name='rtcwdemand-ecsdecrement-lambda-role-' + hostname_suffix,
                                   assumed_by=iam.ServicePrincipal("lambda.amazonaws.com")
                                   )
        ecsdecrement_lambda_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole'))
        
        policy = iam.Policy(
            self,
            "ecsdecrementPolicy" + hostname_suffix,
            policy_name="rtcwdemand_ecsdecrement_lambda_policy" + hostname_suffix,
            statements=[
                iam.PolicyStatement(resources=["arn:aws:ecs:" + self.region + ":" + self.account + ":service/" + settings["ECS_CLUSTER_NAME"] + "/" + settings["ECS_SERVICE_NAME"]],
                                    sid="AllowChangeCluster" + hostname_suffix,
                                    effect=iam.Effect.ALLOW,
                                    actions=["ecs:UpdateService", "ecs:DescribeServices"]
                )
            ]
        )

        ecsdecrement_lambda_role.attach_inline_policy(policy=policy)
        
        ecsdecrement_lambda = _lambda.Function(
            self, 'ecsdecrement_lambda',
            function_name='rtcwdemand-ecsdecrement-lambda',
            runtime=_lambda.Runtime.PYTHON_3_8,
            code=_lambda.Code.from_asset("lambdas/ecsdecrement"), 
            handler='main.handler',
            role=ecsdecrement_lambda_role,
            timeout=Duration.seconds(9),
            memory_size=128
        )
        
        ecsdecrement_lambda.add_environment("ECS_SERVICE_NAME", settings["ECS_SERVICE_NAME"])
        ecsdecrement_lambda.add_environment("ECS_CLUSTER_NAME", settings["ECS_CLUSTER_NAME"])
        
        vpc = ec2.Vpc.from_lookup(self, "VPC", is_default=True)
        # vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id = VPC_ID)
        
        cluster = ecs.Cluster(self, 'cluster', cluster_name=settings["ECS_CLUSTER_NAME"], vpc=vpc)
        
        task_definition = ecs.FargateTaskDefinition(self, 'RTCWPro',
                                                    cpu=256,
                                                    memory_limit_mib  = 512
                                                    )
            
        env_vars["HOSTNAME"] = env_vars["HOSTNAME"] + " " + hostname_suffix.upper()
        
        
        container = task_definition.add_container('RTCWProTask',
                                                  logging=ecs.AwsLogDriver(stream_prefix="rtcw_container"),
                                                  image=ecs.ContainerImage.from_registry("msh100/rtcw"),
                                                  environment=env_vars)
        
        port_mapping = ecs.PortMapping(container_port=settings["RTCW_PORT"], host_port=settings["RTCW_PORT"], protocol=ecs.Protocol.UDP) 
        container.add_port_mappings(port_mapping)
        

        rtcw_security_group = ec2.SecurityGroup(self, "SecurityGroup",
                                              vpc=cluster.vpc,
                                              description="Allow ssh access to ec2 instances",
                                              allow_all_outbound=True
                                              )
        rtcw_security_group.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.udp(27960), "allow rtcw access from the world")
        
        service = ecs.FargateService(self, "RTCWProService",
                                     service_name=settings["ECS_SERVICE_NAME"],
                                     cluster=cluster,
                                     task_definition=task_definition,
                                     desired_count=0,
                                     assign_public_ip=True,
                                     security_groups = [rtcw_security_group]
                                     )
        
        eventPattern = events.EventPattern(source=["aws.ecs"], 
                                           detail_type=["ECS Task State Change"], 
                                           detail= {"clusterArn": [cluster.cluster_arn], "lastStatus": ["RUNNING", "STOPPED"]}
                                           )
        lambda_target_r53 = targets.LambdaFunction(handler=r53_lambda)
        
        events.Rule(self,
                    id="ContainerMonitor",
                    rule_name="rtcwdemand-taskchange",
                    targets=[lambda_target_r53],
                    description="Monitor rtcw tasks and target r53 lambda",
                    # event_bus=eventBus,
                    event_pattern=eventPattern,
                    )
        
        #every 8AM run lambda to decrement the task
        lambda_target_ecsdecrement_lambda = targets.LambdaFunction(handler=ecsdecrement_lambda)
        events.Rule(self, "ScheduleRule", schedule=events.Schedule.cron(hour=str(morning_hour)), targets=[lambda_target_ecsdecrement_lambda])
