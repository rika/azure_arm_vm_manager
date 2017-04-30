#!/usr/bin/env python
# coding: utf-8

import re, datetime
import azure.mgmt.compute
import azure.mgmt.network
import azure.mgmt.storage
from azure.mgmt.resource.resources.models import ResourceGroup
from azure.mgmt.resource.resources import ResourceManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.common.credentials import UserPassCredentials

import logging
logger = logging.getLogger('azure_resource_manager')
if not logger.handlers:
    # log to the console
    console = logging.StreamHandler()
    
    # default log level - make logger/console match
    logger.setLevel(logging.DEBUG)
    console.setLevel(logging.DEBUG)
    
    # formatter
    formatter = logging.Formatter("%(asctime)s %(levelname)7s:  %(message)s", "%Y-%m-%d %H:%M:%S")
    console.setFormatter(formatter)
    logger.addHandler(console)

class Instance():
    def __init__(self, name, has_public_ip):
        self.name = name
        base = name
        rgx = re.compile('[-.: ]')
        #base = name+'-'+ rgx.sub('', str(datetime.datetime.now()))[2:-4]
        
        self.network_interface_name = base
        self.public_ip_address_name = base
        self.computer_name = base
        self.vm_name = base
        self.os_disk_name = base+ rgx.sub('', str(datetime.datetime.now()))[2:-4]
        
        self.has_public_ip = has_public_ip
        

class AzureResourceManager():
    def __init__(self, azure_config, skip_setup=False):
        
        self.config = azure_config 
        
        subscription_id = azure_config.subscription_id
        username = azure_config.username
        password = azure_config.password
        group_name = azure_config.group_name
        storage_name = azure_config.storage_name
        virtual_network_name = azure_config.virtual_network_name
        subnet_name = azure_config.subnet_name
        region = azure_config.region

        self.vms = {}
            
        # 0. Authentication
        credentials = UserPassCredentials(username, password)

        self.resource_client = ResourceManagementClient(credentials, subscription_id)
        self.storage_client = StorageManagementClient(credentials, subscription_id)
        self.network_client = NetworkManagementClient(credentials, subscription_id)
        self.compute_client = ComputeManagementClient(credentials, subscription_id)
        
        if not skip_setup:
            # 1. Create a resource group
            result = self.resource_client.resource_groups.create_or_update(
                group_name,
                ResourceGroup(location=region),
            )
            
            # 2. Create a storage account
            result = self.storage_client.storage_accounts.create(
                group_name,
                storage_name,
                azure.mgmt.storage.models.StorageAccountCreateParameters(
                    location=region,
                    account_type=azure.mgmt.storage.models.AccountType.standard_lrs,
                ),
            )
            result.wait()
    
            # 3. Create a virtual network
            result = self.network_client.virtual_networks.create_or_update(
                group_name,
                virtual_network_name,
                azure.mgmt.network.models.VirtualNetwork(
                    location=region,
                    address_space=azure.mgmt.network.models.AddressSpace(
                        address_prefixes=[
                            '10.0.0.0/16',
                        ],
                    ),
                    subnets=[
                        azure.mgmt.network.models.Subnet(
                            name=subnet_name,
                            address_prefix='10.0.0.0/24',
                        ),
                    ],
                ),
            )
            result.wait()

    def create_vm(self, name, key_path, tags=[], has_public_ip=True):
        
        admin_username = self.config.admin_username
        vm_size = self.config.vm_size
        
        logger.debug('Preparing to create VM: %s' % name)
        instance = Instance(name, has_public_ip)
        self.vms[name] = instance
        
        network_interface_name = instance.network_interface_name
        public_ip_address_name = instance.public_ip_address_name
        computer_name = instance.computer_name
        vm_name = instance.vm_name
        os_disk_name = instance.os_disk_name
        
        
        group_name = self.config.group_name
        storage_name = self.config.storage_name
        virtual_network_name = self.config.virtual_network_name
        subnet_name = self.config.subnet_name 
        region = self.config.region
        
        network_client = self.network_client
        compute_client = self.compute_client
        
        key_data = open(key_path, 'r').read()
        
        inst_tags={}
        for t in tags:
            inst_tags[t] = t
        
        # 1. Get a new ip (if has a public ip)
        public_ip_address = None
        if has_public_ip:
            result = network_client.public_ip_addresses.create_or_update(
                group_name,
                public_ip_address_name,
                azure.mgmt.network.models.PublicIPAddress(
                    location=region,
                    public_ip_allocation_method=azure.mgmt.network.models.IPAllocationMethod.dynamic,
                    idle_timeout_in_minutes=4,
                ),
            )
            result.wait()
        
            result = network_client.public_ip_addresses.get(
                group_name,
                public_ip_address_name
            )
            public_ip_id = result.id
            public_ip_address=azure.mgmt.network.models.PublicIPAddress(
                id=public_ip_id,
            )
    
        # 2. Setup a ip configuration
        ipconfig = azure.mgmt.network.models.NetworkInterfaceIPConfiguration(
            name='default',
            private_ip_allocation_method=azure.mgmt.network.models.IPAllocationMethod.dynamic,
            subnet=network_client.subnets.get(
                group_name,
                virtual_network_name,
                subnet_name,
            ),
            public_ip_address=public_ip_address
        )
        
        parameters = azure.mgmt.network.models.NetworkInterface(
            location=region,
            #network_security_group=None, # colocar um grupo de segurança
            ip_configurations=[ipconfig],
        )

        # 3. Create a network interface
        result = network_client.network_interfaces.create_or_update(
            resource_group_name = group_name,
            network_interface_name = network_interface_name,
            parameters = parameters,
        )
        result.wait()
    
        network_interface = network_client.network_interfaces.get(
            group_name,
            network_interface_name,
        )
        nic_id = network_interface.id
       
        # 4. Create a virtual machine
        logger.debug('Creating VM: %s' % name)
        image = None
        image_reference = None
        base_os_disk_name = None
        os_type = None
        
        if self.config.template_image_vhd is None:
            base_os_disk_name = os_disk_name
            image_reference = azure.mgmt.compute.models.ImageReference(
                publisher=self.config.image_publisher,
                offer=self.config.image_offer,
                sku=self.config.image_sku,
                version=self.config.image_version,
            )
        else:
            os_type=azure.mgmt.compute.models.OperatingSystemTypes.linux
            base_os_disk_name = self.config.template_image_vhd
            image = azure.mgmt.compute.models.VirtualHardDisk(
                uri='https://{0}.blob.core.windows.net/system/Microsoft.Compute/Images/vhds/{1}'.format(
                    storage_name,
                    base_os_disk_name,
                ),
            )
        
        result = compute_client.virtual_machines.create_or_update(
            group_name,
            vm_name,
            azure.mgmt.compute.models.VirtualMachine(
                location=region,
                tags=inst_tags,
                os_profile=azure.mgmt.compute.models.OSProfile(
                    admin_username=admin_username,
                    #admin_password=admin_password,
                    computer_name=computer_name,
                    linux_configuration = azure.mgmt.compute.models.LinuxConfiguration(
                        disable_password_authentication = True,
                        ssh = azure.mgmt.compute.models.SshConfiguration(
                            public_keys=[
                                azure.mgmt.compute.models.SshPublicKey(
                                    path = "/home/{0}/.ssh/authorized_keys".format(admin_username),
                                    key_data = key_data
                                )
                            ]
                        )
                    ),
                ),
                hardware_profile=azure.mgmt.compute.models.HardwareProfile(
                    vm_size=vm_size
                ),
                network_profile=azure.mgmt.compute.models.NetworkProfile(
                    network_interfaces=[
                        azure.mgmt.compute.models.NetworkInterfaceReference(
                            id=nic_id,
                        ),
                    ],
                ),
                storage_profile=azure.mgmt.compute.models.StorageProfile(
                    os_disk=azure.mgmt.compute.models.OSDisk(
                        caching=azure.mgmt.compute.models.CachingTypes.none,
                        os_type=os_type,
                        create_option=azure.mgmt.compute.models.DiskCreateOptionTypes.from_image,
                        name=base_os_disk_name,
                        vhd=azure.mgmt.compute.models.VirtualHardDisk(
                            uri='https://{0}.blob.core.windows.net/vhds/{1}.vhd'.format(
                                storage_name,
                                os_disk_name,
                            ),
                        ),
                        image=image
                    ),
                    image_reference = image_reference,
                ),
            ),
        )
        result.wait()
        logger.debug('VM created: %s' % name)
        
    def delete_all_vms(self, match=None):
        group_name = self.config.group_name
        network_client = self.network_client
        compute_client = self.compute_client
        
        virtual_machines = compute_client.virtual_machines.list(group_name)
        network_security_groups = network_client.network_security_groups.list(group_name)
        network_interfaces = network_client.network_interfaces.list(group_name)
        public_ip_addresses = network_client.public_ip_addresses.list(group_name)
        
        print 'Match:',match
        
        results = []
        for x in virtual_machines:
            if not match or match in x.name:
                logger.debug('Deleting vm: %s' % x.name)
                results.append(compute_client.virtual_machines.delete(
                    group_name,
                    x.name
                ))

        for r in results:
            r.wait()

        results = []
        for x in network_security_groups:
            if not match or match in x.name:
                logger.debug('Deleting net sec: %s' % x.name)
                results.append(network_client.network_security_groups.delete(
                    group_name,
                    x.name
                ))
            
        for r in results:
            r.wait()
        
        results = []
        for x in network_interfaces:
            if not match or match in x.name:
                logger.debug('Deleting net int: %s' % x.name)
                results.append(network_client.network_interfaces.delete(
                    group_name,
                    x.name
                ))
        
        for r in results:
            r.wait()
        
        results = []
        for x in public_ip_addresses:
            if not match or match in x.name:
                logger.debug('Deleting pub ip: %s' % x.name)
                results.append(network_client.public_ip_addresses.delete(
                    group_name,
                    x.name
                ))

        for r in results:
            r.wait()
        
    def delete_vm(self, name):
        logger.debug('Deleting VM: %s' % name)
        group_name = self.config.group_name
        vm_name = self.vms[name].vm_name
        network_interface_name = self.vms[name].network_interface_name
        public_ip_address_name = self.vms[name].public_ip_address_name
        
        compute_client = self.compute_client
        network_client = self.network_client
        
        # 1. Delete the virtual machine
        result = compute_client.virtual_machines.delete(
            group_name,
            vm_name            
        )
        result.wait()
        # 2. Delete the network interface
        result = network_client.network_interfaces.delete(
            group_name,
            network_interface_name
        )
        result.wait()
        # 3. Delete the ip
        result = network_client.public_ip_addresses.delete(
            group_name,
            public_ip_address_name
        )
        result.wait()
        self.vms.pop(name)

    def get_pub_addr(self, name):
        if not self.vms[name].has_public_ip:
            return ''
        public_ip_address_name = self.vms[name].public_ip_address_name
        
        return self.network_client.public_ip_addresses.get(
            self.config.group_name,
            public_ip_address_name
        ).ip_address

    
    def get_priv_addr(self, name):
        network_interface_name = self.vms[name].network_interface_name
        
        return self.network_client.network_interfaces.get(
            self.config.group_name,
            network_interface_name,
        ).ip_configurations[0].private_ip_address
