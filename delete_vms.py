import sys, os, ConfigParser
from azure_resource_manager import AzureResourceManager
from azure_config import AzureConfig

if len(sys.argv) < 2:
    print("Usage: %s [config_file]" % sys.argv[0])
    sys.exit()

config = AzureConfig(sys.argv[1])
    
arm = AzureResourceManager(
                           config.subscription_id,
                           config.username,
                           config.password,
                           config.group_name,
                           config.storage_name,
                           config.virtual_network_name,
                           config.subnet_name,
                           config.region,
                           skip_setup=True)
arm.delete_all_vms()