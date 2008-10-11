import os
import sys
import unittest
import doctest

OPTIONFLAGS = (doctest.ELLIPSIS |
               doctest.NORMALIZE_WHITESPACE)

from tempfile import gettempdir
cache_dir = gettempdir()

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
        optionflags=OPTIONFLAGS)])

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
