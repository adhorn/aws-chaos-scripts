## Disclaimer

⚠️USE AT YOUR OWN RISK⚠️

Using these scripts may create an unreasonable risk. If you choose to use the scripts provided here in your own activities, you do so at your own risk.
None of the authors or contributors, or anyone else connected with these scripts, in any way whatsoever, can be responsible for your use of the scripts contained in this repository. 
Use these scripts only if you understand what the code does


## Collection of python scripts to inject failure in the AWS Infrastructure.

1. script-fail-az: simulate the lose of an Availability Zone (AZ) in a VPC.

     ```shell
        ❯ script-fail-az --help
        usage: script-fail-az   [-h] --region REGION --vpc-id VPC_ID --az-name AZ_NAME
                                [--duration DURATION] [--failover-rds FAILOVER_RDS]
                                [--failover-elasticache FAILOVER_ELASTICACHE]
                                [--log-level LOG_LEVEL]

        Simulate AZ failure: associate subnet(s) with a Chaos NACL that deny ALL
        Ingress and Egress traffic - blackhole

        optional arguments:
        -h, --help            show this help message and exit
        --region REGION       The AWS region of choice (default: None)
        --vpc-id VPC_ID       The VPC ID of choice (default: None)
        --az-name AZ_NAME     The name of the availability zone to blackout
                                (default: None)
        --duration DURATION   The duration, in seconds, of the blackout (default: 60)
        --failover-rds FAILOVER_RDS
                              Failover RDS if master in AZ_NAME
                                (default: False)
        --failover-elasticache FAILOVER_ELASTICACHE
                               Failover Elasticache if primary in AZ_NAME
                                (default: False)
        --log-level LOG_LEVEL  Python log level. INFO, DEBUG, etc. (default: INFO)
    ```



2. script-stop-instance: randomly kill an instance in a particular AZ if proper tags. 

    ```shell
        ❯ script-stop-instance --help
        usage: script-stop-instance [-h] [--log-level LOG_LEVEL] [--region REGION]
                                    [--az-name AZ_NAME] [--tag-name TAG_NAME]
                                    [--tag-value TAG_VALUE] [--duration DURATION]

        Script to randomly stop instance in AZ filtered by tag

        optional arguments:
        -h, --help            show this help message and exit
        --log-level LOG_LEVEL Python log level. INFO, DEBUG, etc. (default: INFO)
        --region REGION       The AWS region of choice (default: eu-west-3)
        --az-name AZ_NAME     The name of the availability zone to blackout
                                (default: eu-west-3a)
        --tag-name TAG_NAME   The name of the tag (default: SSMTag)
        --tag-value TAG_VALUE The value of the tag (default: chaos-ready)
        --duration DURATION   Duration, in seconds, before restarting the instance
                                (default: None)
    ```

## Building and using for production

1. Build a [wheel][wheel].

   ```shell
   pip install wheel
   python setup.py bdist_wheel
   ```

1. Distribute the wheel file from the `dist` folder:

   ```shell
   dist/chaos_aws-1.0.0-py3-none-any.whl
   ```

1. Install the wheel with pip.

   ```shell
   pip install chaos_aws-1.0.0-py3-none-any.whl
   ```

1. Run the script with its console script:

   ```shell
   script-fail-az --region eu-west-3 --vpc-id vpc-2719dc4e --az-name eu-west-3a --duration 60 --failover-rds True --failover-elasticache True
   script-stop-instance --region eu-west-3 --az-name eu-west-3a --tag-name "chaos" --tag-value "chaos-ready"
   ```


## Building and using for dev or test

1. Install requirements

   ```shell
   pip install -r requirements.txt
   ```

1. Run the script with its console script:

   ```shell
   python scripts/fail_az.py --region eu-west-3 --vpc-id vpc-2719dc4e --az-name eu-west-3c --duration 60 --failover-rds True --failover-elasticache True
   python scripts/stop_random_instance.py --region eu-west-3 --az-name eu-west-3a --tag-name "chaos" --tag-value "chaos-ready"
   ```


[wheel]: http://pythonwheels.com