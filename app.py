#!/usr/bin/env python3
import os
import aws_cdk as cdk
from aws_ai_agent.aws_ai_agent_stack import AwsAiAgentStack


app = cdk.App()


AwsAiAgentStack(app, "AwsAiAgentStack",
env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'),
region=os.getenv('CDK_DEFAULT_REGION')),
)
app.synth()