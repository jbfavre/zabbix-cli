#!/usr/bin/env python
#
# Authors:
# rafael@postgresql.org.es / http://www.postgresql.org.es/
#
# Copyright (c) 2014 USIT-University of Oslo
#
# This file is part of Zabbix-CLI
# https://github.com/rafaelma/zabbix-cli
#
# Zabbix-CLI is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Zabbix-CLI is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Zabbix-CLI.  If not, see <http://www.gnu.org/licenses/>.
#

import cmd
import sys
import os
import time
import signal
import shlex
import datetime
import subprocess
import ast
import ldap
import random
import hashlib

from zabbix_cli.config import *
from zabbix_cli.logs import *

from zabbix_cli.prettytable import *
import zabbix_cli.version

from zabbix_cli.pyzabbix import ZabbixAPI, ZabbixAPIException


# ############################################
# class zabbix_cli
# ############################################


class zabbix_cli(cmd.Cmd):
    '''
    This class implements the Zabbix shell. It is based on the python module cmd
    '''
  
    # ###############################
    # Constructor
    # ###############################

    def __init__(self,username,password,logs):
        cmd.Cmd.__init__(self)
        
        self.version = self.get_version()

        self.intro =  '\n#############################################################\n' + \
                      'Welcome to the Zabbix command-line interface (v.' + self.version + ')\n' + \
                      '#############################################################\n' + \
                      'Type help or \? to list commands.\n'
        
        self.prompt = '[zabbix-CLI]$ '
        self.file = None

        self.conf = configuration()
        self.logs = logs

        self.api_username = username
        self.api_password = password
        self.output_format = 'table'

        if self.conf.logging == 'ON':
            self.logs.logger.debug('Zabbix API url: %s',self.conf.zabbix_api_url)

        try:

            #
            # Connecting to the Zabbix JSON-API
            #

            self.zapi = ZabbixAPI(self.conf.zabbix_api_url)
            self.zapi.session.verify = False
            self.zapi.login(self.api_username,self.api_password)
        
            if self.conf.logging == 'ON':
                self.logs.logger.debug('Connected to Zabbix JSON-API')

        except Exception as e:        
            print '\n[ERROR]: ',e
            print
        
            if self.conf.logging == 'ON':
                self.logs.logger.error('Problems logging to %s',self.conf.zabbix_api_url)
            
            sys.exit(1)

    # ############################################  
    # Method show_hostgroups
    # ############################################  

    def do_show_hostgroups(self,args):
        '''
        DESCRIPTION: 
        This command shows all hostgroups defined in the system.

        COMMAND:
        show_hostgroups

        '''

        result_columns = {}
        result_columns_key = 0

        #
        # Get result from Zabbix API
        #
        try:
            result = self.zapi.hostgroup.get(output='extend',
                                             sortfield='name',
                                             sortorder='ASC')

            if self.conf.logging == 'ON':
                self.logs.logger.debug('Command show_hostgroups executed')

        except Exception as e: 
            print '\n[Error] Problems getting hostgroups information - ',e

            if self.conf.logging == 'ON':
                self.logs.logger.error('Problems getting hostgroups information - %s',e)

            return False   

        #
        # Get the columns we want to show from result 
        #
        for group in result:
            
            result_columns [result_columns_key] = [group['groupid'],
                                                   group['name'],
                                                   self.get_hostgroup_flag(int(group['flags'])),
                                                   self.get_hostgroup_type(int(group['internal']))]

            result_columns_key = result_columns_key + 1

        #
        # Generate output
        #
        self.generate_output(result_columns,
                             ['GroupID','Name','Flag','Type'],
                             ['Name'],
                             ['GroupID'],
                             FRAME)


    # ############################################                                                                                                                                    
    # Method show_hosts
    # ############################################

    def do_show_hosts(self,args):
        '''
        DESCRIPTION:
        This command shows all hosts defined in the system.

        COMMAND:
        show_hosts
        '''

        cmd.Cmd.onecmd(self,'show_host "*"')


    # ############################################                                                                                                                                    
    # Method show_host
    # ############################################
    
    def do_show_host(self,args):
        '''
        DESCRIPTION:
        This command shows hosts information

        COMMAND:
        show_host [HostID / Hostname]
                  [Filter]

        [HostID / Hostname]:
        -------------------
        One can search by HostID or by Hostname. We can use wildcards 
        if we search by Hostname
            
        [Filter]:
        --------
        * Zabbix agent: 'available': 0=Unknown  
                                     1=Available  
                                     2=Unavailable
        
        * Maintenance: 'maintenance_status': 0:No maintenance
                                             1:In progress
        
        * Status: 'status': 0:Monitored
                            1: Not monitored
        
        e.g.: Show all hosts with Zabbix agent: Available AND Status: Monitored:
              show_host * "'available':'1','status':'0'"
        
        '''

        result_columns = {}
        result_columns_key = 0

        try: 
            arg_list = shlex.split(args)
            
        except ValueError as e:
            print '\n[ERROR]: ',e,'\n'
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:
                print '--------------------------------------------------------'
                host = raw_input('# Host: ')
                filter = raw_input('# Filter: ')
                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------' 
                print '\n[Aborted] Command interrupted by the user.\n'
                return False   

        #
        # Command without filters attributes
        #

        elif len(arg_list) == 1:

            host = arg_list[0]
            filter = ''

        #
        # Command with filters attributes
        #
            
        elif len(arg_list) == 2:
            
            host = arg_list[0]
            filter = arg_list[1]

        #
        # Command with the wrong number of parameters
        #

        else:
            print '\n[ERROR] - Wrong number of parameters used.\n          Type help or \? to list commands\n'
            return False

        #
        # Check if we are searching by hostname or hostID
        #

        if host.isdigit():
            search_host = '\'hostids\':\'' + host + '\'' 
        else:
            search_host = '\'search\':{\'host\':\'' + host + '\'}' 
        
        #
        # Generate query
        #

        try:
            query=ast.literal_eval("{'output':'extend'," + search_host  + ",'selectParentTemplates':['templateid','name'],'selectGroups':['groupid','name'],'selectApplications':['name'],'sortfield':'host','sortorder':'ASC','searchWildcardsEnabled':'True','filter':{" + filter + "}}")
        
        except Exception as e:
            print '\n[ERROR]: Problems generating query - ',e
            print

            if self.conf.logging == 'ON':
                self.logs.logger.error('Problems generating query - %s',e)

            return False

        #
        # Get result from Zabbix API
        #

        try:
            result = self.zapi.host.get(**query)
        
            if self.conf.logging == 'ON':
                self.logs.logger.debug('Command show_host executed.')
            
        except Exception as e:
            print '\n[Error] Problems getting host information - ',e

            if self.conf.logging == 'ON':
                self.logs.logger.error('Problems getting host information - %s',e)

            return False   

        #
        # Get the columns we want to show from result 
        #

        for host in result:
        
            hostgroup_list = ''
            template_list = ''
            application_list = ''

            host['groups'].sort()
            host['parentTemplates'].sort()
            host['applications'].sort()
                        
            for hostgroup in host['groups']:

                if self.output_format == 'table':
                    hostgroup_list = hostgroup_list + '[' + hostgroup['groupid'] + '] ' + hostgroup['name'] + '\n'
                    
                elif self.output_format == 'csv':
                    hostgroup_list = hostgroup_list + '[' + hostgroup['groupid'] + '] ' + hostgroup['name'] + ','

            for template in host['parentTemplates']:
                
                if self.output_format == 'table':
                    template_list = template_list + '[' + template['templateid'] + '] ' + template['name'] + '\n'

                elif self.output_format == 'csv':
                    template_list = template_list + '[' + template['templateid'] + '] ' + template['name'] + ','
            
            for application in host['applications']:
                
                if self.output_format == 'table':
                    application_list = application_list + application['name'] + '\n'

                elif self.output_format == 'csv':
                    application_list = application_list + '[' + application['name'] + ','


            result_columns [result_columns_key] = [host['hostid'],
                                                   host['name'],
                                                   hostgroup_list[:-1],
                                                   template_list[:-1],
                                                   application_list[:-1],
                                                   self.get_zabbix_agent_status(int(host['available'])),
                                                   self.get_maintenance_status(int(host['maintenance_status'])),
                                                   self.get_monitoring_status(int(host['status']))]

            result_columns_key = result_columns_key + 1

        #
        # Generate output
        #
        self.generate_output(result_columns,
                             ['HostID','Name','Hostgroups','Templates','Applications','Zabbix agent','Maintenance','Status'],
                             ['Name','Hostgroups','Templates','Applications'],
                             ['HostID'],
                             ALL)


    # ############################################  
    # Method show_usergroups
    # ############################################  

    def do_show_usergroups(self,args):
        '''
        DESCRIPTION:
        This command shows user groups information.
        
        COMMAND:
        show_usergroups
        '''

        result_columns = {}
        result_columns_key = 0

        #
        # Get result from Zabbix API
        #
        try:
            result = self.zapi.usergroup.get(output='extend',
                                             sortfield='name',
                                             sortorder='ASC',
                                             selectUsers=['alias'])

            if self.conf.logging == 'ON':
                self.logs.logger.debug('Command show_usergroups executed')
                     
        except Exception as e:
            print '\n[Error] Problems getting usergroup information - ',e

            if self.conf.logging == 'ON':
                self.logs.logger.error('Problems getting usergroup information - %s',e)

            return False   
       
        #
        # Get the columns we want to show from result 
        #
        for group in result:

            result_columns [result_columns_key] =[group['usrgrpid'],
                                                  group['name'],
                                                  self.get_gui_access(int(group['gui_access'])),
                                                  self.get_usergroup_status(int(group['users_status']))]
            
            result_columns_key = result_columns_key + 1

        #
        # Generate output
        #
        self.generate_output(result_columns,
                             ['GroupID','Name','GUI access','Status'],
                             ['Name'],
                             ['GroupID'],
                             FRAME)


    # ############################################  
    # Method show_users
    # ############################################  

    def do_show_users(self,args):
        '''
        DESCRIPTION:
        This command shows users information.

        COMMAND:
        show_users
        '''

        result_columns = {}
        result_columns_key = 0

        #
        # Get result from Zabbix API
        #
        try:
            result = self.zapi.user.get(output='extend',
                                         getAccess=True,
                                         sortfield='alias',
                                         sortorder='ASC')

            if self.conf.logging == 'ON':
                self.logs.logger.debug('Command show_users executed')
                     
        except Exception as e:
            print '\n[Error] Problems getting users information - ',e

            if self.conf.logging == 'ON':
                self.logs.logger.error('Problems getting users information - %s',e)

            return False   
       
        #
        # Get the columns we want to show from result 
        #
        for user in result:

            result_columns [result_columns_key] =[user['userid'],
                                                  user['alias'],
                                                  user['name'] + ' ' + user['surname'],
                                                  self.get_autologin_type(int(user['autologin'])),
                                                  user['autologout'],
                                                  self.get_user_type(int(user['type']))]

                                                  
            
            result_columns_key = result_columns_key + 1

        #
        # Generate output
        #
        self.generate_output(result_columns,
                             ['UserID','Alias','Name','Autologin','Autologout','Type'],
                             ['Name','Type'],
                             ['UserID'],
                             FRAME)


    # ############################################  
    # Method show_alarms
    # ############################################  

    def do_show_alarms(self,args):
        '''
        DESCRIPTION:
        This command shows all active alarms.

        COMMAND:
        show_alarms
        '''

        result_columns = {}
        result_columns_key = 0

        #
        # Get result from Zabbix API
        #
        try:
            result = self.zapi.trigger.get(only_true=1,
                                           skipDependent=1,
                                           monitored=1,
                                           active=1,
                                           output='extend',
                                           expandDescription=1,
                                           expandData='host',
                                           sortfield='lastchange',
                                           sortorder='DESC')

            if self.conf.logging == 'ON':
                self.logs.logger.debug('Command show_alarms executed')

        except Exception as e:
            print '\n[Error] Problems getting alarm information - ',e

            if self.conf.logging == 'ON':
                self.logs.logger.error('Problems getting alarm information - %s',e)

            return False   

        #
        # Get the columns we want to show from result 
        #
        for trigger in result:

            lastchange = datetime.datetime.fromtimestamp(int(trigger['lastchange']))
            age = datetime.datetime.now() - lastchange

            result_columns [result_columns_key] = [trigger['triggerid'],
                                                   trigger['hostname'],
                                                   trigger['description'],
                                                   self.get_trigger_severity(int(trigger['priority'])),
                                                   str(lastchange),
                                                   str(age)]
            
            result_columns_key = result_columns_key + 1

        #
        # Generate output
        #
        self.generate_output(result_columns,
                             ['TriggerID','Host','Description','Severity','Last change', 'Age'],
                             ['Host','Description','Last change','Age'],
                             ['TriggerID'],
                             FRAME)


    # ############################################
    # Method do_create_usergroup
    # ############################################

    def do_create_usergroup(self,args):
        '''
        DESCRIPTION:
        This command creates an usergroup.

        COMMAND:
        create_usergroup [group name]
                         [GUI access]
                         [Status]

        [group name]
        ------------
        Usergroup name

        [GUI access]
        ------------
        0:'System default' [*]
        1:'Internal'
        2:'Disable'        

        [Status]
        --------
        0:'Enable' [*]
        1:'Disable'

        '''
        
        # Default 0: System default
        gui_access_default = '0'
        
        # Default 0: Enable
        users_status_default = '0'

        try: 
            arg_list = shlex.split(args)
            
        except ValueError as e:
            print '\n[ERROR]: ',e,'\n'
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:
                print '--------------------------------------------------------'
                groupname = raw_input('# Name: ')
                gui_access = raw_input('# GUI access ['+ gui_access_default + ']: ')
                users_status = raw_input('# Status ['+ users_status_default + ']: ')
                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------' 
                print '\n[Aborted] Command interrupted by the user.\n'
                return False   

        #
        # Command without filters attributes
        #

        elif len(arg_list) == 3:

            groupname = arg_list[0]
            gui_access = arg_list[1]
            users_status = arg_list[2]

        #
        # Command with the wrong number of parameters
        #

        else:
            print '\n[ERROR] - Wrong number of parameters used.\n          Type help or \? to list commands\n'
            return False


        #
        # Sanity check
        #

        if gui_access == '' or gui_access not in ('0','1','2'):
            gui_access = gui_access_default

        if users_status == '' or users_status not in ('0','1'):
            users_status = users_status_default

        #
        # Check if usergroup exists
        #

        try:
            
            result = self.zapi.usergroup.exists(name=groupname)

            if self.conf.logging == 'ON':
                self.logs.logger.debug('Cheking if usergroup (%s) exists',groupname)

        except Exception as e:
            print '\n[ERROR] Problems checking if usergroup (' + groupname + ') exists \n',e
         
            if self.conf.logging == 'ON':
                self.logs.logger.error('Problems checking if usergroup (%s) exists',groupname)

            return False   
        
        #
        # Create usergroup if it does not exist
        #

        try:

            if result == True:
                print '\n[Warning] This usergroup (' + groupname + ') already exists.\n'

                if self.conf.logging == 'ON':
                    self.logs.logger.debug('Usergroup (%s) already exists',groupname)
                
                return False   
                
            elif result == False:
                result = self.zapi.usergroup.create(name=groupname,
                                                    gui_access=gui_access,
                                                    users_status=users_status)
                
                print '\n[Done]: Usergroup (' + groupname + ') with ID: ' + str(result['usrgrpids'][0]) + ' created.\n'
        
                if self.conf.logging == 'ON':
                    self.logs.logger.debug('Usergroup (%s) with ID: %s created',groupname,str(result['usrgrpids'][0]))

        except Exception as e:
            print '\n[Error] Problems creating usergroup (' + groupname + ')\n',e

            if self.conf.logging == 'ON':
                    self.logs.logger.error('Problems creating Usergroup (%s)',groupname)

            return False   
            


    # ############################################
    # Method do_create_user
    # ############################################

    def do_create_user(self,args):
        '''
        DESCRIPTION:
        This command creates an user.

        COMMAND:
        create_user [alias]
                    [name]
                    [surname]
                    [passwd]
                    [type]
                    [autologin]
                    [autologout]
                    [groups]
                    
        [alias]
        -------
        User alias (account name)
            
        [name]
        ------
        Name

        [surname]
        ---------
        Surname

        [passwd]
        --------
        Password. 

        The system will generate an automatic password if this value
        is not defined.

        [type]
        ------
        1:'User' [*]
        2:'Admin'
        3:'Super admin'
        
        [autologin]
        -----------
        0:'Disable' [*]
        1:'Enable'        
        
        [autologout]
        ------------
        In seconds [86400]

        [groups]
        --------   
        User groups ID

        '''
        
        # Default: md5 value of a random int >1 and <1000000 
        x = hashlib.md5()
        x.update(str(random.randint(1,1000000)))
        passwd_default = x.hexdigest()
        
        # Default: 1: Zabbix user
        type_default = '1'

        # Default: 0: Disable
        autologin_default = '0'

        # Default: 1 day: 86400s
        autologout_default = '86400'

        try: 
            arg_list = shlex.split(args)
            
        except ValueError as e:
            print '\n[ERROR]: ',e,'\n'
            return False

        #
        # Command without parameters
        #

        if len(arg_list) == 0:

            try:
                print '--------------------------------------------------------'
                alias = raw_input('# Alias []: ')
                name = raw_input('# Name []: ')
                surname = raw_input('# Surname []: ')
                passwd = raw_input('# Password []: ')
                type = raw_input('# User type [' + type_default + ']: ')
                autologin = raw_input('# Autologin [' + autologin_default + ']: ')
                autologout = raw_input('# Autologout [' + autologout_default + ']: ')
                usrgrps = raw_input('# Usergroups []: ')
                print '--------------------------------------------------------'

            except Exception as e:
                print '\n--------------------------------------------------------' 
                print '\n[Aborted] Command interrupted by the user.\n'
                return False   

        #
        # Command with parameters
        #

        elif len(arg_list) == 8:

            alias = arg_list[0]
            name = arg_list[1]
            surname = arg_list[2]
            passwd = arg_list[3]
            type = arg_list[4]
            autologin = arg_list[5]
            autologout = arg_list[6]
            usrgrps = arg_list[7]

        #
        # Command with the wrong number of parameters
        #

        else:
            print '\n[Error] - Wrong number of parameters used.\n          Type help or \? to list commands\n'
            return False

        #
        # Sanity check
        #

        if alias == '':
            print '\n[Error]: User Alias is empty\n'
            return False

        if passwd == '':
            passwd = passwd_default

        if type == '' or type not in ('1','2','3'):
            type = type_default

        if autologin == '':
            autologin = autologin_default

        if autologout == '':
            autologout = autologout_default
        
        if usrgrps == '':
            print '\n[Error]: Group list is empty\n'
            return False

        #
        # Check if user exists
        #

        try:
            
            result = self.zapi.user.get(search={'alias':alias},output='extend',searchWildcardsEnabled=True)

            if self.conf.logging == 'ON':
                    self.logs.logger.debug('Checking if user (%s) exists',alias)

        except Exception as e:
            print '\n[ERROR] Problems checking if user (' + alias + ') exists \n',e

            if self.conf.logging == 'ON':
                    self.logs.logger.error('Problems checking if user (%s) exists',alias)

            return False   

        #
        # Create user
        #

        try:

            if result != []:

                print '\n[Warning] This user (' + alias + ') already exists.\n'

                if self.conf.logging == 'ON':
                    self.logs.logger.debug('This user (%s) already exists',alias)

                return False   
                
            else:
                result = self.zapi.user.create(alias=alias,
                                               name=name,
                                               surname=surname,
                                               passwd=passwd,
                                               type=type,
                                               autologin=autologin,
                                               autologout=autologout,
                                               usrgrps=usrgrps.strip().split(','))
                
                print '\n[Done]: User (' + alias + ') with ID: ' + str(result['userids'][0]) + ' created.\n'

                if self.conf.logging == 'ON':
                    self.logs.logger.debug('User (%s) with ID: %s created',alias,str(result['userids'][0]))

        except Exception as e:
            print '\n[Error] Problems creating user (' + alias + '\n',e

            if self.conf.logging == 'ON':
                self.logs.logger.error('Problems creating user (%s)',alias)

            return False   
            

        
    # ############################################
    # Method get_trigger_severity
    # ############################################
    
    def get_trigger_severity(self,code):
        '''
        Get trigger severity from code
        '''

        trigger_severity = {0:'Not classified',1:'Information',2:'Warning',3:'Average',4:'High',5:'Disaster'}

        if code in trigger_severity:
            return trigger_severity[code] + " (" + str(code) +")"

        else:
            return 'Unknown' + " (" + str(code) +")"


    # ############################################
    # Method get_maintenance_status
    # ############################################
    
    def get_maintenance_status(self,code):
        '''
        Get maintenance status from code
        '''

        maintenance_status = {0:'No maintenance',1:'In progress'}

        if code in maintenance_status:
            return maintenance_status[code]  + " (" + str(code) +")"

        else:
            return 'Unknown' + " (" + str(code) +")"

    
    # ############################################
    # Method get_monitoring_status
    # ############################################
    
    def get_monitoring_status(self,code):
        '''
        Get monitoring status from code
        '''

        monitoring_status = {0:'Monitored',1:'Not monitored'}

        if code in monitoring_status:
            return monitoring_status[code] + " (" + str(code) +")"

        else:
            return 'Unknown' + " (" + str(code) +")"


    # ############################################
    # Method get_monitoring_status
    # ############################################
    
    def get_zabbix_agent_status(self,code):
        '''
        Get zabbix agent status from code
        '''

        zabbix_agent_status = {1:'Available',2:'Unavailable'}

        if code in zabbix_agent_status:
            return zabbix_agent_status[code] + " (" + str(code) +")"

        else:
            return 'Unknown' + " (" + str(code) +")"


    # ############################################
    # Method get_gui_access
    # ############################################
    
    def get_gui_access(self,code):
        '''
        Get GUI access from code
        '''

        gui_access = {0:'System default',1:'Internal',2:'Disable'}

        if code in gui_access:
            return gui_access[code] + " (" + str(code) +")"

        else:
            return 'Unknown' + " (" + str(code) +")"

    # ############################################
    # Method get_usergroup_status
    # ############################################
    
    def get_usergroup_status(self,code):
        '''
        Get usergroup status from code
        '''

        usergroup_status = {0:'Enable',1:'Disable'}

        if code in usergroup_status:
            return usergroup_status[code] + " (" + str(code) +")"

        else:
            return 'Unknown' + " (" + str(code) +")"


    # ############################################
    # Method get_hostgroup_flag
    # ############################################
    
    def get_hostgroup_flag(self,code):
        '''
        Get hostgroup flag from code
        '''

        hostgroup_flag = {0:'Plain',4:'Discover'}

        if code in hostgroup_flag:
            return hostgroup_flag[code] + " (" + str(code) +")"

        else:
            return 'Unknown' + " (" + str(code) +")"


    # ############################################
    # Method get_hostgroup_type
    # ############################################
    
    def get_hostgroup_type(self,code):
        '''
        Get hostgroup type from code
        '''

        hostgroup_type = {0:'Not internal',1:'Internal'}

        if code in hostgroup_type:
            return hostgroup_type[code] + " (" + str(code) +")"

        else:
            return 'Unknown' + " (" + str(code) +")"


    # ############################################
    # Method get_user_type
    # ############################################
    
    def get_user_type(self,code):
        '''
        Get user type from code
        '''

        user_type = {1:'User',2:'Admin',3:'Super admin'}

        if code in user_type:
            return user_type[code] + " (" + str(code) +")"

        else:
            return 'Unknown' + " (" + str(code) +")"


    # ############################################
    # Method get_autologin_type
    # ############################################
    
    def get_autologin_type(self,code):
        '''
        Get autologin type from code
        '''

        autologin_type = {0:'Disable',1:'Enable'}

        if code in autologin_type:
            return autologin_type[code] + " (" + str(code) +")"

        else:
            return 'Unknown' + " (" + str(code) +")"


    # ############################################
    # Method generate_output
    # ############################################

    def generate_output(self,result,colnames,left_col,right_col,hrules):
        '''
        Generate the result output
        '''

        try:
        
            if self.output_format == 'table':
            
                x = PrettyTable(colnames)
                x.header = True
                x.padding_width = 1
                x.hrules = hrules
            
                for column in left_col:
                    x.align[column] = "l"
        
                for column in right_col:
                    x.align[column] = "r"

                for records in result:
                    x.add_row(result[records])
            
                print x.get_string()
                print

            elif self.output_format == 'csv':
            
                for records in result:
                    print '"' +  '","'.join(result[records]) + '"'
             
        except Exception as e: 
            print '\n[Error] Problems generating the output ',e

            if self.conf.logging == 'ON':
                self.logs.logger.error('Problems generating the output')


    # ############################################
    # Method do_clear
    # ############################################

    def do_clear(self,args):
        '''
        DESCRIPTION: 
        Clears the screen and shows the welcome banner.

        COMMAND: 
        clear
        
        '''
        
        os.system('clear')
        print self.intro


    # ############################################
    # Method default
    # ############################################

    def default(self,line):
        print '\n[ERROR] - Unknown command: %s.\n          Type help or \? to list commands\n' % line


    # ############################################
    # Method emptyline
    # ############################################

    def emptyline(self):
        pass


    # ############################################
    # Method precmd
    # ############################################

    def precmd(self, line_in):

        if line_in != '':
            split_line = line_in.split()
            
            if split_line[0] not in ['EOF','shell','SHELL','\!']:
                line_out = line_in.lower()
            else:
                line_out = line_in

            if split_line[0] == '\h':
                line_out = line_out.replace('\h','help')
            elif split_line[0] == '\?':
                line_out = line_out.replace('\?','help')
            elif split_line[0] == '\!':
                line_out = line_out.replace('\!','shell')
            elif line_out == '\s':
                line_out = 'show_history'    
            elif line_out == '\q':
                line_out = 'quit' 
                
            self._hist += [ line_out.strip() ]
          
        else:
            line_out = ''
       
        return cmd.Cmd.precmd(self, line_out)


    # ############################################
    # Method do_shell
    # ############################################

    def do_shell(self, line):
        '''
        DESCRIPTION:
        This command runs a command in the operative system
        
        COMMAND:
        shell [command]

        [command]:
        ----------
        Any command that can be run in the operative system.
        
        '''

        try:
            proc = subprocess.Popen([line],stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True)
            output, errors = proc.communicate()
            print output,errors
            print

        except Exception as e:
            print '\n[ERROR]: Problems running %s' % line


    # ############################################
    # Method do_quit
    # ############################################

    def do_quit(self, args):
        '''
        DESCRIPTION: 
        Quits/terminate the Zabbix-CLI shell.

        COMMAND: 
        quit
        
        '''
        
        print '\nDone, thank you for using Zabbix-CLI'
        return True


    # ############################################
    # Method do_EOF
    # ############################################

    def do_EOF(self, line):
        '''
        DESCRIPTION: 
        Quit/terminate the Zabbix-CLI shell.

        COMMAND: 
        EOF
        
        '''

        print
        print '\nDone, thank you for using Zabbix-CLI'
        return True


    # ############################################
    # Method do_hist
    # ############################################

    def do_show_history(self, args):
        '''
        DESCRIPTION: 
        This command shows the list of commands that have been entered
        during the Zabbix-CLI shell session.

        COMMAND: 
        show_history

        '''

        cnt = 0
        print

        for line in self._hist:
            print '[' + str(cnt) + ']: ' + line
            cnt = cnt +1

        print


    # ########################################################
    # Method get_hostgroupid
    # ########################################################

    def get_hostgroup_id(self, hostgroup):
        '''
        DESCRIPTION:
        Get the hostgroup_id for a hostgroup
        '''

        try:
            data = self.zapi.hostgroup.get(output='extend', filter={"name":hostgroup})
            if not data:
                hostgroupid = 0
            else:
                hostgroupid = data[0]['groupid']

        except Exception as e:
            raise e

        return hostgroupid


    # #################################################
    # Method get_host_id
    # #################################################
    
    def get_host_id(self, host):
        '''
        DESCRIPTION:
        Get the hostid for a host
        '''
        
        try:
            data = self.zapi.host.get(output='extend', filter={"host":host})
            if not data:
                hostid = 0
            else:
                hostid = data[0]['hostid']
            
        except Exception as e:
            raise e

        return hostid
    

    # ###############################################
    # Method get_template_id
    # ###############################################
    
    def get_template_id(self, template):
        '''
        DESCRIPTION:
        Get the templateid for a template
        '''

        try:
            data = self.zapi.template.get(output='extend', filter={"host":template})
            if not data:
                templateid = 0
            else:
                templateid = data[0]['templateid']

        except Exception as e:
            raise e

        return templateid


    # ##########################################
    # Method get_usergroup_id
    # ##########################################
    
    def get_usergroup_id(self, usergroup):
        '''
        DESCRIPTION:
        Get the usergroupid for a usergroup
        '''

        try:
            data = self.zapi.usergroup.get(output='extend', filter={"name":usergroup})
            if not data:
                usergroupid = 0
            else:
                usergroupid = data[0]['usrgrpid']

        except Exception as e:
            raise e

        return usergroupid
    

    # ############################################
    # Method preloop
    # ############################################

    def preloop(self):
        '''
        Initialization before prompting user for commands.
        '''
        
        cmd.Cmd.preloop(self)   ## sets up command completion
        self._hist    = []      ## No history yet
        self._locals  = {}      ## Initialize execution namespace for user
        self._globals = {}


    # ############################################
    # Method help_shortcuts
    # ############################################

    def help_shortcuts(self):
        '''
        Help information about shortcuts in Zabbix-CLI
        '''
        
        print '''
        Shortcuts in Zabbix-CLI:

        \h [COMMAND] - Help on syntax of Zabbix-CLI commands
        \? [COMMAND] - Help on syntax of Zabbix-CLI commands
        
        \s - display history 
        \q - quit Zabbix-CLI shell

        \! [COMMAND] - Execute command in shell
          
        '''


    # ############################################
    # Method help_shortcuts
    # ############################################

    def help_support(self):
        '''
        Help information about Zabbix-CLI support
        '''
        
        print '''
        The latest information and versions of Zabbix-CLI can be obtained 
        from: http://
          
        '''


    # ############################################
    # Method handler
    # ############################################

    def signal_handler_sigint(self,signum, frame):
        cmd.Cmd.onecmd(self,'quit')
        sys.exit(0)


    # ############################################
    # Method get_version
    # ############################################

    def get_version(self):
        '''
        Get Zabbix-CLI version
        '''
        
        try:
            return zabbix_cli.version.__version__

        except Exception as e:
            return 'Unknown'


if __name__ == '__main__':

    signal.signal(signal.SIGINT, zabbix_cli().signal_handler_sigint)
    signal.signal(signal.SIGTERM,zabbix_cli().signal_handler_sigint)
    zabbix_cli().cmdloop()

