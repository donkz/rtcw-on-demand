import aws_cdk.aws_lambda as _lambda
import aws_cdk.aws_iam as iam
from aws_cdk import Stack, Duration
from constructs import Construct
import aws_cdk.aws_certificatemanager as acm
import aws_cdk.aws_apigateway as apigw
import aws_cdk.aws_route53 as route53
import aws_cdk.aws_route53_targets as r53targets


class MainRegionSetup(Construct):

    def __init__(self, scope: Construct, id: str, settings: dict, account: str,  **kwargs):
        super().__init__(scope, id, **kwargs)

        ecs_lambda_role = iam.Role(self, "LambdaECS",
                                   role_name='rtcwdemand-ecs-lambda-role',
                                   assumed_by=iam.ServicePrincipal("lambda.amazonaws.com")
                                   )
        ecs_lambda_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole'))

        ecs_lambda = _lambda.Function(
            self, 'ecs_lambda',
            function_name='rtcwdemand-ecs-lambda',
            runtime=_lambda.Runtime.PYTHON_3_8,
            code=_lambda.Code.from_asset("lambdas/ecslambda"), 
            handler='main.handler',
            role=ecs_lambda_role,
            timeout=Duration.seconds(10),
            memory_size=128
        )
        
        ecs_lambda.add_environment("ECS_SERVICE_NAME", settings["ECS_SERVICE_NAME"])
        ecs_lambda.add_environment("ECS_CLUSTER_NAME", settings["ECS_CLUSTER_NAME"])
        
        all_ecs_clusters = self.list_clusters(settings, account)
        
        policy = iam.Policy(
            self,
            "ecslambdaPolicy",
            policy_name="rtcwdemand_ecs_lambda_Policy",
            statements=[
                iam.PolicyStatement(resources=all_ecs_clusters,
                                    sid="AllowChangeRecords",
                                    effect=iam.Effect.ALLOW,
                                    actions=["ecs:UpdateService", "ecs:DescribeServices"]
                )
            ]
        )

        ecs_lambda_role.attach_inline_policy(policy=policy)
        
        # the following role will be able to execute this lambda from another AWS resource
        if settings.get("other_role", None):
            other_role = iam.Role.from_role_arn(self, id="other_role", role_arn=settings["other_role"])
            ecs_lambda.grant_invoke(other_role)
            
        cert = acm.Certificate.from_certificate_arn(self, "Certificate", settings["cert_arn"])

        api = apigw.RestApi(self, "rtcwdemand",
                            domain_name={
                                "domain_name": settings["dns_api_url"],
                                "certificate": cert
                                },
                            default_cors_preflight_options={
                                "allow_origins": apigw.Cors.ALL_ORIGINS,
                                "allow_methods": apigw.Cors.ALL_METHODS
                                }
                            )
        
        zone = route53.HostedZone.from_hosted_zone_attributes(self, "rtcwdemand_apiname", 
                                                              hosted_zone_id=settings["dns_hosted_zone"], 
                                                              zone_name=settings["dns_zone_name"]
                                                              )

        route53.ARecord(self, 'AliasRecord2',
                        record_name=settings["dns_record_name"],
                        target=route53.RecordTarget.from_alias(r53targets.ApiGateway(api)),
                        zone=zone)

        start_resource = api.root.add_resource("start")
        start_region_id = start_resource.add_resource("{region}")
        ecs_lambda_integration = apigw.LambdaIntegration(ecs_lambda)
        start_region_id.add_method("GET", ecs_lambda_integration)

        plan = api.add_usage_plan("UsagePlan",name="Easy",throttle={"rate_limit": 1, "burst_limit": 1 })
        plan.add_api_stage(stage=api.deployment_stage)
        
    def list_clusters(self, settings, account):
        clusters = []
        for region_code, region in settings["regions"].items():
            clusters.append("arn:aws:ecs:" + region + ":" + account + ":service/" + settings["ECS_CLUSTER_NAME"] + "/" + settings["ECS_SERVICE_NAME"])
        return clusters
    

