import os
import sys
import unittest
import doctest

OPTIONFLAGS = (doctest.ELLIPSIS |
               doctest.NORMALIZE_WHITESPACE)

from tempfile import gettempdir
cache_dir = gettempdir()

class TestResourceSqueezinMiddleware(unittest.TestCase):

    @property
    def middleware(self):
        from repoze.squeeze.processor import ResourceSqueezingMiddleware
        return ResourceSqueezingMiddleware

    @property
    def accept_request_data(self):
        from repoze.squeeze.processor import AcceptRequestData
        return AcceptRequestData

    def test_ie_conditionals(self):
        # IE conditional stylesheets should be left untouched since they
        # shouln't be combined with the other stylesheets.
        html = '''
  <html><head>
    <link type="text/css" media="screen" href="http://john/doe.css">
    <link type="text/css" media="screen" href="http://john/doegh.css">

    <!-- Internet Explorer CSS Fixes -->
    <!--[if lt IE 7]>
        <style type="text/css" media="all">
           @import url(http://foo/bar.css);
    </style>
    <![endif]-->
  </head><body></body></html>'''

        requestdata = self.accept_request_data()

        mw = self.middleware(None, url_prefix='', cache_dir=cache_dir)
        changed, expires, processed_html = mw.process_html(
            requestdata, 'foo', 'http://foo/bar.css', html)
        # It should not handle the IE comment in any way
        self.assertEqual(requestdata.stylesheets.keys(),
                         [('http://john/doe.css', 'http://john/doegh.css')])


if sys.version_info[:3] < (2,5,0):
    print "Python 2.5 is required to run the test suite."
    sys.exit(1)

def test_suite():
    return unittest.TestSuite([
        doctest.DocFileSuite(
        'README.txt',
        globs=dict(cache_dir=cache_dir, os=os),
        optionflags=OPTIONFLAGS,
        package="repoze.squeeze"),

        doctest.DocTestSuite(
        'repoze.squeeze.processor',
        optionflags=OPTIONFLAGS),
        
        unittest.makeSuite(TestResourceSqueezinMiddleware)])

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
