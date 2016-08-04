#!/usr/bin/env python
# coding: utf-8

import unittest
import threading
import os
import sys
import time
import traceback
import uuid

from azure_resource_manager import AzureResourceManager
from azure_config import AzureConfig



class TestAzure(unittest.TestCase):

    def setUp(self):
        home = os.path.expanduser("~")
        try:
            filepath = os.path.join(home, 'git', 'azure_config', 'config')
            self.config = AzureConfig(filepath)
        except Exception as e:
            print "ERROR: %s" % e
            traceback.print_exc(file=sys.stdout)
            
        self.arm = AzureResourceManager(self.config, skip_setup=True)
        
        self.key_path = os.path.join(home, '.ssh', 'id_rsa.pub') 
        
        
    def test_simple_provision(self):
        result = False
        arm = self.arm
        
        test_tag = 'simple-provision'
        name = test_tag + '-' + str(uuid.uuid4().get_hex())
        try:
            arm.create_vm(
                name,
                self.key_path,
                tags = [test_tag],
                has_public_ip = True
            )

            print 'priv_addr', arm.get_priv_addr(name)
            print 'pub_addr', arm.get_pub_addr(name)
            result = True
        except Exception as e:
            print "ERROR: %s" % e
            traceback.print_exc(file=sys.stdout)
        finally:
            arm.delete_vm(name)
        self.assertTrue(result)

    def test_conc_provision(self):
        n = 4
        result = False
        arm = self.arm
        
        test_tag = 'conc-provision'
        def create_vm(i):
            name = test_tag + '-' + str(i) + '-' + str(uuid.uuid4().get_hex())
            arm.create_vm(
                name,
                self.key_path,
                tags = [test_tag],
                has_public_ip = True
            )
        try:
            threads = []
            for i in range(n):
                threads.append(threading.Thread(target=create_vm,args=(i,),))
                threads[-1].start()
            for t in threads:
                t.join()
            for vm in arm.vms.values():
                print 'vm: %s' % vm.name
                print 'priv_addr', arm.get_priv_addr(vm.name)
                print 'pub_addr', arm.get_pub_addr(vm.name)
            result = True
        except Exception as e:
            print "ERROR: %s" % e
            traceback.print_exc(file=sys.stdout)
        finally:
            threads = []
            for vm in arm.vms.values():
                threads.append(threading.Thread(target=arm.delete_vm, args=(vm.name,),))
                threads[-1].start()
            for t in threads:
                t.join()
        self.assertTrue(result)

    def test_template_provision(self):
        result = False
        arm = self.arm
        
        test_tag = 'template-provision'
        name = test_tag + '-' + str(uuid.uuid4().get_hex())
        try:
            arm.create_vm(
                name,
                self.key_path,
                tags = [test_tag],
                has_public_ip = True
            )

            print 'priv_addr', arm.get_priv_addr(name)
            print 'pub_addr', arm.get_pub_addr(name)
            result = True
        except Exception as e:
            print "ERROR: %s" % e
            traceback.print_exc(file=sys.stdout)
        finally:
            arm.delete_vm(name)
        self.assertTrue(result)

if __name__ == '__main__':
    unittest.main()
