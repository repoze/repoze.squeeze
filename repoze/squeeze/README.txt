Documentation
=============

When an HTML document is passed through the filter, we take note of
the browser resources referenced in the DOM.

  >>> document = """\
  ... <html>
  ...  <head>
  ...    <meta><title>Example page</title></meta>
  ...    <script type="text/javascript" src="foo.js"></script>
  ...    <script type="text/javascript" src="bar.js"></script>
  ...    <link type="text/css" href="foo.css" />
  ...    <link type="text/css" href="print-foo.css" media="print" />
  ...    <link type="text/css" href="print-bar.css" media="print" />
  ...    <style><!-- @import url(bar.css); --></style>
  ...  </head>
  ... </html>"""

To verify HTML output, we use lxml's doctest extension.
  
  >>> import lxml.html.usedoctest  

This document would be served by a WSGI application sitting in front
of the middleware. For testing purposes, we'll set up an application
function which lets us choose which content to serve using a simple
list structure.

  >>> app_data = [document, 'text/html']
  
  >>> def app(environ, start_response):
  ...     body, content_type = app_data[:2]
  ...     headers = app_data[2:]
  ...     start_response(
  ...         '200 OK', [('content-type', content_type),
  ...                    ('content-length', str(len(body)))] + headers)
  ...     return (body,)

  >>> from repoze.squeeze.processor import make_squeeze_middleware
  >>> middleware = make_squeeze_middleware(
  ...     app, None, url_prefix='squeeze', cache_dir=cache_dir)

To verify results, we'll catch the WSGI responses in a list.

  >>> response = []
  >>> def start_response(*args):
  ...     response.append(args)

The first time we run the document through the middleware, we don't
expect any action to happen because we have not yet requested the
actual resources (so we couldn't possibly merge them).

  >>> from webob import Request
  >>> environ = Request.blank("/foo.html").environ
  >>> print "".join(middleware(environ, start_response))
  <html>
    <head>
      <meta>
      <title>Example page</title>
      <script type="text/javascript" src="foo.js"></script>
      <script type="text/javascript" src="bar.js"></script>
      <link href="foo.css" type="text/css">
      <link href="print-foo.css" media="print" type="text/css">
      <link href="print-bar.css" media="print" type="text/css">
      <style><!-- @import url(bar.css); --></style>
    </head>
  </html>

Request the resources that our example document references.

  >>> test_javascript = "/* An example javascript */"
  
  >>> test_stylesheet = """\
  ... body { background: url(background.png) repeat-xy; }
  ... body { background-image: url(background.png) repeat-xy; }
  ... """
  
  >>> def process_demo_resources(middleware, headers=[]):
  ...     app_data[:] = [test_javascript, "application/javascript"] + headers
  ...     for resource in ('/foo.js', '/bar.js'):
  ...         environ = Request.blank(resource).environ
  ...         middleware(environ, start_response)
  ...     app_data[:] = [test_stylesheet, 'text/css'] + headers
  ...     for resource in ('/foo.css', '/bar.css',
  ...                      '/print-foo.css', '/print-bar.css'):
  ...         environ = Request.blank(resource).environ
  ...         middleware(environ, start_response)

  >>> process_demo_resources(middleware)
  
Now we should have a full cache with regards to these resources.

  >>> environ = Request.blank("/foo.html").environ
  >>> app_data[:] = [document, 'text/html']
  >>> print "".join(middleware(environ, start_response))
  <html>
    <head>
      <meta>
      <title>Example page</title>
      <script type="text/javascript"
      src="http://localhost/squeeze/5143af681b9e5f4a8a9a59ab9e52be94c36b6bcc.js"></script>
      <style><!-- @import url(http://localhost/squeeze/fa0c046451639595d3b9b0ee7a85d09c2fcb5080.css); --></style>
    </head>
  </html>

Inspecting the merged file (which has been written to the cache
directory), we see that URLs to background-images have been
rebased. Note that you'll see the stylesheet appearing twice due to
our test requests.

The media for the stylesheets has been taken into account as
well. Squeeze has merged them with the `@media` CSS2 syntax.

  >>> print open(os.path.join(
  ...     cache_dir, 'fa0c046451639595d3b9b0ee7a85d09c2fcb5080.css')).read()
  body { background: url(http://localhost/background.png) repeat-xy; }
  body { background-image: url(http://localhost/background.png) repeat-xy; }
  @media print {
  body { background: url(http://localhost/background.png) repeat-xy; }
  body { background-image: url(http://localhost/background.png) repeat-xy; }
  }
  @media print {
  body { background: url(http://localhost/background.png) repeat-xy; }
  body { background-image: url(http://localhost/background.png) repeat-xy; }
  }
  body { background: url(http://localhost/background.png) repeat-xy; }
  body { background-image: url(http://localhost/background.png) repeat-xy; }

Cache-headers
-------------

The middleware parses cache-headers and tries to do the right thing;
it needs to make sure that documents gets passed through the filter
enough to have an educated guess as to how resources should be
bundled. For this reason, it will try to limit caching of pages that
it does not have a sufficient history on.

When an HTML response document comes in, we need to determine, based
on the value of the vary-header, which resources we can merge.

The middleware maintains separate state with regards to vary-headers.

  >>> app_data[:] = [document, 'text/html', ('vary', 'accept-encoding')]

  >>> environ = {'accept-encoding': 'utf-8'}
  >>> environ = Request.blank("/foo.html", environ=environ).environ
  >>> print "".join(middleware(environ, start_response))
  <html>
    <head>
      <meta>
      <title>Example page</title>
      <script type="text/javascript" src="foo.js"></script>
      <script type="text/javascript" src="bar.js"></script>
      <link href="foo.css" type="text/css">
      <link href="print-foo.css" media="print" type="text/css">
      <link href="print-bar.css" media="print" type="text/css">
      <style><!-- @import url(bar.css); --></style>
    </head>
  </html>

  >>> status, headers = response[-1][:2]
  >>> import webob
  >>> webob.HeaderDict(headers)['cache-control']
  'no-cache'

Documents may not out-live their squeezed resources. Therefore we
truncate the cache lifetime of documents to match the resource with
the earliest expiration date.

Let's serve the resources with a explicit expiration date.

  >>> process_demo_resources(
  ...     middleware, headers=[('expires', 'Mon, 05 Oct 1998 03:30:00 GMT')])

  >>> app_data[:] = [
  ...    document, 'text/html', ('expires', 'Mon, 05 Oct 1999 03:30:00 GMT')]

Running the application, we'll see that document is squeezed.
  
  >>> '5143af681b9e5f4a8a9a59ab9e52be94c36b6bcc' in \
  ...     "".join(middleware(environ, start_response))
  True

But the expiration date is set to the one of the resources.

  >>> status, headers = response[-1][:2]
  >>> webob.HeaderDict(headers)['expires']
  'Mon, 05 Oct 1998 03:30:00 GMT'


