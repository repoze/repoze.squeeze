repoze.squeeze
==============

This package provides a WSGI middleware component which "squeezes"
HTML documents by merging browser resources (javascript
and stylesheets).

It uses statistical analysis to determine the optimal bundles based on
the HTML documents that pass through it. Vary-headers are observed, as
are resource expiration dates.

Documents that are not squeezed are given the 'no-cache' pragma in an
expectation that we will be able to squeeze it after sufficient
burn-in. Squeezed documents are served with expiration dates no later
than the expiration dates of the squeezed resources which it
references.

Usage
-----

Configure the middleware with the following two options (required):

  @cache_dir: Relative path to a directory where we store squeezed
  resources

  @url_prefix: Path segment or full base URL that will be used to
  serve the cache directory as static files.

The following option is optional:
  
  @threshold: Floating-point parameter that controls the merge to
  apperances threshold. This parameter can normally be left at the
  default (0.5).

In addition, you must configure the WSGI application to serve the file
cache directory from the ``url_prefix`` (e.g. "cache").

Invalidation
------------

To invalidate the file cache, upstream applications can set the
"X-Squeeze-Invalidate" header to a true value; note that before the
application is called, the middleware adds this key to the environment
such that applications which can't modify the environment can still
flag for invalidation:

  >>> invalidate = environ["X-Squeeze-Invalidate"]
  >>> invalidate()

This will reset the file cache registry; note that no cache files are
ever deleted (to preserve web server integrity). You can manually
purge the file cache at any time be deleting the files (this is
allowed at run-time).
