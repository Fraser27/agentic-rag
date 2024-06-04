#!/usr/bin/env python3
import os

import aws_cdk as cdk
from aws_cdk import Stack, Tags
from agentic_rag_infra.agentic_rag import AgenticRAG
from infrastructure.api_gw_stack import ApiGw_Stack

app = cdk.App()

def tag_my_stack(stack):
    tags = Tags.of(stack)
    tags.add("project", "agentic-rag")

account_id = os.getenv('CDK_DEFAULT_ACCOUNT')
region = os.getenv('CDK_DEFAULT_REGION')
env=cdk.Environment(account=account_id, region=region)

env_name = app.node.try_get_context("environment_name")
AgenticRAG(app, f"agentic-rag-{env_name}-stack", env=env
    # If you don't specify 'env', this stack will be environment-agnostic.
    # Account/Region-dependent features and context lookups will not work,
    # but a single synthesized template can be deployed anywhere.

    # Uncomment the next line to specialize this stack for the AWS Account
    # and Region that are implied by the current CLI configuration.

    #env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),

    # Uncomment the next line if you know exactly what Account and Region you
    # want to deploy the stack to. */

    #env=cdk.Environment(account='123456789012', region='us-east-1'),

    # For more information, see https://docs.aws.amazon.com/cdk/latest/guide/environments.html
    )

api_gw_stack = ApiGw_Stack(app, f'agentic-rag-api-{env_name}')
tag_my_stack(api_gw_stack)
app.synth()

