# coding: utf-8
import os
from django.conf import settings
from time import gmtime, strftime

def log_actions(user, action):
    '''
    Logs into a txt file every action performed

    '''
    log_folder = os.path.join(settings.PROJECT_PATH, 'logs')
    log_file = log_folder + '/logs_%s.txt' % strftime('%Y-%m-%d')
 #   log_file = log_folder + '/logs.txt'

    when = strftime('%Y-%m-%d %H:%M:%S')
    
    log_file = open(log_file, 'a+')
    msg_to_log = '%s - %s - %s\n' % (when, user, action)
    log_action = log_file.write(msg_to_log)
    log_file.close()
