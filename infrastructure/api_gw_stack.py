from aws_cdk import (
    Stack,
    aws_iam as _iam,
    aws_lambda as _lambda,
    aws_ecr as _ecr, 
    aws_s3 as _s3
)
import uuid
import aws_cdk as _cdk
import os
from constructs import Construct, DependencyGroup
import cdk_nag as _cdk_nag
from cdk_nag import NagSuppressions, NagPackSuppression

class ApiGw_Stack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.stack_level_suppressions()
        env_name = self.node.try_get_context("environment_name")
        current_timestamp = self.node.try_get_context('current_timestamp')
        region=os.getenv('CDK_DEFAULT_REGION')
        account_id = os.getenv('CDK_DEFAULT_ACCOUNT')
        collection_endpoint = 'random'
        secret_api_key = self.node.try_get_context("secret_api_key")
        is_opensearch = self.node.try_get_context("is_aoss")
        embed_model_id = self.node.try_get_context("embed_model_id")

        html_header_name = 'Amazon Bedrock'
        try:
            collection_endpoint = self.node.get_context("collection_endpoint")
            collection_endpoint = collection_endpoint.replace("https://", "")
        except Exception as e:
            pass

        env_params = self.node.try_get_context(env_name)
        print(f'Collection_endpoint={collection_endpoint}')
        
        print(f'Secret Key={secret_api_key}')
        
        bucket_name = f'{env_params["s3_files_data"]}-{account_id}-{region}'
        
        # Define API's
        # Base URL
        api_description = "Agentic RAG APIs"

        
        rag_llm_root_api = _cdk.aws_apigateway.RestApi(
            self,
            env_params["agentic-rag-api"],
            deploy=True,
            endpoint_types=[_cdk.aws_apigateway.EndpointType.REGIONAL],
            deploy_options={
                "stage_name": env_name,
                "throttling_rate_limit": 100,
                "description": env_name + " stage deployment",
            },
            description=api_description,
        )

        secure_key = _cdk.aws_apigateway.ApiKey(self,
                                                f"agent-rag-api-{env_name}",
                                                api_key_name=secret_api_key,
                                                enabled=True,
                                                value=secret_api_key,
                                                description="Secure access to API's")
        
        plan = _cdk.aws_apigateway.UsagePlan(self, f"agent-rag-api-plan-{env_name}", 
                                            throttle=_cdk.aws_apigateway.ThrottleSettings(burst_limit=50, rate_limit=200),
                                            quota=_cdk.aws_apigateway.QuotaSettings(limit=500, period=_cdk.aws_apigateway.Period.MONTH),
                                            api_stages= [_cdk.aws_apigateway.UsagePlanPerApiStage(api=rag_llm_root_api,
                                                                                                stage=rag_llm_root_api.deployment_stage)]
                                                                                                
                                            )
        plan.add_api_key(secure_key)
            
        parent_path='rag'
        rag_llm_api = rag_llm_root_api.root.add_resource(parent_path)
        rest_endpoint_url = f'https://{rag_llm_root_api.rest_api_id}.execute-api.{region}.amazonaws.com/{env_name}/{parent_path}/'
        
        print(rest_endpoint_url)
        
        # Lets create an S3 bucket to store Images and also an API call
        # create s3 bucket to store ocr related objects
        cors_s3_link = f'https://{rag_llm_root_api.rest_api_id}.execute-api.{region}.amazonaws.com'
        self.images_bucket = _s3.Bucket(self,
                                        id=env_params["s3_files_data"],
                                        bucket_name=bucket_name,
                                        auto_delete_objects=True,
                                        removal_policy=_cdk.RemovalPolicy.DESTROY,
                                        cors= [_s3.CorsRule(allowed_headers=["*"],
                                                            allowed_origins=[cors_s3_link],
                                                            allowed_methods=[_s3.HttpMethods.GET, _s3.HttpMethods.POST],
                                                            id="serverless-rag-demo-cors-rule")],
                                        versioned=False)
        
        method_responses = [
            # Successful response from the integration
            {
                "statusCode": "200",
                # Define what parameters are allowed or not
                "responseParameters": {
                    "method.response.header.Content-Type": True,
                    "method.response.header.Access-Control-Allow-Origin": True,
                    "method.response.header.Access-Control-Allow-Credentials": True,
                },
            }
        ]

        
        custom_lambda_role = _iam.Role(self, f'llm_rag_role_{env_name}', 
                    role_name= env_params['lambda_role_name'] + '_' + region,
                    assumed_by= _iam.ServicePrincipal('lambda.amazonaws.com'),
                    managed_policies= [
                        _iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
                    ]
                )

        lambda_function = None
        bedrock_query_lambda_integration = None
        bedrock_index_lambda_integration = None
        wss_url=''
        
        # These are created in buildspec-bedrock.yml file.
        boto3_bedrock_layer = _lambda.LayerVersion.from_layer_version_arn(self, f'boto3-bedrock-layer-{env_name}',
                                                   f'arn:aws:lambda:{region}:{account_id}:layer:{env_params["boto3_bedrock_layer"]}:1')
        
        opensearchpy_layer = _lambda.LayerVersion.from_layer_version_arn(self, f'opensearchpy-layer-{env_name}',
                                                   f'arn:aws:lambda:{region}:{account_id}:layer:{env_params["opensearchpy_layer"]}:1')
        
        aws4auth_layer = _lambda.LayerVersion.from_layer_version_arn(self, f'aws4auth-layer-{env_name}',
                                                   f'arn:aws:lambda:{region}:{account_id}:layer:{env_params["aws4auth_layer"]}:1')
        
        langchainpy_layer = _lambda.LayerVersion.from_layer_version_arn(self, f'langchain-layer-{env_name}',
                                                   f'arn:aws:lambda:{region}:{account_id}:layer:{env_params["langchainpy_layer_name"]}:1')
        
        print('--- Amazon Bedrock Deployment ---')
        
        
        bedrock_indexing_lambda_function = _lambda.Function(self, f'llm-bedrock-index-{env_name}',
                              function_name=env_params['bedrock_indexing_function_name'],
                              code = _cdk.aws_lambda.Code.from_asset(os.path.join(os.getcwd(), 'artifacts/bedrock_lambda/index_lambda/')),
                              runtime=_lambda.Runtime.PYTHON_3_10,
                              handler="index.handler",
                              role=custom_lambda_role,
                              timeout=_cdk.Duration.seconds(300),
                              description="Create embeddings in Amazon Bedrock",
                              environment={ 'VECTOR_INDEX_NAME': env_params['index_name'],
                                            'OPENSEARCH_VECTOR_ENDPOINT': collection_endpoint,
                                            'REGION': region,
                                            'S3_BUCKET_NAME': bucket_name,
                                            'EMBED_MODEL_ID': embed_model_id
                              },
                              memory_size=3000,
                              layers= [boto3_bedrock_layer , opensearchpy_layer, aws4auth_layer, langchainpy_layer])
        
        lambda_function = bedrock_indexing_lambda_function
        bedrock_querying_lambda_function = _lambda.Function(self, f'llm-bedrock-query-{env_name}',
                              function_name=env_params['bedrock_querying_function_name'],
                              code = _cdk.aws_lambda.Code.from_asset(os.path.join(os.getcwd(), 'artifacts/bedrock_lambda/query_lambda/')),
                              runtime=_lambda.Runtime.PYTHON_3_10,
                              handler="query_rag_bedrock.handler",
                              role=custom_lambda_role,
                              timeout=_cdk.Duration.seconds(300),
                              description="Query Models in Amazon Bedrock",
                              environment={ 'VECTOR_INDEX_NAME': env_params['index_name'],
                                            'OPENSEARCH_VECTOR_ENDPOINT': collection_endpoint,
                                            'REGION': region,
                                            'REST_ENDPOINT_URL': rest_endpoint_url,
                                            'IS_RAG_ENABLED': is_opensearch,
                                            'S3_BUCKET_NAME': bucket_name,
                                            'EMBED_MODEL_ID': embed_model_id
                              },
                              memory_size=3000,
                              layers= [boto3_bedrock_layer , opensearchpy_layer, aws4auth_layer, langchainpy_layer]
                            )
        
        
        websocket_api = _cdk.aws_apigatewayv2.CfnApi(self, f'agentic-rag-streaming-{env_name}',
                                    protocol_type='WEBSOCKET',
                                    name=env_params['agentic-rag-streaming-socket'],
                                    route_selection_expression='$request.body.action'
                                    )
        
        print(f'Bedrock streaming wss url {websocket_api.attr_api_endpoint}')
        wss_url = websocket_api.attr_api_endpoint
        bedrock_oss_policy = _iam.PolicyStatement(
            actions=[
                "aoss:ListCollections", "aoss:BatchGetCollection", "aoss:APIAccessAll", "lambda:InvokeFunction",
                "apigateway:GET", "apigateway:DELETE", "apigateway:PATCH", "apigateway:POST", "apigateway:PUT",
                "execute-api:InvalidateCache", "execute-api:Invoke", "execute-api:ManageConnections",
                "bedrock:ListFoundationModelAgreementOffers", "bedrock:ListFoundationModels","bedrock:GetFoundationModel",
                "bedrock:GetFoundationModelAvailability", "bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream",
                "iam:ListUsers", "iam:ListRoles", "s3:*", "textract:*"],
            resources=["*"],
        )
        bedrock_querying_lambda_function.add_to_role_policy(bedrock_oss_policy)
        bedrock_indexing_lambda_function.add_to_role_policy(bedrock_oss_policy)
        
        bedrock_querying_lambda_function.add_environment('WSS_URL', wss_url + '/' + env_name)
        bedrock_index_lambda_integration = _cdk.aws_apigateway.LambdaIntegration(
        bedrock_indexing_lambda_function, proxy=True, allow_test_invoke=True)
        bedrock_query_lambda_integration = _cdk.aws_apigateway.LambdaIntegration(
        bedrock_querying_lambda_function, proxy=True, allow_test_invoke=True)
        apigw_role = _iam.Role(self, f'bedrock-lambda-invoke-{env_name}', assumed_by=_iam.ServicePrincipal('apigateway.amazonaws.com'))
        apigw_role.add_to_policy(_iam.PolicyStatement(effect=_iam.Effect.ALLOW,
                            actions=["lambda:InvokeFunction"],
                            resources=[bedrock_querying_lambda_function.function_arn], 
                            ))
        
        websocket_integrations = _cdk.aws_apigatewayv2.CfnIntegration(self, f'bedrock-websocket-integration-{env_name}',
                                            api_id=websocket_api.ref,
                                            integration_type="AWS_PROXY",
                                            integration_uri="arn:aws:apigateway:" + region + ":lambda:path/2015-03-31/functions/" + bedrock_querying_lambda_function.function_arn + "/invocations",
                                            credentials_arn=apigw_role.role_arn
                                            )
        
        websocket_connect_route = _cdk.aws_apigatewayv2.CfnRoute(self, f'bedrock-connect-route-{env_name}',
                                        api_id=websocket_api.ref, route_key="$connect",
                                        authorization_type="NONE",
                                        target="integrations/"+ _cdk.aws_apigatewayv2.CfnIntegration(self, f"bedrock-socket-conn-integration-{env_name}",
                                                                                                     api_id= websocket_api.ref,
                                                                                                     integration_type="AWS_PROXY",
                                                                                                     integration_uri="arn:aws:apigateway:" + region + ":lambda:path/2015-03-31/functions/" + bedrock_querying_lambda_function.function_arn + "/invocations",
                                                                                                     credentials_arn= apigw_role.role_arn).ref
        )
        dependencygrp = DependencyGroup()
        dependencygrp.add(websocket_connect_route)
        
        websocket_disconnect_route = _cdk.aws_apigatewayv2.CfnRoute(self, f'bedrock-disconnect-route-{env_name}',
                                        api_id=websocket_api.ref, route_key="$disconnect",
                                        authorization_type="NONE",
                                        target="integrations/" + websocket_integrations.ref)
        
        websocket_default_route = _cdk.aws_apigatewayv2.CfnRoute(self, f'bedrock-default-route-{env_name}',
                                        api_id=websocket_api.ref, route_key="$default",
                                        authorization_type="NONE",
                                        target="integrations/" + websocket_integrations.ref)
        websocket_bedrock_route = _cdk.aws_apigatewayv2.CfnRoute(self, f'bedrock-route-{env_name}',
                                        api_id=websocket_api.ref, route_key="bedrock",
                                        authorization_type="NONE",
                                        target="integrations/" + websocket_integrations.ref)
        
        
        deployment = _cdk.aws_apigatewayv2.CfnDeployment(self, f'bedrock-streaming-deploy-{env_name}', api_id=websocket_api.ref)
        deployment.add_dependency(websocket_connect_route)
        deployment.add_dependency(websocket_disconnect_route)
        deployment.add_dependency(websocket_bedrock_route)
        deployment.add_dependency(websocket_default_route)
        
        websocket_stage = _cdk.aws_apigatewayv2.CfnStage(self, f'bedrock-streaming-stage-{env_name}', 
                                       api_id=websocket_api.ref,
                                       auto_deploy=True,
                                       deployment_id= deployment.ref,
                                       stage_name= env_name) 
            
        html_generation_function = _cdk.aws_lambda.Function(self, f'llm_html_function_{env_name}',
                                            function_name=env_params['agentic-rag-html-function'],
                                            runtime=_cdk.aws_lambda.Runtime.PYTHON_3_9,
                                            memory_size=128,
                                            handler='llm_html_generator.handler',
                                            timeout=_cdk.Duration.minutes(1),
                                            code=_cdk.aws_lambda.Code.from_asset(os.path.join(os.getcwd(), 'artifacts/html_lambda/')),
                                            environment={ 'ENVIRONMENT': env_name,
                                                          'LLM_MODEL_NAME': html_header_name,
                                                          'WSS_URL': wss_url + '/' + env_name,
                                                          'IS_RAG_ENABLED': is_opensearch
                                                        })        
    
        oss_policy = _iam.PolicyStatement(
            actions=[
                "aoss:*",
                "sagemaker:*",
                "iam:ListUsers",
                "iam:ListRoles",
                "apigateway:*"
            ],
            resources=["*"],
        )

        lambda_function.add_to_role_policy(oss_policy)
        

        lambda_integration = _cdk.aws_apigateway.LambdaIntegration(
            lambda_function, proxy=True, allow_test_invoke=True
        )

        html_generation_lambda_integration = _cdk.aws_apigateway.LambdaIntegration(
            html_generation_function, proxy=True, allow_test_invoke=True
        )

        rag_llm_api.add_method("GET",
                                html_generation_lambda_integration, operation_name="HTML file",
                                method_responses=method_responses)

        query_api = rag_llm_api.add_resource("query")
        index_docs_api = rag_llm_api.add_resource("index-documents")
        detect_text_api = rag_llm_api.add_resource("detect-text")
        index_files_api = rag_llm_api.add_resource("index-files")
        get_job_status_api = rag_llm_api.add_resource("get-job-status")
        get_presigned_url_api = rag_llm_api.add_resource("get-presigned-url")
        
        index_sample_data_api = rag_llm_api.add_resource("index-sample-data")
        file_data_api = rag_llm_api.add_resource("file_data")
        connect_tracker_api = rag_llm_api.add_resource("connect-tracker")
        
    
        index_docs_api.add_method(
            "POST",
            bedrock_index_lambda_integration,
            operation_name="index document",
            method_responses=method_responses,
            api_key_required=True
        )
        index_docs_api.add_method(
            "DELETE",
            bedrock_index_lambda_integration,
            operation_name="delete document index",
            method_responses=method_responses,
            api_key_required=True
        )
    
        index_sample_data_api.add_method(
            "POST",
            bedrock_index_lambda_integration,
            operation_name="index sample document",
            method_responses=method_responses,
            api_key_required=True
        )
        detect_text_api.add_method(
            "POST",
            lambda_integration,
            operation_name="Detect Text or Index a file",
            api_key_required=True,
            method_responses=method_responses,
        )
        index_files_api.add_method(
            "POST",
            lambda_integration,
            operation_name="Index a file",
            api_key_required=True,
            method_responses=method_responses,
        )
        get_job_status_api.add_method(
            "GET",
            lambda_integration,
            operation_name="Get Job Status",
            api_key_required=True,
            method_responses=method_responses,
        )
        get_presigned_url_api.add_method(
            "GET",
            lambda_integration,
            operation_name="Get Presigned Post URL",
            api_key_required=True,
            method_responses=method_responses,
        )
        file_data_api.add_method(
            "POST",
            bedrock_query_lambda_integration,
            operation_name="Store documents",
            method_responses=method_responses,
            api_key_required=True
        )
        self.add_cors_options(file_data_api)
        connect_tracker_api.add_method(
            "GET",
            bedrock_index_lambda_integration,
            operation_name="Websocket rate limiter",
            method_responses=method_responses,
            api_key_required=True
        )
        self.add_cors_options(connect_tracker_api)
        self.add_cors_options(get_job_status_api)
        self.add_cors_options(get_presigned_url_api)
        self.add_cors_options(index_files_api)
        self.add_cors_options(detect_text_api)
        
        
        self.add_cors_options(index_docs_api)
        self.add_cors_options(query_api)
        self.add_cors_options(index_sample_data_api)
        

    def add_cors_options(self, apiResource: _cdk.aws_apigateway.IResource):
        apiResource.add_method(
            "OPTIONS",
            _cdk.aws_apigateway.MockIntegration(
                integration_responses=[
                    {
                        "statusCode": "200",
                        "responseParameters": {
                            "method.response.header.Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Amz-User-Agent'",
                            "method.response.header.Access-Control-Allow-Origin": "'*'",
                            "method.response.header.Access-Control-Allow-Credentials": "'false'",
                            "method.response.header.Access-Control-Allow-Methods": "'OPTIONS,GET,PUT,POST,DELETE'",
                        },
                    }
                ],
                passthrough_behavior=_cdk.aws_apigateway.PassthroughBehavior.NEVER,
                request_templates={"application/json": '{"statusCode": 200}'},
            ),
            method_responses=[
                {
                    "statusCode": "200",
                    "responseParameters": {
                        "method.response.header.Access-Control-Allow-Headers": True,
                        "method.response.header.Access-Control-Allow-Methods": True,
                        "method.response.header.Access-Control-Allow-Credentials": True,
                        "method.response.header.Access-Control-Allow-Origin": True,
                    },
                }
            ],
        )
    
    def stack_level_suppressions(self):
        NagSuppressions.add_stack_suppressions(self, [
            _cdk_nag.NagPackSuppression(id='AwsSolutions-IAM5', reason='Its a basic lambda execution role, only has access to create/write to a cloudwatch stream'),
            _cdk_nag.NagPackSuppression(id='AwsSolutions-IAM4', reason='Its a basic lambda execution role, only has access to create/write to a cloudwatch stream'),
            _cdk_nag.NagPackSuppression(id='AwsSolutions-APIG4', reason='Remediated, we are using API keys for access control'),
            _cdk_nag.NagPackSuppression(id='AwsSolutions-APIG1', reason='Logging is expensive for websocket streaming responses coming in from LLMs'),
            _cdk_nag.NagPackSuppression(id='AwsSolutions-COG4', reason='Remediated, we are using API keys for access control')
        ])