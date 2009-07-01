#    Readable Feeds
#    Copyright (C) 2009  
#    
#    This file originally written by Nirmal Patel (http://nirmalpatel.com/).
#    Generic feed and Google App Engine support added by Andrew Trusty (http://andrewtrusty.com/).
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



import urllib, re, os, urlparse
import HTMLParser, feedparser
from BeautifulSoup import BeautifulSoup

import rfc822
from datetime import datetime
from pickle import dumps, loads
import time

import urlgrabber

from appengine_utilities.cache import Cache


# memcache & db backed cache that stores entries for 1 week
CACHE = Cache(default_timeout = 3600 * 24 * 7)



NEGATIVE    = re.compile("comment|meta|footer|footnote|foot")
POSITIVE    = re.compile("post|hentry|entry|content|text|body|article")
PUNCTUATION = re.compile("""[!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~]""")


def grabContent(link, html):
    
    replaceBrs = re.compile("<br */? *>[ \r\n]*<br */? *>")
    html = re.sub(replaceBrs, "</p><p>", html)
    
    try:
        soup = BeautifulSoup(html)
    except HTMLParser.HTMLParseError:
        return u""
    
    # REMOVE SCRIPTS
    for s in soup.findAll("script"):
        s.extract()
    
    allParagraphs = soup.findAll("p")
    topParent     = None
    
    parents = []
    for paragraph in allParagraphs:
        
        parent = paragraph.parent
        
        if (parent not in parents):
            parents.append(parent)
            parent.score = 0
            
            if (parent.has_key("class")):
                if (NEGATIVE.match(parent["class"])):
                    parent.score -= 50
                if (POSITIVE.match(parent["class"])):
                    parent.score += 25
                    
            if (parent.has_key("id")):
                if (NEGATIVE.match(parent["id"])):
                    parent.score -= 50
                if (POSITIVE.match(parent["id"])):
                    parent.score += 25

        if (parent.score == None):
            parent.score = 0
        
        innerText = paragraph.renderContents() #"".join(paragraph.findAll(text=True))
        if (len(innerText) > 10):
            parent.score += 1
            
        parent.score += innerText.count(",")
        
    for parent in parents:
        if ((not topParent) or (parent.score > topParent.score)):
            topParent = parent

    if (not topParent):
        return u""
            
    # REMOVE LINK'D STYLES
    styleLinks = soup.findAll("link", attrs={"type" : "text/css"})
    for s in styleLinks:
        s.extract()

    # REMOVE ON PAGE STYLES
    for s in soup.findAll("style"):
        s.extract()

    # CLEAN STYLES FROM ELEMENTS IN TOP PARENT
    for ele in topParent.findAll(True):
        del(ele['style'])
        del(ele['class'])
        
    killDivs(topParent)
    clean(topParent, "form")
    clean(topParent, "object")
    clean(topParent, "iframe")
    
    fixLinks(topParent, link)
    
    return topParent.renderContents().decode('utf-8')
    

def fixLinks(parent, link):
    tags = parent.findAll(True)
    
    for t in tags:
        if (t.has_key("href")):
            t["href"] = urlparse.urljoin(link, t["href"])
        if (t.has_key("src")):
            t["src"] = urlparse.urljoin(link, t["src"])


def clean(top, tag, minWords=10000):
    tags = top.findAll(tag)

    for t in tags:
        if (t.renderContents().count(" ") < minWords):
            t.extract()


def killDivs(parent):
    
    divs = parent.findAll("div")
    for d in divs:
        p     = len(d.findAll("p"))
        img   = len(d.findAll("img"))
        li    = len(d.findAll("li"))
        a     = len(d.findAll("a"))
        embed = len(d.findAll("embed"))
        pre   = len(d.findAll("pre"))
        code  = len(d.findAll("code"))
    
        if (d.renderContents().count(",") < 10):
            if ((pre == 0) and (code == 0)):
                if ((img > p ) or (li > p) or (a > p) or (p == 0) or (embed > 0)):
                    d.extract()
    

# gives me the content i want
def upgradeLink(link, user_agent, graball=False):
    
    link = link.encode('utf-8')
    
    # TODO: handle other exceptions
    
    # XXX: also, better way to check file types would be content-type headers
    #        and don't mess with anything that isn't a webpage..
    if (not (link.startswith("http://news.ycombinator.com") or link.endswith(".pdf"))):
        linkFile = "upgraded/" + re.sub(PUNCTUATION, "_", link)
        if linkFile in CACHE:
            return CACHE[linkFile]
        else:
            content = u""
            try:
                html = urlgrabber.urlread(link, keepalive=0, user_agent=agent)
                content = grabContent(link, html, graball=graball)
                CACHE[linkFile] = content
            except IOError:
                pass
            return content
    else:
        return u""


def get_headers(feedUrl):
    if 'headers-'+feedUrl not in CACHE:
        return None, None, None
    headers = loads(CACHE['headers-'+feedUrl])
    
    # headers are lowercased by feedparser
    last_modified = headers.get('last-modified', '')
    etag = headers.get('etag', '')
    expires = headers.get('expires', '')
    
    fp_last_modified = None
    if last_modified:
        fp_last_modified = rfc822.parsedate(last_modified)
    fp_expires = None
    if expires:
        fp_expires = rfc822.parsedate(expires)
    # fp if for 9 tuple feed parser required format
    return etag, fp_last_modified, fp_expires

def save_headers(parsedFeed, feedUrl):
    CACHE['headers-'+feedUrl] = dumps(parsedFeed.headers)


class NotFeedException(Exception):
    pass

# don't use
def upgradeFeed(feedUrl, agent=None, out=None):
    
    etag, last_modified, expires = get_headers(feedUrl)
    
    # TODO: use expires header..
    #if expires and datetime.utcnow().utctimetuple() < expires:
    #    return cached entries ..??

    # Mozilla/ should catch IE, Firefox, Safari, Chrome, Epiphany, Konqueror, Flock, 
    #  & a bunch of others (also catches one version of Googlebot & Yahoo! Slurp..)
    if agent and (('Mozilla/' in agent or 'Opera/' in agent) and 
                  ('Googlebot' not in agent) and ('Yahoo!' not in agent)):
        agent = None
        # i would pass-thrhough all user-agents but feedBurner returns HTML
        #    instead of the feed with some user agents
        #    (but only on GAE & not on dev which makes this even more confusing) 
    if not agent:
        agent = 'Readable-Feeds (http://andrewtrusty.appspot.com/readability/)'
    # otherwise allow user-agent to go through for subscriber reports like
    #    Bloglines, Google FeedFetcher, et al to work

    parsedFeed = feedparser.parse(feedUrl, etag=etag, modified=last_modified,
                                  agent=agent) #, referrer=feedUrl)
    save_headers(parsedFeed, feedUrl)

    
    # test if its a feed by trying to get the title & link
    try:
        title = parsedFeed.feed.title
        link = parsedFeed.feed.link
    except: # assume that if i get title, link & subtitle its a valid feed
        raise NotFeedException("Failed to retrieve a feed!")
    
    description = parsedFeed.feed.get('subtitle', '')
    
    start_time = time.time()
    items = []
    for entry in parsedFeed.entries:
        content = upgradeLink(entry.link, agent)
        items.append((entry, content))
        
        if time.time() - start_time  > 25.0:
            # if we hit 30 seconds we go over quota, so break early
            #     at the price of one user missing older entries
            break
            
    
    return {'title':title,
            'link':link, 
            'description':description,
            'items':items}
    
    
    
if __name__ == "__main__":  
    print upgradeFeed(HN_RSS_FEED)



