#!/usr/bin/env python3
import os
import aws_cdk as cdk

from stacks.rtcw_on_demand import RtcwOnDemandStack
from mysettings import settings

app = cdk.App()
for region_code, region_name in settings["regions"].items():
    RtcwOnDemandStack(app, "RtcwOnDemandStack" + region_code, 
                      env=cdk.Environment(account=settings["account"], region=region_name), 
                      settings = settings)

cdk.Tags.of(app).add("purpose", "rtcwdemand")
app.synth()
