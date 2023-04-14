# -*- coding: utf-8 -*-
"""
Copyright (c) 2008, appengine-utilities project
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
- Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.
- Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.
- Neither the name of the appengine-utilities project nor the names of its
  contributors may be used to endorse or promote products derived from this
  software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

# main python imports
import os
import time
import datetime
import random
import md5
import CustomCookie as Cookie
import pickle
import __main__
from time import strftime

# google appengine imports
from google.appengine.ext import db
from google.appengine.api import memcache

#django simplejson import, used for flash
from django.utils import simplejson

from rotmodel import ROTModel

# settings, if you have these set elsewhere, such as your django settings file,
# you'll need to adjust the values to pull from there.


class _AppEngineUtilities_Session(ROTModel):
    """
    Model for the sessions in the datastore. This contains the identifier and
    validation information for the session.
    """

    sid = db.StringListProperty()
    ip = db.StringProperty()
    ua = db.StringProperty()
    last_activity = db.DateTimeProperty(auto_now=True)


class _AppEngineUtilities_SessionData(ROTModel):
    """
    Model for the session data in the datastore.
    """

    session = db.ReferenceProperty(_AppEngineUtilities_Session)
    keyname = db.StringProperty()
    content = db.BlobProperty()

class _DatastoreWriter(object):

    def put(self, keyname, value, session):
        """
        Insert a keyname/value pair into the datastore for the session.

        Args:
            keyname: The keyname of the mapping.
            value: The value of the mapping.
        """
        keyname = session._validate_key(keyname)
        if value is None:
            raise ValueError('You must pass a value to put.')

        # datestore write trumps cookie. If there is a cookie value
        # with this keyname, delete it so we don't have conflicting
        # entries.
        if session.cookie_vals.has_key(keyname):
            del(session.cookie_vals[keyname])
            session.output_cookie[session.cookie_name + '_data'] = \
                simplejson.dumps(session.cookie_vals)
            print session.output_cookie.output()

        sessdata = session._get(keyname=keyname)
        if sessdata is None:
            sessdata = _AppEngineUtilities_SessionData()
            sessdata.session = session.session
            sessdata.keyname = keyname
        sessdata.content = pickle.dumps(value)
        # UNPICKLING CACHE session.cache[keyname] = pickle.dumps(value)
        session.cache[keyname] = value
        sessdata.put()
        session._set_memcache()


class _CookieWriter(object):
    def put(self, keyname, value, session):
        """
        Insert a keyname/value pair into the datastore for the session.

        Args:
            keyname: The keyname of the mapping.
            value: The value of the mapping.
        """
        keyname = session._validate_key(keyname)
        if value is None:
            raise ValueError('You must pass a value to put.')

        # Use simplejson for cookies instead of pickle.
        session.cookie_vals[keyname] = value
        # update the requests session cache as well.
        session.cache[keyname] = value
        session.output_cookie[session.cookie_name + '_data'] = \
            simplejson.dumps(session.cookie_vals)
        print session.output_cookie.output()

class Session(object):
    """
    Sessions used to maintain user presence between requests.

    Sessions store a unique id as a cookie in the browser and
    referenced in a datastore object. This maintains user presence
    by validating requests as visits from the same browser.

    You can add extra data to the session object by using it
    as a dictionary object. Values can be any python object that
    can be pickled.

    For extra performance, session objects are also store in
    memcache and kept consistent with the datastore. This
    increases the performance of read requests to session
    data.
    """

    COOKIE_NAME = 'appengine-utilities-session-sid' # session token
    DEFAULT_COOKIE_PATH = '/'
    SESSION_EXPIRE_TIME = 7200 # sessions are valid for 7200 seconds (2 hours)
    CLEAN_CHECK_PERCENT = 50 # By default, 50% of all requests will clean the database
    INTEGRATE_FLASH = True # integrate functionality from flash module?
    CHECK_IP = True # validate sessions by IP
    CHECK_USER_AGENT = True # validate sessions by user agent
    SET_COOKIE_EXPIRES = True # Set to True to add expiration field to cookie
    SESSION_TOKEN_TTL = 5 # Number of seconds a session token is valid for.
    UPDATE_LAST_ACTIVITY = 60 # Number of seconds that may pass before
                            # last_activity is updated
    WRITER = "datastore" # Use the datastore writer by default. cookie is the
                        # other option.


    def __init__(self, cookie_path=DEFAULT_COOKIE_PATH,
            cookie_name=COOKIE_NAME,
            session_expire_time=SESSION_EXPIRE_TIME,
            clean_check_percent=CLEAN_CHECK_PERCENT,
            integrate_flash=INTEGRATE_FLASH, check_ip=CHECK_IP,
            check_user_agent=CHECK_USER_AGENT,
            set_cookie_expires=SET_COOKIE_EXPIRES,
            session_token_ttl=SESSION_TOKEN_TTL,
            last_activity_update=UPDATE_LAST_ACTIVITY,
            writer=WRITER, secure=False, httponly=False):
        """
        Initializer

        Args:
          cookie_name: The name for the session cookie stored in the browser.
          session_expire_time: The amount of time between requests before the
              session expires.
          clean_check_percent: The percentage of requests the will fire off a
              cleaning routine that deletes stale session data.
          integrate_flash: If appengine-utilities flash utility should be
              integrated into the session object.
          check_ip: If browser IP should be used for session validation
          check_user_agent: If the browser user agent should be used for
              sessoin validation.
          set_cookie_expires: True adds an expires field to the cookie so
              it saves even if the browser is closed.
          session_token_ttl: Number of sessions a session token is valid
              for before it should be regenerated.
        """

        self.cookie_path = cookie_path
        self.cookie_name = cookie_name
        self.session_expire_time = session_expire_time
        self.integrate_flash = integrate_flash
        self.check_user_agent = check_user_agent
        self.check_ip = check_ip
        self.set_cookie_expires = set_cookie_expires
        self.session_token_ttl = session_token_ttl
        self.last_activity_update = last_activity_update
        self.writer = writer

        # make sure the page is not cached in the browser
        self.no_cache_headers()
        # Check the cookie and, if necessary, create a new one.
        self.cache = {}
        string_cookie = os.environ.get('HTTP_COOKIE', '')
        self.cookie = Cookie.SimpleCookie()
        self.output_cookie = Cookie.SimpleCookie()
        self.cookie.load(string_cookie)
        try:
            self.cookie_vals = \
                simplejson.loads(self.cookie[self.cookie_name + '_data'].value)
                # sync self.cache and self.cookie_vals which will make those
                # values available for all gets immediately.
            for k in self.cookie_vals:
                self.cache[k] = self.cookie_vals[k]
                self.output_cookie[self.cookie_name + '_data'] = self.cookie[self.cookie_name + '_data']
            # sync the input cookie with the output cookie
        except:
            self.cookie_vals = {}


        if writer == "cookie":
            pass
        else:
            self.sid = None
            new_session = True

            # do_put is used to determine if a datastore write should
            # happen on this request.
            do_put = False

            # check for existing cookie
            if self.cookie.get(cookie_name):
                self.sid = self.cookie[cookie_name].value
                self.session = self._get_session() # will return None if
                                                   # sid expired
                if self.session:
                    new_session = False

            if new_session:
                # start a new session
                self.session = _AppEngineUtilities_Session()
                self.session.put()
                self.sid = self.new_sid()
                if 'HTTP_USER_AGENT' in os.environ:
                    self.session.ua = os.environ['HTTP_USER_AGENT']
                else:
                    self.session.ua = None
                if 'REMOTE_ADDR' in os.environ:
                    self.session.ip = os.environ['REMOTE_ADDR']
                else:
                    self.session.ip = None
                self.session.sid = [self.sid]
                # do put() here to get the session key
                key = self.session.put()
            else:
                # check the age of the token to determine if a new one
                # is required
                duration = datetime.timedelta(seconds=self.session_token_ttl)
                session_age_limit = datetime.datetime.now() - duration
                if self.session.last_activity < session_age_limit:
                    self.sid = self.new_sid()
                    if len(self.session.sid) > 2:
                        self.session.sid.remove(self.session.sid[0])
                    self.session.sid.append(self.sid)
                    do_put = True
                else:
                    self.sid = self.session.sid[-1]
                    # check if last_activity needs updated
                    ula = datetime.timedelta(seconds=self.last_activity_update)
                    if datetime.datetime.now() > self.session.last_activity + ula:
                        do_put = True

            self.output_cookie[cookie_name] = self.sid
            self.output_cookie[cookie_name]['path'] = cookie_path
            
            # Added by me
            if httponly:
                self.output_cookie[cookie_name]['httponly'] = True
            if secure:
                self.output_cookie[cookie_name]['secure'] = True

            # UNPICKLING CACHE self.cache['sid'] = pickle.dumps(self.sid)
            self.cache['sid'] = self.sid

            if do_put:
                if self.sid != None or self.sid != "":
                    self.session.put()

        if self.set_cookie_expires:
            if not self.output_cookie.has_key(cookie_name + '_data'):
                self.output_cookie[cookie_name + '_data'] = ""
            self.output_cookie[cookie_name + '_data']['expires'] = \
                self.session_expire_time
        print self.output_cookie.output()

        # fire up a Flash object if integration is enabled
        if self.integrate_flash:
            import flash
            self.flash = flash.Flash(cookie=self.cookie)

        # randomly delete old stale sessions in the datastore (see
        # CLEAN_CHECK_PERCENT variable)
        if random.randint(1, 100) < clean_check_percent:
            self._clean_old_sessions() 

    def new_sid(self):
        """
        Create a new session id.
        """
        return (
            str(self.session.key())
            + md5.new(repr(time.time()) + str(random.random())).hexdigest()
        )

    def _get_session(self):
        """
        Get the user's session from the datastore
        """
        query = _AppEngineUtilities_Session.all()
        query.filter('sid', self.sid)
        if self.check_user_agent:
            query.filter('ua', os.environ['HTTP_USER_AGENT'])
        if self.check_ip:
            query.filter('ip', os.environ['REMOTE_ADDR'])
        results = query.fetch(1)
        if len(results) is 0:
            return None
        sessionAge = datetime.datetime.now() - results[0].last_activity
        if sessionAge.seconds > self.session_expire_time:
            results[0].delete()
            return None
        return results[0]

    def _get(self, keyname=None):
        """
        Return all of the SessionData object data from the datastore onlye,
        unless keyname is specified, in which case only that instance of 
        SessionData is returned.
        Important: This does not interact with memcache and pulls directly
        from the datastore. This also does not get items from the cookie
        store.

        Args:
            keyname: The keyname of the value you are trying to retrieve.
        """
        query = _AppEngineUtilities_SessionData.all()
        query.filter('session', self.session)
        if keyname != None:
            query.filter('keyname =', keyname)
        results = query.fetch(1000)

        if len(results) is 0:
            return None
        return results[0] if keyname != None else results

    def _validate_key(self, keyname):
        """
        Validate the keyname, making sure it is set and not a reserved name.
        """
        if keyname is None:
            raise ValueError('You must pass a keyname for the session' + \
                    ' data content.')
        elif keyname in ('sid', 'flash'):
            raise ValueError(f'{keyname} is a reserved keyname.')

        return str(keyname) if type(keyname) != type([str, unicode]) else keyname

    def _put(self, keyname, value):
        """
        Insert a keyname/value pair into the datastore for the session.

        Args:
            keyname: The keyname of the mapping.
            value: The value of the mapping.
        """
        writer = _DatastoreWriter() if self.writer == "datastore" else _CookieWriter()
        writer.put(keyname, value, self)

    def _delete_session(self):
        """
        Delete the session and all session data.
        """
        if hasattr(self, "session"):
            sessiondata = self._get()
            # delete from datastore
            if sessiondata is not None:
                for sd in sessiondata:
                    sd.delete()
            # delete from memcache
            memcache.delete('sid-'+str(self.session.key()))
            # delete the session now that all items that reference it are deleted.
            self.session.delete()
        # unset any cookie values that may exist
        self.cookie_vals = {}
        self.cache = {}
        self.output_cookie[self.cookie_name + '_data'] = \
            simplejson.dumps(self.cookie_vals)
        print self.output_cookie.output()

        # if the event class has been loaded, fire off the sessionDeleted event
        if 'AEU_Events' in __main__.__dict__:
            __main__.AEU_Events.fire_event('sessionDelete')

    def delete(self):
        """
        Delete the current session and start a new one.

        This is useful for when you need to get rid of all data tied to a
        current session, such as when you are logging out a user.
        """
        self._delete_session()

    @classmethod
    def delete_all_sessions(cls):
        """
        Deletes all sessions and session data from the data store and memcache:

        NOTE: This is not fully developed. It also will not delete any cookie
        data as this does not work for each incoming request. Keep this in mind
        if you are using the cookie writer.
        """
        all_sessions_deleted = False
        all_data_deleted = False

        while not all_sessions_deleted:
            query = _AppEngineUtilities_Session.all()
            results = query.fetch(75)
            if len(results) is 0:
                all_sessions_deleted = True
            else:
                for result in results:
                    memcache.delete(f'sid-{str(result.key())}')
                    result.delete()

        while not all_data_deleted:
            query = _AppEngineUtilities_SessionData.all()
            results = query.fetch(75)
            if len(results) is 0:
                all_data_deleted = True
            else:
                for result in results:
                    result.delete()

    def _clean_old_sessions(self):
        """
        Delete expired sessions from the datastore.

        This is only called for CLEAN_CHECK_PERCENT percent of requests because
        it could be rather intensive.
        """
        duration = datetime.timedelta(seconds=self.session_expire_time)
        session_age = datetime.datetime.now() - duration
        query = _AppEngineUtilities_Session.all()
        query.filter('last_activity <', session_age)
        results = query.fetch(50)
        for result in results:
            data_query = _AppEngineUtilities_SessionData.all()
            data_query.filter('session', result)
            data_results = data_query.fetch(1000)
            for data_result in data_results:
                data_result.delete()
            memcache.delete(f'sid-{str(result.key())}')
            result.delete()

    # Implement Python container methods

    def __getitem__(self, keyname):
        """
        Get item from session data.

        keyname: The keyname of the mapping.
        """
        # flash messages don't go in the datastore

        if self.integrate_flash and (keyname == 'flash'):
            return self.flash.msg
        if keyname in self.cache:
            # UNPICKLING CACHE return pickle.loads(str(self.cache[keyname]))
            return self.cache[keyname]
        if keyname in self.cookie_vals:
            return self.cookie_vals[keyname]
        if hasattr(self, "session"):
            mc = memcache.get(f'sid-{str(self.session.key())}')
            if mc is not None and keyname in mc:
                return mc[keyname]
            if data := self._get(keyname):
                #UNPICKLING CACHE self.cache[keyname] = data.content
                self.cache[keyname] = pickle.loads(data.content)
                self._set_memcache()
                return pickle.loads(data.content)
            else:
                raise KeyError(str(keyname))
        raise KeyError(str(keyname))

    def __setitem__(self, keyname, value):
        """
        Set item in session data.

        Args:
            keyname: They keyname of the mapping.
            value: The value of mapping.
        """

        if self.integrate_flash and (keyname == 'flash'):
            self.flash.msg = value
        else:
            keyname = self._validate_key(keyname)
            self.cache[keyname] = value
            # self._set_memcache() # commented out because this is done in the datestore put
            return self._put(keyname, value)

    def delete_item(self, keyname, throw_exception=False):
        """
        Delete item from session data, ignoring exceptions if
        necessary.

        Args:
            keyname: The keyname of the object to delete.
            throw_exception: false if exceptions are to be ignored.
        Returns:
            Nothing.
        """
        if throw_exception:
            self.__delitem__(keyname)
            return None
        else:
            try:
                self.__delitem__(keyname)
            except KeyError:
                return None

    def __delitem__(self, keyname):
        """
        Delete item from session data.

        Args:
            keyname: The keyname of the object to delete.
        """
        bad_key = False
        sessdata = self._get(keyname = keyname)
        if sessdata is None:
            bad_key = True
        else:
            sessdata.delete()
        if keyname in self.cookie_vals:
            del self.cookie_vals[keyname]
            bad_key = False
            self.output_cookie[self.cookie_name + '_data'] = \
                simplejson.dumps(self.cookie_vals)
            print self.output_cookie.output()
        if bad_key:
            raise KeyError(str(keyname))
        if keyname in self.cache:
            del self.cache[keyname]
        self._set_memcache()

    def __len__(self):
        """
        Return size of session.
        """
        # check memcache first
        if hasattr(self, "session"):
            mc = memcache.get(f'sid-{str(self.session.key())}')
            if mc is not None:
                return len(mc) + len(self.cookie_vals)
            results = self._get()
            return len(results) + len(self.cookie_vals) if results is not None else 0
        return len(self.cookie_vals)

    def __contains__(self, keyname):
        """
        Check if an item is in the session data.

        Args:
            keyname: The keyname being searched.
        """
        try:
            r = self.__getitem__(keyname)
        except KeyError:
            return False
        return True

    def __iter__(self):
        """
        Iterate over the keys in the session data.
        """
        # try memcache first
        if hasattr(self, "session"):
            mc = memcache.get(f'sid-{str(self.session.key())}')
            if mc is not None:
                yield from mc
            else:
                for k in self._get():
                    yield k.keyname
        yield from self.cookie_vals

    def __str__(self):
        """
        Return string representation.
        """

        #if self._get():
        return '{' + ', '.join([f'"{k}" = "{self[k]}"' for k in self]) + '}'
        #else:
        #    return []

    def _set_memcache(self):
        """
        Set a memcache object with all the session data. Optionally you can
        add a key and value to the memcache for put operations.
        """
        # Pull directly from the datastore in order to ensure that the
        # information is as up to date as possible.
        if self.writer == "datastore":
            data = {}
            sessiondata = self._get()
            if sessiondata is not None:
                for sd in sessiondata:
                    data[sd.keyname] = pickle.loads(sd.content)

            memcache.set(f'sid-{str(self.session.key())}', data, self.session_expire_time)

    def cycle_key(self):
        """
        Changes the session id.
        """
        self.sid = self.new_sid()
        if len(self.session.sid) > 2:
            self.session.sid.remove(self.session.sid[0])
        self.session.sid.append(self.sid)

    def flush(self):
        """
        Delete's the current session, creating a new one.
        """
        self._delete_session()
        self.__init__()

    def no_cache_headers(self):
        """
        Adds headers, avoiding any page caching in the browser. Useful for highly
        dynamic sites.
        """
        print "Expires: Tue, 03 Jul 2001 06:00:00 GMT"
        print strftime("Last-Modified: %a, %d %b %y %H:%M:%S %Z")
        print "Cache-Control: no-store, no-cache, must-revalidate, max-age=0"
        print "Cache-Control: post-check=0, pre-check=0"
        print "Pragma: no-cache"

    def clear(self):
        """
        Remove all items
        """
        sessiondata = self._get()
        # delete from datastore
        if sessiondata is not None:
            for sd in sessiondata:
                sd.delete()
        # delete from memcache
        memcache.delete('sid-'+str(self.session.key()))
        self.cache = {}
        self.cookie_vals = {}
        self.output_cookie[self.cookie_name + '_data'] = \
            simplejson.dumps(self.cookie_vals)
        print self.output_cookie.output()

    def has_key(self, keyname):
        """
        Equivalent to k in a, use that form in new code
        """
        return self.__contains__(keyname)

    def items(self):
        """
        A copy of list of (key, value) pairs
        """
        return {k: self[k] for k in self}

    def keys(self):
        """
        List of keys.
        """
        return list(self)

    def update(*dicts):
        """
        Updates with key/value pairs from b, overwriting existing keys, returns None
        """
        for dict in dicts:
            for k in dict:
                self._put(k, dict[k])
        return None

    def values(self):
        """
        A copy list of values.
        """
        return [self[k] for k in self]

    def get(self, keyname, default = None):
        """
        a[k] if k in a, else x
        """
        try:
            return self.__getitem__(keyname)
        except KeyError:
            return default if default is not None else None

    def setdefault(self, keyname, default = None):
        """
        a[k] if k in a, else x (also setting it)
        """
        try:
            return self.__getitem__(keyname)
        except KeyError:
            if default is not None:
                self.__setitem__(keyname, default)
                return default
            return None

    @classmethod
    def check_token(cls, cookie_name=COOKIE_NAME, delete_invalid=True):
        """
        Retrieves the token from a cookie and validates that it is
        a valid token for an existing cookie. Cookie validation is based
        on the token existing on a session that has not expired.

        This is useful for determining if datastore or cookie writer
        should be used in hybrid implementations.

        Args:
            cookie_name: Name of the cookie to check for a token.
            delete_invalid: If the token is not valid, delete the session
                            cookie, to avoid datastore queries on future
                            requests.

        Returns True/False
        """

        string_cookie = os.environ.get('HTTP_COOKIE', '')
        cookie = Cookie.SimpleCookie()
        cookie.load(string_cookie)
        if cookie.has_key(cookie_name):
            query = _AppEngineUtilities_Session.all()
            query.filter('sid', cookie[cookie_name].value)
            results = query.fetch(1)
            if len(results) > 0:
                return True
            else:
                if delete_invalid:
                    output_cookie = Cookie.SimpleCookie()
                    output_cookie[cookie_name] = cookie[cookie_name]
                    output_cookie[cookie_name]['expires'] = 0
                    print output_cookie.output()
        return False
