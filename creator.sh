#!/usr/bin/bash 
Green='\033[0;32m'
Red='\033[0;31m'
NC='\033[0m'

if [ -z "$1" ]
then
    infra_env='dev'
else
    infra_env=$1
fi  

if [ $infra_env != "dev" -a $infra_env != "qa" -a $infra_env != "sandbox" ]
then
    echo "Environment name can only be dev or qa or sandbox. example 'sh creator.sh dev' "
    exit 1
fi
echo "Environment: $infra_env"

deployment_region=$(curl -s http://169.254.169.254/task/AvailabilityZone | sed 's/\(.*\)[a-z]/\1/')
embed_model_id='amazon.titan-embed-image-v1'
aoss_selected='no'
oss_selected='no'
oss_stack_name='agentic-rag-oss-stack-'$infra_env
OSDomainName=$(jq '.context.'$infra_env'.oss_domain_name' cdk.json -r)

# oss_params
InstanceType=t3.medium.search
InstanceCount=2
OSPassword=Sillachi@27
OSUsername=admin 

if [ -z "$deployment_region" ]
then
    printf  "$Red !!! Cannot detect region. Manually select your AWS Cloudshell region from the below list $NC"
    printf "\n"
    printf "$Green Please enter your current AWS cloudshell region (1/2/3/4/5/6): $NC"
    printf "\n"
    region_options=("us-east-1" "us-west-2" "ap-southeast-1" "ap-northeast-1" "ap-south-1" "eu-central-1" "Quit")
    select region_opts in "${region_options[@]}"
    do
        case $region_opts in 
            "us-east-1")
                deployment_region='us-east-1'
                printf "$Green Deploy in US East(N.Virginia) $NC"
                printf "\n"
                ;; 
            "us-west-2")
                deployment_region='us-west-2'
                printf "$Green Deploy in US West(Oregon) $NC"
                ;;
            "ap-southeast-1")
                deployment_region='ap-southeast-1'
                printf "$Green Deploy in Asia Pacific (Singapore) $NC"
                ;;
            "ap-northeast-1")
                deployment_region='ap-northeast-1'
                printf "$Green Deploy in Asia Pacific (Tokyo) $NC"
                ;;
            "ap-south-1")
                deployment_region='ap-south-1'
                printf "$Green Deploy in Asia Pacific (Mumbai) $NC"
                ;;
            "eu-central-1")
                deployment_region='eu-central-1'
                printf "$Green Deploy in Europe (Frankfurt) $NC"
                ;;
            "Quit")
                printf "$Red Quit deployment $NC"
                exit 1
                break
                ;;
            *)
            printf "$Red Exiting, Invalid option $REPLY. Select from 1/2/3/4/5/6 $NC"
            exit 1;;
        esac
        break
    done
fi
echo "Selected region: $deployment_region "

echo '*************************************************************'
echo ' '

echo '*************************************************************'
echo ' '

printf "$Green Do you want to deploy Vector DB or just try out Amazon Bedrock: $NC"
printf "\n"
options=("Amazon Opensearch Serverless vector engine" "Amazon Opensearch - provisioned" "Quit")

select opt in "${options[@]}"
do
    case $opt in
        "Amazon Opensearch Serverless vector engine")
            aoss_selected='yes'
            printf "$Green Amazon Opensearch serverless selected $NC"
            ;;
        "Amazon Opensearch - provisioned")
            oss_selected='yes'
            printf "$Green Amazon Opensearch provisioned selected $NC"
            ;;
        "Quit")
            printf "$Red Quit deployment $NC"
            exit 1
            break
            ;;
        *)
        printf "$Red Exiting, Invalid option $REPLY . Select from 1/2/3 $NC"
        exit 1
        ;;
    esac
    break
done
 
echo '*************************************************************'
echo ' '        
    
printf "$Green Enter a custom secret API Key(atleast 20 Characters long) to secure access to Bedrock APIs. Secret can contain (alphabets, numbers and hyphens) $NC"
read secret_api_key
secret_len=${#secret_api_key}

if [ $secret_len -lt 20 ]
then
    printf "$Red Secret Cannot be less than 20 characters. \n Exit \n $NC"
    exit
fi

if ! [[ $secret_api_key =~ ^[a-zA-Z0-9-]+$ ]]
then
    printf "$Red Secret can contain only words/digits or hyphens example: bedrock-sample-demo-access. \n Exiting setup \n $NC"
    exit
fi

if [ $oss_selected = "yes" ]
then
    echo ' '
    echo '*************************************************************'
    echo ' '
    printf "$Green Enter password for Amazon Opensearch cluster (The master user password must contain at least one uppercase letter, one lowercase letter, one number, and one special character) $NC"        
    read OSPassword

    echo ' '
    echo '*************************************************************'
    echo ' '
    printf "$Green Press Enter to proceed with deployment else ctrl+c to cancel $NC "
    read -p " "
    
    stack_exists=$(aws cloudformation describe-stacks --stack-name "$oss_stack_name" --region "$deployment_region" --query 'Stacks[0].StackStatus')
    printf "$Green Deploying OSS cluster with password $OSPassword $NC"
    if [ -z "$stack_exists" ]
    then
        echo "Creating new CloudFormation stack: $oss_stack_name"
        aws cloudformation create-stack --stack-name $oss_stack_name --region "$deployment_region" --template-body file://opensearch-cluster.yaml --parameters ParameterKey=InstanceType,ParameterValue=$InstanceType ParameterKey=InstanceCount,ParameterValue=$InstanceCount ParameterKey=OSPassword,ParameterValue=$OSPassword ParameterKey=OSUsername,ParameterValue=$OSUsername ParameterKey=OSDomainName,ParameterValue=$OSDomainName --capabilities CAPABILITY_NAMED_IAM
        
    elif [ "$stack_status" != "CREATE_COMPLETE" ]
    then
            printf "\n"
            echo $oss_stack_name status is $stack_exists
            printf "$Green $oss_stack_name which contains the Opensearch vector database is in  "$stack_status" state. Do you want to delete the stack ? $NC"
            printf "\n"
            options=("Yes - Delete Stack" "No - Update existing stack" "Quit")
            select opt in "${options[@]}"
            do
                case $opt in
                    "Yes - Delete Stack")
                    printf "$Green Deleting existing $oss_stack_name stack  $NC"
                    aws cloudformation delete-stack --stack-name $oss_stack_name --region "$deployment_region"
                    printf "\n"
                    printf "$Green Wait for 60 seconds for stack deletion $NC"
                    sleep 60
                    printf "\n"
                    printf "$Green Creating new stack. Provision new Amazon Openseach cluster. $NC"
                    aws cloudformation create-stack --stack-name $oss_stack_name --region "$deployment_region" --template-body file://opensearch-cluster.yaml --parameters ParameterKey=InstanceType,ParameterValue=$InstanceType ParameterKey=InstanceCount,ParameterValue=$InstanceCount ParameterKey=OSPassword,ParameterValue=$OSPassword ParameterKey=OSUsername,ParameterValue=$OSUsername ParameterKey=OSDomainName,ParameterValue=$OSDomainName --capabilities CAPABILITY_NAMED_IAM
                    printf "\n"
                    ;;
                    "No - Update existing stack")
                    printf "$Green Updating existing $oss_stack_name stack $NC"
                    aws cloudformation update-stack --stack-name $oss_stack_name --region "$deployment_region" --template-body file://opensearch-cluster.yaml --parameters ParameterKey=InstanceType,ParameterValue=$InstanceType ParameterKey=InstanceCount,ParameterValue=$InstanceCount ParameterKey=OSPassword,ParameterValue=$OSPassword ParameterKey=OSUsername,ParameterValue=$OSUsername ParameterKey=OSDomainName,ParameterValue=$OSDomainName --capabilities CAPABILITY_NAMED_IAM
                    printf "\n"
                    ;;
                    "Quit")
                    printf "$Red Quit deployment $NC"
                    exit 1
                    break
                    ;;
                *)
                printf "$Red Exiting, Invalid option $REPLY . Select from 1/2/3 $NC"
                exit 1
                ;;
                esac
                break
            done
    else
            printf "$Green Updating existing $oss_stack_name stack $NC"
            aws cloudformation update-stack --stack-name $oss_stack_name --region "$deployment_region" --template-body file://opensearch-cluster.yaml --parameters ParameterKey=InstanceType,ParameterValue=$InstanceType ParameterKey=InstanceCount,ParameterValue=$InstanceCount ParameterKey=OSPassword,ParameterValue=$OSPassword ParameterKey=OSUsername,ParameterValue=$OSUsername ParameterKey=OSDomainName,ParameterValue=$OSDomainName --capabilities CAPABILITY_NAMED_IAM
            printf "\n"
        
    fi
    
    printf "$Green Check stack deployment status every 60 seconds $NC"
    j=0
    stack_status_1=READY
    while [ $j -lt 50 ];
    do 
        echo 'Wait for 60 seconds. Provisioning Amazon Opensearch domain'
        sleep 60
        stack_status_1=$(aws cloudformation describe-stacks --stack-name $oss_stack_name --region "$deployment_region" --query "Stacks[0].StackStatus")
        echo "Current Amazon Opensearch cluster Status $stack_status_1"
        if [[ "$stack_status_1" =~ "COMPLETE"|"FAILED" ]]
        then
            echo "Build complete: $oss_stack_name : status $stack_status_1"
            if [[ "$stack_status_1" =~ "CREATE_COMPLETE" ]]
            then
                echo "Opensearch Cluster created: $oss_stack_name : status $stack_status_1"
                break
            else
                echo "Exiting due to Build failure: $oss_stack_name is in $stack_status_1 state"
                exit 1
            fi
        else
            echo "Current Amazon Opensearch cluster Status $stack_status_1"
            
        fi
    ((j++))
    done

fi

echo ' '
echo '*************************************************************'
echo ' '
cd ..
echo "--- Upgrading npm ---"
sudo npm install n stable -g
echo "--- Installing cdk ---"
sudo npm install -g aws-cdk@2.91.0

echo "--- Bootstrapping CDK on account in region $deployment_region ---"
cdk bootstrap aws://$(aws sts get-caller-identity --query "Account" --output text)/$deployment_region

cd agentic-rag
echo "--- pip install requirements ---"
python3 -m pip install -r requirements.txt

domain_endpoint='https://dummy-endpoint'

echo "--- CDK synthesize ---"
cdk synth -c environment_name=$infra_env -c current_timestamp=$CURRENT_UTC_TIMESTAMP -c secret_api_key=$secret_api_key -c is_aoss=$aoss_selected  -c is_oss=$oss_selected  -c embed_model_id=$embed_model_id

echo "--- CDK deploy ---"
CURRENT_UTC_TIMESTAMP=$(date -u +"%Y%m%d%H%M%S")
echo Setting Tagging Lambda Image with timestamp $CURRENT_UTC_TIMESTAMP
cdk deploy -c environment_name=$infra_env -c current_timestamp=$CURRENT_UTC_TIMESTAMP -c secret_api_key="$secret_api_key" -c is_aoss="$aoss_selected" -c is_oss=$oss_selected -c embed_model_id=$embed_model_id agentic-rag-"$infra_env"-stack --require-approval never
echo "--- Get Build Container ---"
project=agenticragcntnr"$infra_env"
echo project: $project
build_container=$(aws codebuild list-projects|grep -o $project'[^,"]*')
echo container: $build_container
echo "--- Trigger Build ---"
BUILD_ID=$(aws codebuild start-build --project-name $build_container | jq '.build.id' -r)
echo Build ID : $BUILD_ID
if [ "$?" != "0" ]; then
    echo "Could not start CodeBuild project. Exiting."
    exit 1
else
    echo "Build started successfully."
fi

echo "Check build status every 30 seconds. Wait for codebuild to finish"
j=0
while [ $j -lt 50 ];
do 
    sleep 30
    echo 'Wait for 30 seconds. Build job typically takes 15 minutes to complete...'
    build_status=$(aws codebuild batch-get-builds --ids $BUILD_ID | jq -cs '.[0]["builds"][0]["buildStatus"]')
    build_status="${build_status%\"}"
    build_status="${build_status#\"}"
    if [ $build_status = "SUCCEEDED" ] || [ $build_status = "FAILED" ] || [ $build_status = "STOPPED" ]
    then
        echo "Build complete: $latest_build : status $build_status"
        break
    fi
    ((j++))
done

if [ $build_status = "SUCCEEDED" ]
then
    COLLECTION_ENDPOINT=https://dummy-vector-endpoint.amazonaws.com
    

    if [ $aoss_selected = "yes" ]
    then
        COLLECTION_NAME=$(jq '.context.'$infra_env'.collection_name' cdk.json -r)
        COLLECTION_ENDPOINT=$(aws opensearchserverless batch-get-collection --names $COLLECTION_NAME |jq '.collectionDetails[0]["collectionEndpoint"]' -r)
    fi

    if [ $oss_selected = "yes" ]
    then
        domain_endpoint=$(aws cloudformation describe-stacks --stack-name $oss_stack_name --query "Stacks[0].Outputs[0].OutputValue")
        COLLECTION_ENDPOINT=$domain_endpoint
    fi
    
    cdk deploy -c environment_name=$infra_env -c collection_endpoint=$COLLECTION_ENDPOINT -c current_timestamp=$CURRENT_UTC_TIMESTAMP -c secret_api_key=$secret_api_key -c is_aoss=$aoss_selected -c is_oss=$oss_selected -c embed_model_id=$embed_model_id agentic-rag-api-"$infra_env" --require-approval never

else
    echo "Exiting. Build did not succeed."
fi

echo "Deployment Complete"
