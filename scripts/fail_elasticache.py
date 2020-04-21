"""
Script to force an ElastiCache failover to another AZ.

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
        description='Force ElastiCache failover if master is in a particular AZ or if master node ID provided',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--region', type=str, required=True,
                        help='The AWS region of choice.')
    parser.add_argument('--elasticache-cluster-name', type=str, default=None,
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


def force_failover_elasticache_az(elasticache_client, az_name):
    logger = logging.getLogger(__name__)
    replication_groups = elasticache_client.describe_replication_groups()
    for replication in replication_groups['ReplicationGroups']:
        if replication['AutomaticFailover'] == 'enabled':
            # find if primary node in blackout AZ
            for nodes in replication['NodeGroups']:
                for node in nodes['NodeGroupMembers']:
                    if node['CurrentRole'] == 'primary' and node['PreferredAvailabilityZone'] == az_name:
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
                            try:
                                elasticache_client.test_failover(
                                    ReplicationGroupId=ReplicationGroupId,
                                    NodeGroupId=NodeGroupId
                                )
                                return
                            except (Exception) as e:
                                logger.error(e)
                        else:
                            logger.info('Failover aborted')

                    elif node['CurrentRole'] == 'primary' and node['PreferredAvailabilityZone'] != az_name:
                        logger.info('Primary node %s found but not in %s', node['CacheClusterId'], az_name)

                    else:
                        logger.info(
                            'Node %s found but not primary', node['CacheClusterId'])


def force_failover_elasticache(
        elasticache_client, elasticache_cluster_name):
    logger = logging.getLogger(__name__)
    replication_groups = elasticache_client.describe_replication_groups(
        ReplicationGroupId=elasticache_cluster_name
    )
    for replication in replication_groups['ReplicationGroups']:
        if replication['AutomaticFailover'] == 'enabled':
            # find primary node
            for nodes in replication['NodeGroups']:
                for node in nodes['NodeGroupMembers']:
                    if node['CurrentRole'] == 'primary':
                        NodeGroupId = node['CacheNodeId']
                        logger.info(
                            'cluster with ReplicationGroupId %s and NodeGroupId %s found with primary node in %s',
                            elasticache_cluster_name,
                            NodeGroupId,
                            node['PreferredAvailabilityZone']
                        )
                        confirm = confirm_choice()
                        if confirm == 'c':
                            logger.info('Force automatic failover; no rollback possible')
                            try:
                                elasticache_client.test_failover(
                                    ReplicationGroupId=elasticache_cluster_name,
                                    NodeGroupId=NodeGroupId
                                )
                                return
                            except (Exception) as e:
                                logger.error(e)
                        else:
                            logger.info('Failover aborted')


def run(region, elasticache_cluster_name=None, az_name=None, vpc_id=None, log_level='INFO', profile='default'):
    setup_logging(log_level)
    logger = logging.getLogger(__name__)
    logger.info('Setting up elasticache client for region %s ', region)
    session = boto3.Session(profile_name=profile)
    elasticache_client = session.client('elasticache', region_name=region)
    if elasticache_cluster_name:
        force_failover_elasticache(
            elasticache_client, elasticache_cluster_name)
    else:
        force_failover_elasticache_az(elasticache_client, az_name)
    logger.info('done')


def entry_point():
    args = get_arguments()
    run(
        args.region,
        args.elasticache_cluster_name,
        args.az_name,
        args.vpc_id,
        args.log_level,
        args.profile
    )


if __name__ == '__main__':
    entry_point()
