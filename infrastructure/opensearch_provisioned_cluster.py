import os
from aws_cdk import (
    NestedStack,
    aws_iam as _iam,
    aws_opensearchservice as _opensearch,
    Tag as _tags,
    CfnOutput as _output,
    Aspects,
    aws_ec2 as _ec2
)
from constructs import Construct
import aws_cdk as _cdk
import os

class OpensearchProvisionedCluster(NestedStack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        env_name = self.node.try_get_context('environment_name')
        env_params = self.node.try_get_context(env_name)
        account_id = os.getenv("CDK_DEFAULT_ACCOUNT")
        region=os.getenv('CDK_DEFAULT_REGION')
        
        cidr_range = env_params['cidr_range']
        vpc_id = env_params['vpc_id']
        security_group_id = env_params['security_group_id']

        opensearch_vpc = None
        if not vpc_id:
            print("No VPC-Id Provided, a new VPC will be created")
            opensearch_vpc = _ec2.Vpc(self, f"oss_cluster_rag_{env_name}", cidr=cidr_range, max_azs=3, 
                subnet_configuration=[
                    _ec2.SubnetConfiguration(name="opensearch-private1", subnet_type=_ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=26),
                    _ec2.SubnetConfiguration(name="opensearch-private2", subnet_type=_ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=26),
                    _ec2.SubnetConfiguration(name="opensearch-private3", subnet_type=_ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=26),
                    _ec2.SubnetConfiguration(name="opensearch-public", subnet_type=_ec2.SubnetType.PUBLIC, cidr_mask=24)
                ]     
                )
        else:
            opensearch_vpc = _ec2.Vpc.from_lookup(self, f"vpc-{env_name}", vpc_id=vpc_id)
        
        os_security_group = None

        if not security_group_id:
            print("No Security Group-Id Provided, a new Security Group will be created")
            os_security_group = _ec2.SecurityGroup(self, f"opensearch-sg-{env_name}", vpc=vpc_id, allow_all_outbound=True)
        else:
            os_security_group = _ec2.SecurityGroup.from_security_group_id(self, f"opensearch-rag-sg-{env_name}", security_group_id=security_group_id)

        os_security_group.add_ingress_rule(_ec2.Peer.ipv4(), _ec2.Port.tcp(443))
        os_security_group.add_ingress_rule(_ec2.Peer.ipv4(), _ec2.Port.tcp(80))
        os_security_group.add_ingress_rule(_ec2.Peer.ipv4(), _ec2.Port.tcp(9200))
        os_security_group.add_ingress_rule(_ec2.Peer.ipv4(), _ec2.Port.tcp(5601))
        os_security_group.add_ingress_rule(_ec2.Peer.ipv4(), _ec2.Port.tcp(8443))
        os_security_group.addIngressRule(os_security_group, _ec2.Port.all_traffic())

        domain = _opensearch.Domain(version= _opensearch.EngineVersion.OPENSEARCH_2_7,
                            domain_name=f"opensearch-rag-llm-{env_name}",
                            capacity={
                                "data_nodes": 2,
                                "data_node_instance_type": "t4g.large.search"
                            },
                            ebs={
                                "volume_size": 100,
                                "volume_type": _ec2.EbsDeviceVolumeType.GP2
                            },
                            node_to_node_encryption=True,
                            encryption_at_rest={
                                "enabled": True
                            },
                            removal_policy= _cdk.RemovalPolicy.DESTROY,
                            zone_awareness={
                                "availability_zone_count": 3,
                                "enabled": True
                            },
                            enforce_https=True,
                            vpc=opensearch_vpc,
                            access_policies=[
                                _iam.PolicyStatement(
                                    principals=[_iam.AnyPrincipal()],
                                    actions=["es:*"],
                                    resources=["arn:aws:es:*:*:domain/*"])],
                            security_groups=[os_security_group]

        )
