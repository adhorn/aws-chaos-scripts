## About
Collection of python scripts to inject failure in the AWS Infrastructure

script-fail-az: simulate the lose of an Availability Zone (AZ) in a VPC.
script-kill-random: randomly kill instances in a particular AZ, VPC. 


## Building and using

1. Build a [wheel][wheel].

   ```shell
   pip install wheel
   python setup.py bdist_wheel
   ```

1. Distribute the wheel file from the `dist` folder:

   ```shell
   dist/fail_aws_az-1.0.0-py3-none-any.whl
   ```

1. Install the wheel with pip.

   ```shell
   pip install fail_aws_az-1.0.0-py3-none-any.whl
   ```

1. Run the script with its console script:

   ```shell
   script-fail-az --region eu-west-3 --vpc-id vpc-2719dc4e --az-name eu-west-3a --duration 60
   ```

[wheel]: http://pythonwheels.com