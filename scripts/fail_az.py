"""
Script to simulate the lose of an AZ in an AWS Region
It is using Network ACL with deny all traffic
The script will rollback to the original state
And delete all created resources
Optional: it can also failover the RDS database.
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
        description='Simulate AZ failure: associate subnet(s) with a Chaos NACL that deny ALL Ingress and Egress traffic - blackhole',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--region', type=str, required=True,
                        help='The AWS region of choice')
    parser.add_argument('--vpc-id', type=str, required=True,
                        help='The VPC ID of choice')
    parser.add_argument('--az-name', type=str, required=True,
                        help='The name of the availability zone to blackout')
    parser.add_argument('--duration', type=int,
                        help='The duration, in seconds, of the blackout')
    parser.add_argument('--limit-asg', type=bool, default=False,
                        help='Remove "failed" AZ from Auto Scaling Group (ASG)')
    parser.add_argument('--failover-rds', type=bool, default=False,
                        help='Failover RDS if master in the blackout subnet')
    parser.add_argument('--failover-elasticache', type=bool, default=False,
                        help='Failover Elasticache if primary in the blackout subnet')
    parser.add_argument('--log-level', type=str, default='INFO',
                        help='Python log level. INFO, DEBUG, etc.')
    parser.add_argument('--profile', type=str, default='default',
                        help='AWS credential profile to use')

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
                'Value': 'failover-testing-chaos-nacl'
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
    return subnets_to_chaos

def get_nacls_to_chaos(ec2_client, subnets_to_chaos):
    logger = logging.getLogger(__name__)
    logger.info('Getting the list of NACLs to blackhole')

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
                nacl_ass_id, nacl_id = nacl_ass[
                    'NetworkAclAssociationId'], nacl_ass['NetworkAclId']
                nacl_ids.append((nacl_ass_id, nacl_id))

    return nacl_ids

def limit_auto_scaling(autoscaling_client, subnets_to_chaos):
    logger = logging.getLogger(__name__)
    logger.info('Limit autoscaling to the remaining subnets')

    # Get info on all the AutoScalingGroups (ASGs) in the region
    response = autoscaling_client.describe_auto_scaling_groups()
    asgs = response['AutoScalingGroups']

    # Find the ASG we need to modify
    # (makes assumption that only one ASG should be impacted)
    correct_asg = False
    for asg in asgs:

        asg_name = asg['AutoScalingGroupName']
        asg_subnets = asg['VPCZoneIdentifier'].split(',')

        subnets_to_keep = list(set(asg_subnets)-set(subnets_to_chaos))

        # if the any of the subnets_to_chaos are in this ASG
        # then it is the ASG we will modify
        correct_asg = len(subnets_to_keep) < len(asg_subnets)
        if correct_asg: break

    # If we find an impacted ASG, we remove the subnets for the "failed AZ".  
    # In a real AZ failure ASG would not put new instances into this AZ
    if correct_asg:
        try:
            vpczoneidentifier = ",".join(subnets_to_keep)
            response = autoscaling_client.update_auto_scaling_group(AutoScalingGroupName=asg_name, VPCZoneIdentifier=vpczoneidentifier)
            return asg
        except:
            logger.error("Unable to update ASG:")
            logger.error("response: " + str(response))
            return None
    else:
        logger.error("Cannot find impacted ASG")
        return None

def apply_chaos_config(ec2_client, nacl_ids, chaos_nacl_id):
    logger = logging.getLogger(__name__)
    logger.info('Saving original config & applying new chaos config')
    save_for_rollback = []
    # Modify the association of the subnets_to_chaos with the Chaos NetworkACL
    for nacl_ass_id, nacl_id in nacl_ids:
        response = ec2_client.replace_network_acl_association(
            AssociationId=nacl_ass_id,
            NetworkAclId=chaos_nacl_id
        )
        save_for_rollback.append((response['NewAssociationId'], nacl_id))
    return save_for_rollback


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
                    'Database found in VPC: %s and AZ: %s', rds_db[
                        'DBInstanceIdentifier'], rds_db['AvailabilityZone']
                )
                # if RDS master is multi-az and in blackholed AZ
                # force reboot with failover
                confirm = confirm_choice()
                if confirm == 'c':
                    logger.info('Force reboot/failover')
                    rds_client.reboot_db_instance(
                        DBInstanceIdentifier=rds_db['DBInstanceIdentifier'],
                        ForceFailover=True
                    )
                else:
                    logger.info('Failover aborted')


def force_failover_elasticache(elasticache_client, az_name):
    logger = logging.getLogger(__name__)
    replication_groups = elasticache_client.describe_replication_groups()
    for replication in replication_groups['ReplicationGroups']:
        if replication['AutomaticFailover'] == 'enabled':
            # find if primary node in blackout AZ
            for nodes in replication['NodeGroups']:
                for node in nodes['NodeGroupMembers']:
                    if node['CurrentRole'] == 'primary' and node['PreferredAvailabilityZone'] == az_name:
                        print(node)
                        ReplicationGroupId = replication['ReplicationGroupId']
                        NodeGroupId = node['CacheNodeId']
                        logger.info(
                            'cluster with ReplicationGroupId %s and NodeGroupId %s found with primary node in %s',
                            ReplicationGroupId,
                            NodeGroupId,
                            node['PreferredAvailabilityZone']
                        )
                        confirm = confirm_choice()
                        if confirm == 'c':
                            logger.info('Force automatic failover; no rollback possible')
                            elasticache_client.test_failover(
                                ReplicationGroupId=ReplicationGroupId,
                                NodeGroupId=NodeGroupId
                            )
                        else:
                            logger.info('Failover aborted')


def rollback(ec2_client, save_for_rollback, autoscaling_client, original_asg):
    logger = logging.getLogger(__name__)
    logger.info('Rolling back Network ACL to original configuration')
    # Rollback the initial association
    for nacl_ass_id, nacl_id in save_for_rollback:
        ec2_client.replace_network_acl_association(
            AssociationId=nacl_ass_id,
            NetworkAclId=nacl_id
        )
    if original_asg is not None:
        logger.info('Rolling back AutoScalingGroup to original configuration')
        asg_name = original_asg['AutoScalingGroupName']
        asg_subnets = original_asg['VPCZoneIdentifier'].split(',')
        vpczoneidentifier = ",".join(asg_subnets)
        autoscaling_client.update_auto_scaling_group(AutoScalingGroupName=asg_name, VPCZoneIdentifier=vpczoneidentifier)


def delete_chaos_nacl(ec2_client, chaos_nacl_id):
    logger = logging.getLogger(__name__)
    logger.info('Deleting the Chaos NACL')
    # delete the Chaos NACL
    ec2_client.delete_network_acl(
        NetworkAclId=chaos_nacl_id
    )


def run(region, az_name, vpc_id, duration, limit_asg, failover_rds, failover_elasticache, log_level='INFO', profile='default'):
    setup_logging(log_level)
    logger = logging.getLogger(__name__)
    logger.info('Setting up ec2 client for region %s ', region)
    session = boto3.Session(profile_name=profile)
    ec2_client = session.client('ec2', region_name=region)
    autoscaling_client = session.client('autoscaling', region_name=region)
    chaos_nacl_id = create_chaos_nacl(ec2_client, vpc_id)
    subnets_to_chaos = get_subnets_to_chaos(ec2_client, vpc_id, az_name)
    nacl_ids = get_nacls_to_chaos(ec2_client, subnets_to_chaos)

    # Limit AutoScalingGroup to no longer include failed AZ
    if limit_asg:
        original_asg = limit_auto_scaling(autoscaling_client, subnets_to_chaos)
    else:
        original_asg = None

    # Blackhole networking to EC2 instances in failed AZ
    save_for_rollback = apply_chaos_config(ec2_client, nacl_ids, chaos_nacl_id)

    # Fail-over RDS if in the "failed" AZ
    if failover_rds:
        rds_client = session.client('rds', region_name=region)
        force_failover_rds(rds_client, vpc_id, az_name)

    # Fail-over Elasticache if in the "failed" AZ
    if failover_elasticache:
        elasticache_client = session.client('elasticache', region_name=region)
        force_failover_elasticache(elasticache_client, az_name)

    if duration:
        time.sleep(duration)
    else:
        input("Press Enter to rollback...")

    rollback(ec2_client, save_for_rollback,  autoscaling_client, original_asg)
    delete_chaos_nacl(ec2_client, chaos_nacl_id)


def entry_point():
    args = get_arguments()
    print(args)
    run(
        args.region,
        args.az_name,
        args.vpc_id,
        args.duration,
        args.limit_asg,
        args.failover_rds,
        args.failover_elasticache,
        args.log_level,
        args.profile
    )


if __name__ == '__main__':
    entry_point()
