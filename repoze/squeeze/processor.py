""" Middleware that squeezes resources."""

import re
import os
import urlparse
import lxml.html
import sha
import mimetypes
import logging
import webob
import urllib

logger = logging.getLogger("squeeze")
    
try:
    from repoze.xmliter import XMLSerializer
except ImportError:
    def XMLSerializer(tree, serializer=None):
        return lxml.html.tostring(tree, pretty_print=True)

from cStringIO import StringIO

re_stylesheet_import = re.compile(
    r'^((?:<!--)?\s*@import\surl*\()([^\)]+)(\);?\s*(?:-->)?)$')

re_stylesheet_url = re.compile(
    r'url\((?![A-Za-z]+://)([^\)]+)\)')

class AcceptRequestData(object):
    def __init__(self):
        self.appearances = {}
        self.javascripts = {}
        self.stylesheets = {}
        self.cache = {}
        
class ResourceSqueezingMiddleware(object):
    def __init__(self, app, cache_dir=None, url_prefix=None, threshold=0.5):
        if url_prefix is None:
            raise ValueError("Must configure URL prefix (`url_prefix`).")
        if cache_dir is None:
            raise ValueError("Must configure cache directory (`cache_dir`).")
        
        self.app = app
        self.cache_dir = cache_dir
        self.url_prefix = url_prefix
        self.threshold = threshold
        self.accept_request_registry = {}
        
    def get_merged_resource(self, cache, selection, mediatypes):
        expires = None
        
        # verify that the entire selection is in the cache
        for url in selection:
            if url not in cache:
                return expires, None

        # create extension
        ext = None
        body, mimetype, ttl = cache[selection[0]]
        if mimetype is not None:
            ext = mimetypes.guess_extension(mimetype)

        # compute digest
        out = StringIO()
        for url, body, mimetype, ttl in ((s,) + cache.get(s)
                                         for s in selection):
            mediatype = mediatypes.get(url)
            if expires is None or ttl < expires:
                expires = ttl
            if mimetype == 'text/css' and mediatype:
                out.write('@media %s {\n%s}\n' % (mediatype, body))
            else:
                out.write(body)
        body = out.getvalue()
        digest = sha.new(body).hexdigest() + (ext or "")

        # write file to cache
        filename = os.path.join(self.cache_dir, digest)
        if not os.path.exists(filename):
            file(filename, 'w').write(body)

        return expires, digest

    def get_url_for_resource(self, host, resource):
        if self.url_prefix.startswith('http'):
            return "/".join((self.url_prefix.rstrip('/'), resource))                
        return "/".join((host, self.url_prefix.strip('/'), resource))
        
    def __call__(self, environ, start_response):
        request = webob.Request(environ)
        response = request.get_response(self.app, catch_exc_info=True)

        # get accept request data object based on the value of the vary-header
        vary = map(request.environ.get, response.vary or ('*',))
        accept_request_data = self.accept_request_registry.setdefault(
            ",".join(filter(None, vary)), AcceptRequestData())

        content_type = response.content_type
        if content_type and content_type.startswith('text/html'):
            # process document body
            changed, expires, body = self.process_html(
                accept_request_data, request.host_url, request.path, response.body)

            # if document is unchanged, set the cache-headers as
            if not changed:
                response.cache_control = 'no-cache'

            # set the response expiration date to the minimum value in
            # the set of the response expiration date and the resource
            # expiration date(s).
            if expires and response.expires:
                response.expires = min(response.expires, expires)

            # set new body
            response.body = body

        # if url matches a URL we've seen in a processed document, and
        # if it's served from this host, process the response body and
        # cache it
        url = urllib.unquote(request.url)
        if url in accept_request_data.appearances:
            ttl = response.expires
            if content_type == 'text/css':
                base_path = os.path.dirname(url)
                response.body = re_stylesheet_url.sub(
                    'url(%s/\\1)' % base_path, response.body)

            status_code = int(response.status.split(' ', 1)[0])
            if status_code == 200:
                accept_request_data.cache[url] = response.body, content_type, ttl
            elif status_code == 304:
                # update ttl for cached resource
                cache = accept_request_data.cache.get(url)
                if cache is not None:
                    body, content_type, previous_ttl = cache
                    accept_request_data.cache[url] = body, content_type, ttl

        return response(environ, start_response)


    def process_html(self, accept_request_data, host, uri, body):
        javascripts = accept_request_data.javascripts
        stylesheets = accept_request_data.stylesheets
        appearances = accept_request_data.appearances
        cache = accept_request_data.cache

        if not body.strip():
            return False, None, body

        tree = lxml.html.fromstring(body)
        changed = False

        expires = None
        # process javascripts and stylesheets in two loops
        for groups, xpath in (
            (javascripts, './/head/script[@src]'),
            (stylesheets, './/head/link[@href] | .//head/style')):
            items = []
            elements = tree.xpath(xpath)
            for element in elements:
                mutator, accessor = tag_functions[element.tag]
                url = accessor(element)
                if url is not None:
                    items.append(get_url(tree, host, uri, url))
            selections = maintain_appearances(
                items, groups, appearances, self.threshold)
            ttl, changed = self.update_elements(
                elements, selections, tree, host, uri, cache) or changed

            if expires is None or ttl < expires:
                expires = ttl                
                
        return changed, expires, XMLSerializer(tree, lxml.html.tostring)

    def update_elements(self, elements, selections, tree, host, uri, cache):
        changed = False
        expires = None
        mediatypes = {}

        for element in elements:
            parent = element.getparent()
            mutator, accessor = tag_functions[element.tag]
            url = accessor(element)
            if url is None:
                continue
            
            # prepend base path to relative path
            src = get_url(tree, host, uri, url)
            mediatypes[src] = element.attrib.get('media')

            if not src.startswith(host):
                continue

            for selection in selections:
                ttl, resource = self.get_merged_resource(cache, selection,
                                                         mediatypes)

                if resource is None or src not in selection:
                    continue

                if expires is None or ttl < expires:
                    expires = ttl

                # if this is the last item in the selection,
                # merge and update link, else remove it.
                if src == selection[-1]:
                    url = self.get_url_for_resource(host, resource)
                    changed = True
                    mutator(element, url)
                else:
                    parent.remove(element)
                    break
                    
        return expires, changed

def update_script_tag(element, url):
    element.attrib['src'] = url

def update_link_tag(element, url):
    element.attrib['href'] = url

def update_style_tag(element, url):
    """Match style tag with regular expression.

    >>> re_stylesheet_import.match('<!-- @import url(foo.css); -->').groups()
    ('<!-- @import url(', 'foo.css', '); -->')
    
    >>> re_stylesheet_import.match('@import url(foo.css);').groups()
    ('@import url(', 'foo.css', ');')
    
    """
    
    m = re_stylesheet_import.match(element.text)
    if m is not None:
        before = m.group(1)
        path = m.group(2)
        after = m.group(3)
        element.text = before+url+after
        
def get_script_url(element):
    return element.attrib['src']

def get_link_url(element):
    return element.attrib['href']

def get_style_url(element):
    m = re_stylesheet_import.match(element.text)
    if m is not None:
        return m.group(2)
    
tag_functions = dict(
    script=(update_script_tag, get_script_url),
    link=(update_link_tag, get_link_url),
    style=(update_style_tag, get_style_url))

def make_squeeze_middleware(app, global_conf, **kw):
    return ResourceSqueezingMiddleware(app, **kw)

def get_url(tree, host, uri, src):
    if src.startswith('http://'):
        return src
    
    if tree.xpath('.//base'):
        url = tree.xpath('.//base')[0].attrib['href']
    else:
        path = "/".join((host, uri))
        protocol, host, path, query, fragment = urlparse.urlsplit(path)
        path = os.path.dirname(path)
        url = urlparse.urlunsplit((protocol, host, path, query, fragment))

    return "/".join((url.rstrip('/'), src))

def get_slices_ordered_by_size(items):
    slices = []
    length = len(items)
    for i in range(length):
        for j in range(i+1, length+1):
            slices.append(tuple(items[i:j]))
    slices.sort(key=lambda item: len(item))
    return slices

def maintain_appearances(refs, groups, appearances, threshold):
    """Update group statistics.

    >>> abcde = tuple('abcde')
    >>> abcd = tuple('abcd')
    >>> abc = tuple('abc')
    >>> de = tuple('de')

    >>> appearances = {}
    >>> groups = {}
    
    >>> maintain_appearances(abcde, groups, appearances, 0.8)
    [('a', 'b', 'c', 'd', 'e')]

    The groups should be updated accordingly.

    >>> groups, appearances
    ({('a', 'b', 'c', 'd', 'e'): 1},
     {'a': 1, 'c': 1, 'b': 1, 'e': 1, 'd': 1})

    Running the same set will update all numbers.
    
    >>> maintain_appearances(abcde, groups, appearances, 0.8)
    [('a', 'b', 'c', 'd', 'e')]

    >>> groups, appearances
    ({('a', 'b', 'c', 'd', 'e'): 2},
     {'a': 2, 'c': 2, 'b': 2, 'e': 2, 'd': 2})

    Now let's run a subset.

    >>> maintain_appearances(abc, groups, appearances, 0.8)
    []

    We now expect to see the inverse group, too.

    >>> groups.keys()
    [('a', 'b', 'c', 'd', 'e'), ('a', 'b', 'c'), ('d', 'e')]
    
    Let's adjust the threshold to see the inclusion of this group.

    >>> maintain_appearances(abc, groups, appearances, 0.4)
    [('a', 'b', 'c')]

    Now, for a real-world scenario.

    >>> for i in range(1000):
    ...     _ = maintain_appearances(abcde, groups, appearances, 0.8)

    >>> for i in range(1000):
    ...     _ = maintain_appearances(abc, groups, appearances, 0.8)

    >>> maintain_appearances(abcde, groups, appearances, 0.8)
    [('a', 'b', 'c'), ('d', 'e')]
    
    >>> appearances
    {'a': 2005, 'c': 2005, 'b': 2005, 'e': 1003, 'd': 1003}

    >>> groups
    {('a', 'b', 'c', 'd', 'e'): 1003,
     ('a', 'b', 'c'): 2003,
     ('d', 'e'): 1001}

    >>> maintain_appearances(abcd, groups, appearances, 0.8)
    [('a', 'b', 'c')]

    >>> maintain_appearances(de, groups, appearances, 0.8)
    [('d', 'e')]
    """

    # increase our appearance count (how many times this
    # resource has passed through the middleware
    for ref in refs:
        appearances.setdefault(ref, 0)
        appearances[ref] += 1

    groups.setdefault(tuple(refs), 0)
            
    selections = []
    # pick out combinations iterator-style
    for selection in get_slices_ordered_by_size(refs):
        if len(selection) == 1:
            continue
        
        value = groups.get(selection)
        if value is not None:
            # update values
            value = groups[selection] = 1 + value

            # calculate "seen together" ratio
            highest = max(map(appearances.get, selection)) or 1

            ratio = float(value)/highest

            if ratio > threshold:
                selections.append(selection)

            for group in groups.keys():
                if group != selection:
                    inverse = tuple(ref for ref in group if ref not in selection)
                    if len(inverse):
                        groups.setdefault(inverse, 0)

    refs = list(refs)
    selections.sort(key=lambda selection: refs.index(selection[0]))
    return selections
