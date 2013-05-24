import os, sys
sys.path.append('/home/ecgovbr/www/opentrials')
sys.path.append('/home/ecgovbr/www')
os.environ['DJANGO_SETTINGS_MODULE'] = 'opentrials.settings'

import django.core.handlers.wsgi

application = django.core.handlers.wsgi.WSGIHandler()
