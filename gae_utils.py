#    Readable Feeds
#    Copyright (C) 2009  Andrew Trusty (http://andrewtrusty.com)
#    
#    This file is part of Readable Feeds.
#
#    Readable Feeds is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Readable Feeds is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Readable Feeds.  If not, see <http://www.gnu.org/licenses/>.

import os
import logging
import re
from datetime import datetime, timedelta
from cStringIO import StringIO

import wsgiref.handlers
from google.appengine.ext import webapp
from google.appengine.api import mail

import jinja2
from jinja2 import Environment, FileSystemLoader

# webpy
from web import utils
from web import urlquote

from appengine_utilities.sessions import Session

DEV = False
if 'DEV' in os.listdir('.'):
    DEV = True

ENV = Environment(loader=FileSystemLoader('templates/'), autoescape=True,
                  auto_reload=DEV, line_statement_prefix='#')

def cond(c, str, other=''):
  if c:
    return str
  return other
ENV.globals['cond'] = cond

ENV.globals['urlquote'] = urlquote


def number_format(num, places=0):
   """Format a number with grouped thousands and given decimal places"""

   # in utils, commify(n) adds commas to an int

   places = max(0,places)
   tmp = "%.*f" % (places, num)
   point = tmp.find(".")
   integer = (point == -1) and tmp or tmp[:point]
   decimal = (point != -1) and tmp[point:] or ""

   count = 0
   formatted = []
   for i in range(len(integer), 0, -1):
       count += 1
       formatted.append(integer[i - 1])
       if count % 3 == 0 and i - 1:
           formatted.append(",")

   integer = "".join(formatted[::-1])
   return integer+decimal
ENV.filters['number_format'] = number_format


def simple_name(name, sep='-'):
    """
    Create nice names to put in urls like stackoverflow.com but with endings
    cut off at the word level rather than the character level.
    """
    name = re.sub('[ \.\-]+', '-', re.sub(r'[^\w\-\. ]+', '', name)).lower()
    if len(name) > 80:
        name = name[:81]
        name = name[:name.rfind('-')]
    return name.strip('-')
ENV.globals['simple_name'] = simple_name


def valid_email(email):
    if len(email) <= 5: # a@b.ca
        return False
    
    if not re.match("^.+\\@(\\[?)[a-zA-Z0-9\\-\\.]+\\.([a-zA-Z]{2,3}|[0-9]{1,3})(\\]?)$", email):
        return False
    
    return True


class RenderHandler(webapp.RequestHandler):
  def render(self, template, args={}, ext='.html'):
      content = ENV.get_template(template + ext).render(args)
      self.response.out.write(content)
 
  def write(self, str):
      self.response.out.write(str)
      self.response.out.write('<br />')


def get_session():
    secure, httponly = False, True
    if DEV:
        secure = False
    session = Session(cookie_name='andrewtrusty.appspot', secure=secure, httponly=httponly)
    return session
