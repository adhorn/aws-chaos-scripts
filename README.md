## Disclaimer

⚠️USE AT YOUR OWN RISK⚠️

Using these scripts may create an unreasonable risk. If you choose to use the scripts provided here in your own activities, you do so at your own risk.
None of the authors or contributors, or anyone else connected with these scripts, in any way whatsoever, can be responsible for your use of the scripts contained in this repository. 
Use these scripts only if you understand what the code does



## About
Collection of python scripts to inject failure in the AWS Infrastructure

    script-fail-az: simulate the lose of an Availability Zone (AZ) in a VPC.
    script-stop-instance: randomly kill an instance in a particular AZ if proper tags. 

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
   script-fail-az --region eu-west-3 --vpc-id vpc-2719dc4e --az-name eu-west-3a --duration 60 --failover-rds True
   script-stop-instance --region eu-west-3 --az-name eu-west-3a --tag-name "chaos" --tag-value "chaos-ready"
   ```


## Building and using for dev or test

1. Install requirements

   ```shell
   pip install -r requirements.txt
   ```

1. Run the script with its console script:

   ```shell
   python scripts/fail_az.py --region eu-west-3 --vpc-id vpc-2719dc4e --az-name eu-west-3c --duration 60
   python scripts/stop_random_instance.py --region eu-west-3 --az-name eu-west-3a --tag-name "chaos" --tag-value "chaos-ready"
   ```


[wheel]: http://pythonwheels.com