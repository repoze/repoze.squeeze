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

The middleware requires two following options to be set:

  @cache_dir: Relative path to a directory where we store squeezed
  resources

  @url_prefix: Path segment or full base URL that will be used to
  serve the cache directory as static files.

Remember to configure a WSGI application to serve the squeezed
resources!


