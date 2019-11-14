"""
Script to simulate the lose of an AZ in an AWS Region
It is using Network ACL with deny all traffic
The script will Rollback to the originial state
And delete all created resources
Optional: it can also failover the masteRDS database.
"""
import argparse
import logging
import boto3
import time

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
        description='Script to associate subnet(s) with a Chaos NACL that deny ALL Ingress and Egress traffic - Simulation AZ failure',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--log-level', type=str, default='INFO',
                        help='Python log level. INFO, DEBUG, etc.')
    parser.add_argument('--region', type=str, default='eu-west-3',
                        help='The AWS region of choice')
    parser.add_argument('--vpc-id', type=str, default='vpc-2719dc4e',
                        help='The VPC ID of choice')
    parser.add_argument('--az-name', type=str, default='eu-west-3a',
                        help='The name of the availability zone to blackout')
    parser.add_argument('--duration', type=int, default=60,
                        help='The duration, in seconds, of the blackout')
    parser.add_argument('--failover-rds', type=bool, default=False,
                        help='Failover RDS master in the blackout subnet')
    return parser.parse_args()


def create_chaos_nacl(ec2_client, vpc_id):
    logger = logging.getLogger(__name__)
    logger.info('Create a Chaos Network ACL')
    # Create a Chaos Network ACL
    chaos_nacl = ec2_client.create_network_acl(
        VpcId=vpc_id,
    )
    associations = chaos_nacl['NetworkAcl']
    chaos_nacl_id = associations['NetworkAclId']

    # Tagging the network ACL with chaos for obvious reasons
    ec2_client.create_tags(
        Resources=[
            chaos_nacl_id,
        ],
        Tags=[
            {
                'Key': 'Name',
                'Value': 'chaos-kong'
            },
        ]
    )
    # Create Egress and Ingress rule blocking all inbound and outbound traffic
    # Egress
    ec2_client.create_network_acl_entry(
        CidrBlock='0.0.0.0/0',
        Egress=True,
        PortRange={'From': 0, 'To': 65535, },
        NetworkAclId=chaos_nacl_id,
        Protocol='-1',
        RuleAction='deny',
        RuleNumber=100,
    )

    # Ingress
    ec2_client.create_network_acl_entry(
        CidrBlock='0.0.0.0/0',
        Egress=False,
        PortRange={'From': 0, 'To': 65535, },
        NetworkAclId=chaos_nacl_id,
        Protocol='-1',
        RuleAction='deny',
        RuleNumber=101,
    )
    return chaos_nacl_id


def get_subnets_to_chaos(ec2_client, vpc_id, az_name):
    logger = logging.getLogger(__name__)
    logger.info('Getting the list of subnets to fail')
    # Describe the subnet so you can see if it is in the AZ
    subnets_response = ec2_client.describe_subnets(
        Filters=[
            {
                'Name': 'availability-zone',
                'Values': [az_name]
            },
            {
                'Name': 'vpc-id',
                'Values': [vpc_id]
            }
        ]
    )
    subnets_to_chaos = [
        subnet['SubnetId'] for subnet in subnets_response['Subnets']
    ]
    # Find network acl associations mapped to the subnets_to_chaos
    acls_response = ec2_client.describe_network_acls(
        Filters=[
            {
                    'Name': 'association.subnet-id',
                    'Values': subnets_to_chaos
            }
        ]
    )
    network_acls = acls_response['NetworkAcls']

    # SAVE THEM so it can revert
    nacl_ids = []

    for nacl in network_acls:
        for nacl_ass in nacl['Associations']:
            if nacl_ass['SubnetId'] in subnets_to_chaos:
                nacl_ass_id, nacl_id = nacl_ass['NetworkAclAssociationId'], nacl_ass['NetworkAclId']
                nacl_ids.append((nacl_ass_id, nacl_id))

    return nacl_ids


def apply_chaos_config(ec2_client, nacl_ids, chaos_nacl_id):
    logger = logging.getLogger(__name__)
    logger.info('save original config & apply new chaos config')
    save_for_rollback = []
    # Modify the association of the subnets_to_chaos with the Chaos NetworkACL
    for nacl_ass_id, nacl_id in nacl_ids:
        response = ec2_client.replace_network_acl_association(
            AssociationId=nacl_ass_id,
            NetworkAclId=chaos_nacl_id
        )
        save_for_rollback.append((response['NewAssociationId'], nacl_id))
    return save_for_rollback


def force_failover_rds(rds_client, vpc_id, az_name):
    logger = logging.getLogger(__name__)
    # Find RDS master instances within the AZ
    rds_dbs = rds_client.describe_db_instances()
    for rds_db in rds_dbs['DBInstances']:
        if rds_db['DBSubnetGroup']['VpcId'] == vpc_id:
            logger.info(
                'Database found in VPC: %s ', rds_db['DBInstanceIdentifier'])
            # if RDS master is multi-az and in blackholed AZ
            # force reboot with failover
            if rds_db['AvailabilityZone'] == az_name and rds_db['MultiAZ']:
                logger.info('Force reboot/failover')
                rds_client.reboot_db_instance(
                    DBInstanceIdentifier=rds_db['DBInstanceIdentifier'],
                    ForceFailover=True
                )


def rollback(ec2_client, save_for_rollback):
    logger = logging.getLogger(__name__)
    logger.info('Rolling back original configuration ')
    # Rollback the initial association
    for nacl_ass_id, nacl_id in save_for_rollback:
        ec2_client.replace_network_acl_association(
            AssociationId=nacl_ass_id,
            NetworkAclId=nacl_id
        )


def delete_chaos_nacl(ec2_client, chaos_nacl_id):
    logger = logging.getLogger(__name__)
    logger.info('Deleting the Chaos NACL')
    # delete the Chaos NACL
    ec2_client.delete_network_acl(
        NetworkAclId=chaos_nacl_id
    )


def confirm_choice():
    logger = logging.getLogger(__name__)
    confirm = input("!!WARNING!! [c]Confirm or [a]Abort Rebooting Database: ")
    if confirm != 'c' and confirm != 'a':
        print("\n Invalid Option. Please Enter a Valid Option.")
        return confirm_choice()
    logger.info('Selection: %s', confirm)
    return confirm


def run(region, az_name, vpc_id, duration, failover_rds, log_level='INFO'):
    setup_logging(log_level)
    logger = logging.getLogger(__name__)
    logger.info('Setting up ec2 client for region %s ', region)
    ec2_client = boto3.client('ec2', region_name=region)
    chaos_nacl_id = create_chaos_nacl(ec2_client, vpc_id)
    nacl_ids = get_subnets_to_chaos(ec2_client, vpc_id, az_name)
    save_for_rollback = apply_chaos_config(ec2_client, nacl_ids, chaos_nacl_id)

    if failover_rds:
        confirm = confirm_choice()
        if confirm == 'c':
            rds_client = boto3.client('rds', region_name=region)
            force_failover_rds(rds_client, vpc_id, az_name)
        else:
            pass

    time.sleep(duration)
    rollback(ec2_client, save_for_rollback)
    delete_chaos_nacl(ec2_client, chaos_nacl_id)


def entry_point():
    args = get_arguments()
    run(
        args.region,
        args.az_name,
        args.vpc_id,
        args.duration,
        args.failover_rds,
        args.log_level
    )
