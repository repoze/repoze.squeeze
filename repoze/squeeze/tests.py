import unittest
import doctest

OPTIONFLAGS = (doctest.ELLIPSIS |
               doctest.NORMALIZE_WHITESPACE)

from tempfile import gettempdir
cache_dir = gettempdir()

def test_suite():
    return unittest.TestSuite([
        doctest.DocFileSuite(
        'README.txt',
        globs=dict(cache_dir=cache_dir),
        optionflags=OPTIONFLAGS,
        package="repoze.squeeze"),

        doctest.DocTestSuite(
        'repoze.squeeze.processor',
        optionflags=OPTIONFLAGS)])

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
