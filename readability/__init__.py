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

__all__ = ['ReadabilityHandler', 'ReadabilityFeedHandler', 'ReadabilitySiteHandler']


import hn

from gae_utils import *

from google.appengine.ext import db

class Feed(db.Model):
    url = db.StringProperty(required=True)
    hits = db.IntegerProperty(default=1) 
    created = db.DateTimeProperty(auto_now_add=True)
    title = db.StringProperty(default='')

    def feed_url(self):
        return '/readability/feed?url=%s' % urlquote(self.url)
    

class ReadabilityHandler(RenderHandler):
    def get(self):
        args = utils.storage()
        
        args.top_feeds = Feed.all().order('-hits').fetch(10)
        args.newest_feeds = Feed.all().order('-created').fetch(10)
        args.url = 'http://andrewtrusty.appspot.com/readability/'
        args.title = 'Readable Feeds'
        
        self.render('readability.index', args)


class ReadabilityFeedHandler(RenderHandler):
    def get(self):
        
        # TODO: gzip.. & set caching headers: etag, last-modified, expires, cache-control, ..
        
        feed_url = self.request.get('url')
        if not feed_url.startswith('http') or '://' not in feed_url or feed_url == 'http://':
            self.response.set_status(400)
            self.response.out.write('bad website/feed url, please specify the full URL'+
                                    '<br /><br /><a href="/readability/">&laquo; back</a>')
            return
        
        feed = db.GqlQuery("SELECT * FROM Feed WHERE url = :1",
                           feed_url).get()
        if feed:
            feed.hits += 1
        else:
            feed = Feed(url=feed_url)
        
        args = None
        try:
            args = hn.upgradeFeed(feed_url, agent=self.request.user_agent)
        except hn.NotFeedException:
            self.response.set_status(404)
            self.response.out.write("couldn't find a feed at the given URL, is the website down?"+
                                    '<br /><br /><a href="/readability/">&laquo; back</a>')
            return
        
        feed.title = args['title'] # XXX: could also save description..
        feed.put()
        
        self.response.headers["Content-Type"] = "text/xml; charset=UTF-8"
        self.render('readability.feed', args, ext='.xml')
        
        


class ReadabilitySiteHandler(RenderHandler):
    def get(self):
        site = self.request.get('url')
        
        args = utils.storage()
        self.render('index', args)