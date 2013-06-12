#!/usr/bin/env python
# -*- encoding: utf-8 -*-

# OpenTrials: a clinical trials registration system
#
# Copyright (C) 2010 BIREME/PAHO/WHO, ICICT/Fiocruz e
#                    Ministério da Saúde do Brasil
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 2.1 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

from django.http import HttpResponse
from django.core import serializers

ELLIPSIS = u'\u2026'

def safe_truncate(text, max_length=60, ellipsis=ELLIPSIS, encoding='utf-8',
                  raise_exc=False):
    u'''truncate a string without breaking words

        >>> safe_truncate(u'the time has come', 9, u'>')
        u'the time>'
        >>> safe_truncate(u'the-time-has-come', 9, u'>')
        u'the-time>'
        >>> safe_truncate(u'the time', 8)
        u'the time'
        >>> safe_truncate(u'the time', 9)
        u'the time'
        >>> s = u'uncharacteristically-long'
        >>> safe_truncate(s, 10, u'>')
        u'uncharacteristically>'
        >>> safe_truncate(s, 10, u'>', raise_exc=True)
        Traceback (most recent call last):
          ...
        ValueError: Cannot safely truncate to 10 characters
    '''
    if not isinstance(text, unicode):
        text = text.decode(encoding)
    if len(text) <= max_length:
        return text
    # reverse-seek a non-alphanumeric character
    for i, c in enumerate(reversed(text[:max_length])):
        if not c.isalnum():
            pos = max_length - i - 1
            break
    else:
        pos = -1
    if pos == -1:
        if raise_exc:
            msg = 'Cannot safely truncate to %s characters'
            raise ValueError(msg % max_length)
        else:
            # seek nearest non-alphanumeric character after the cuttoff point
            pos = len(text)
            for i, c in enumerate(text[max_length:]):
                if not c.isalnum():
                    pos = max_length + i
                    break
            if pos == len(text):
                return text

    return text[:pos] + ellipsis

def export_json(modeladmin, request, queryset):
    response = HttpResponse(mimetype="application/json")
    serializers.serialize("json", queryset, stream=response, indent=2)
    return response
export_json.short_description = 'Export selected records in JSON format'

def user_in_group(user, group):
    return user.groups.filter(name=group).count() != 0 if user else False

def normalize_age(age, unit):
    "convert age to hours"
    age_to_hour_multipliers = {'Y': 365*24,
                               'M': 30*24,
                               'W': 7*24,
                               'D': 24,
                               'H': 1,
                               }
    return age_to_hour_multipliers[unit] * age

def denormalize_age(hours, unit):
    "convert hours to age"
    hour_to_age_multipliers = {'Y': 365*24,
                               'M': 30*24,
                               'W': 7*24,
                               'D': 24,
                               'H': 1,
                               }
    return hours / hour_to_age_multipliers[unit]

from xml.dom.minidom import parseString

def getValuesFromXml(xmlSource, tag):
    file = open(xmlSource,'r')
    #convert to string:
    data = file.read()
    
    #close file because we dont need it anymore:
    file.close()
    
    #parse the xml you got from the file
    dom = parseString(data)
    
    #retrieve the first xml tag (<tag>data</tag>) that the parser finds with name tagName:
    xmlTag = dom.getElementsByTagName(tag)[0].toxml()
    
    #strip off the tag (<tag>data</tag>  --->   data) and (<tag/>) for empty tags:
    xmlData=xmlTag.replace('<%s>' % tag,'').replace('</%s>' % tag,'').replace('<%s/>' % tag,'')

    #just print the data
    return {'%s' % tag: xmlData.decode('utf-8')}

def geraDicPlataformaBrasil(filesource, lista_de_tags):
    dic = {}
    for tag in lista_de_tags:
            try:
                dic[tag] = getValuesFromXml(filesource, tag)[tag]
            except:
                print "erro"

    return dic

if __name__=='__main__':
    import doctest
    doctest.testmod()
