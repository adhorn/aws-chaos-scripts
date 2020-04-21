"""
Script to force an RDS reboot with failover to another AZ.
Rebooting a DB instance restarts the database engine service.
Rebooting a DB instance results in a momentary outage,
during which the DB instance status is set to rebooting.

To perform the reboot with a failover, Amazon RDS instance
must be configured for Multi-AZ.

When you force a failover of your DB instance, Amazon RDS
automatically switches to a standby replica in another Availability
Zone, and updates the DNS record for the DB instance to point to the
standby DB instance. As a result, you need to clean up and re-establish
any existing connections to your DB instance.

Important: When you force a failover from one Availability Zone to another
when you reboot the Availability Zone change might not be reflected
in the AWS Management Console and in calls to the AWS CLI
and RDS API, for several minutes.
https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_RebootInstance.html
"""
import argparse
import logging
import boto3

from pythonjsonlogger import jsonlogger


def setup_logging(log_level):
    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)
    json_handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        fmt='%(asctime)s %(levelname)s %(name)s %(message)s'
    )
    json_handler.setFormatter(formatter)
    logger.addHandler(json_handler)


def get_arguments():
    parser = argparse.ArgumentParser(
        description='Force RDS failover if master is in a particular AZ or if database ID provided',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--region', type=str, required=True,
                        help='The AWS region of choice.')
    parser.add_argument('--rds-id', type=str, default=None,
                        help='The Id of the RDS database to failover.')
    parser.add_argument('--vpc-id', type=str, default=None,
                        help='The VPC ID of where the DB is.')
    parser.add_argument('--az-name', type=str, default=None,
                        help='The name of the AZ where the DB master is.')
    parser.add_argument('--log-level', type=str, default='INFO',
                        help='Python log level. INFO, DEBUG, etc.')
    parser.add_argument('--profile', type=str, default='default',
                        help='AWS credential profile to use')

    return parser.parse_args()


def confirm_choice():
    logger = logging.getLogger(__name__)
    confirm = input(
        "!!WARNING!! [c]Confirm or [a]Abort Failover: ")
    if confirm != 'c' and confirm != 'a':
        print("\n Invalid Option. Please Enter a Valid Option.")
        return confirm_choice()
    logger.info('Selection: %s', confirm)
    return confirm


def force_failover_rds(rds_client, vpc_id, az_name):
    logger = logging.getLogger(__name__)
    # Find RDS master instances within the AZ
    rds_dbs = rds_client.describe_db_instances()
    for rds_db in rds_dbs['DBInstances']:
        if rds_db['DBSubnetGroup']['VpcId'] == vpc_id:
            if rds_db['AvailabilityZone'] == az_name and rds_db['MultiAZ']:
                logger.info(
                    'Database %s found in VPC: %s and AZ: %s',
                    vpc_id,
                    rds_db['DBInstanceIdentifier'],
                    rds_db['AvailabilityZone']
                )
                # if RDS master is multi-az and in blackholed AZ
                # force reboot with failover
                confirm = confirm_choice()
                if confirm == 'c':
                    logger.info('Force reboot/failover')
                    rsp = rds_client.reboot_db_instance(
                        DBInstanceIdentifier=rds_db['DBInstanceIdentifier'],
                        ForceFailover=True
                    )
                    return {
                        'primary_az': rsp['DBInstance']['AvailabilityZone'],
                        'secondary_az': rsp['DBInstance']['SecondaryAvailabilityZone']
                    }
                else:
                    logger.info('Failover aborted')


def force_failover_rds_id(rds_client, rds_id):
    logger = logging.getLogger(__name__)
    # Find RDS master instances within the AZ
    rds_dbs = rds_client.describe_db_instances(
        DBInstanceIdentifier=rds_id,
    )
    for rds_db in rds_dbs['DBInstances']:
        if rds_db['MultiAZ']:
            logger.info(
                'MultiAZ enabled database found: %s', rds_id
            )
            # if RDS master is multi-az and in blackholed AZ
            # force reboot with failover
            confirm = confirm_choice()
            if confirm == 'c':
                logger.info('Force reboot/failover')
                rsp = rds_client.reboot_db_instance(
                    DBInstanceIdentifier=rds_db['DBInstanceIdentifier'],
                    ForceFailover=True
                )
                return {
                    'primary_az': rsp['DBInstance']['AvailabilityZone'],
                    'secondary_az': rsp['DBInstance']['SecondaryAvailabilityZone']
                }
            else:
                logger.info('Failover aborted')


def run(region, rds_id=None, az_name=None, vpc_id=None, log_level='INFO', profile='default'):
    setup_logging(log_level)
    logger = logging.getLogger(__name__)
    logger.info('Setting up rds client for region %s ', region)
    session = boto3.Session(profile_name=profile)
    rds_client = session.client('rds', region_name=region)
    if rds_id:
        response = force_failover_rds_id(rds_client, rds_id)
    else:
        response = force_failover_rds(rds_client, vpc_id, az_name)
    print(response)


def entry_point():
    args = get_arguments()
    print(args)
    run(
        args.region,
        args.rds_id,
        args.az_name,
        args.vpc_id,
        args.log_level,
        args.profile
    )


if __name__ == '__main__':
    entry_point()
