
import formencode

from formencode import htmlfill
from paste.httpexceptions import HTTPException
import pylons, time
from pylons import tmpl_context as c, request, response
from pylons.templating import render_mako

# our junk
from pylons_common.lib.exceptions import *
from pylons_common.lib.log import create_logger
logger = create_logger('pylons_common.web.response')

from decorator import decorator

FORMAT_JSON = u'json'
FORMAT_CSV = u'csv'

STATUS_SUCCESS   = u'success'
STATUS_FAIL = u'fail'

ERROR_HTTP_STATUS = {
    FORBIDDEN: 403,
    NOT_FOUND: 404
}

MAX_DEBUG_REQUESTS = 200

def htmlfill_error_formatter(error):
    """
    An error formatter to make the errors consistent with the js validate errors.
    """
    from formencode.rewritingparser import html_quote
    return '<div class="error-container"><label class="error">%s</label></div>' % (html_quote(error))

def _jsonify(d):
    import simplejson
    return simplejson.dumps(d)

def format_results(results, format):
    
    if format == FORMAT_JSON:
        content_type = 'text/json'
        formatted_results = _jsonify(results)
    else:
        content_type = 'text/json'
        formatted_results = _jsonify(results)

    # Set HTTP headers, stamp runtime, return
    response.headers['Content-Type'] = content_type + '; charset=utf-8'
    return formatted_results

def ajax(func, *args, **kwargs):
    """
    A decorator to interface with async client requests,
    including returning controller exceptions.
    """
    render_start = time.time()
    
    request.environ['is_async'] = True
    
    # Determine format from param
    format = request.params.get('format')
    format = format in [FORMAT_JSON, FORMAT_CSV] and format or FORMAT_JSON
    
    # Determine format from Accept header, if not specified in the URL
    if format != FORMAT_CSV:
        accept = request.headers.get('Accept','').lower()
        logger.info('Accepting format %s' % accept)
        if FORMAT_JSON in accept:
            format = FORMAT_JSON
    
    user_agent = request.headers.get('User-Agent', '')
    flash_request = 'Adobe Flash Player' in user_agent
    
    def append_client_exception(result, ce):
        if 'errors' not in result: result['errors'] = []
        
        err = {'value': ce.value, 'message': ce.msg, 'code': ce.code}
        if ce.field:
            err['field'] = ce.field
        
        result['errors'].append(err)
    
    # run the function
    try:
        result = func(*args)
        
        if result == True:
            result = {u'status': STATUS_SUCCESS}
        elif result == False:
            result = {u'status': STATUS_FAIL}
        #elif type(result) is dict and not result.has_key('status'):
        #    result[u'status'] = STATUS_SUCCESS
        else:
            result = {
                u'results': result
            }
        
        if flash_request:
            result['status'] = STATUS_SUCCESS
    
    except formencode.validators.Invalid, (e):
        # Keep the response status at 200 for Flash requests, otherwise the client wont see
        # any useful error information        
        if not flash_request:
            response.status = 400
            # Setting this key in the environ disables the error middleware that might otherwise
            # clobber our error structure with a glossy error webpage.
            pylons.request.environ['pylons.status_code_redirect'] = True
        else:
            result['status'] = STATUS_FAIL
        
        result = {}
        
        errs = e.error_dict
        error_list = []
        for field in errs.keys():
            if isinstance(errs[field], formencode.validators.Invalid):
                error_list.append({'value': errs[field].value, 'message': errs[field].msg, 'field': field})
            else:
                error_list.append({'value': None, 'message': errs[field], 'field': field})
            
        result['errors'] = error_list
    
    except HTTPException, (e):
        result = {}
        if e.code in [404, 403]:
            response.status = e.code
            result['errors'] = [{'message': 'Not found (404): %s' % (e.detail), 'code': e.code}]
        else:
            raise
        
    except ClientException, (e):
        # some of the error codes correspond to different HTTP statuses.
        # i.e. errors.NOT_FOUND -> 404
        
        # Keep the response status at 200 for Flash requests, otherwise the client wont see
        # any useful error information
        if not flash_request: 
            response.status = ERROR_HTTP_STATUS.get(e.code, 400)
            # Setting this key in the environ disables the error middleware that might otherwise
            # clobber our error structure with a glossy error webpage.
            pylons.request.environ['pylons.status_code_redirect'] = True
        else:
            result['status'] = STATUS_FAIL
        
        result = {}
        
        append_client_exception(result, e)
    
    except CompoundException, (e):
        # some of the error codes correspond to different HTTP statuses.
        # i.e. errors.NOT_FOUND -> 404
        
        # Keep the response status at 200 for Flash requests, otherwise the client wont see
        # any useful error information
        if not flash_request:
            response.status = 400
            # Setting this key in the environ disables the error middleware that might otherwise
            # clobber our error structure with a glossy error webpage.
            pylons.request.environ['pylons.status_code_redirect'] = True
        else:
            result['status'] = STATUS_FAIL
        
        result = {}
        
        if not e.has_exceptions:
            result['errors'] = [{'message': 'Unknown Error :(', 'code': UNSET}]
        else:
            for ce in e.exceptions:
                append_client_exception(result, ce)
    
    # queries for the query analyzer. Their base controller must set this...
    
    requested_url = request.environ.get('PATH_INFO')
    if request.environ.get('QUERY_STRING'):
        requested_url += '?' + request.environ['QUERY_STRING']
    
    debug = request.environ.get('show_debug', False)
    if debug and c.queries:
        length = len(c.queries)
        queries = sorted(c.queries, key=lambda x: -x[1])
        result['debug'] = {
            'queries': length,
            'query_time': c.query_time or 0,
            'total_time': time.time() - render_start,
            'requested_url': requested_url,
            'query_data': [{'query': q, 'time': t} for q, t in queries[:MAX_DEBUG_REQUESTS]]
        }
        logger.info('ASYNC queries: %s; qtime: %.3fsec; total time: %.3fsec' % (result['debug']['queries'], result['debug']['query_time'], result['debug']['total_time']))
        
    return format_results(result, format)
async = decorator(async)

def dispatch_on(**method_map):
    """Dispatches to alternate controller methods based on HTTP method

    Multiple keyword arguments should be passed, with the keyword
    corresponding to the HTTP method to dispatch on (DELETE, POST, GET,
    etc.) and the value being the function to call. The value should be
    a string indicating the name of the function to dispatch to.

    Example:

    .. code-block:: python

        from pylons.decorators import rest

        class SomeController(BaseController):

            @dispatch_on(POST='create_comment')
            def comment(self):
                # Do something with the comment

            def create_comment(self, id):
                # Do something if its a post to comment
    
    THIS IS A COPY OF THE PYLONS VERSION. Theirs has a bug. I fixed it.
    """
    
    from pylons.decorators.util import get_pylons
    def dispatcher(func, self, *args, **kwargs):
        """Wrapper for dispatch_on"""
        alt_method = method_map.get(get_pylons(args).request.method)
        if alt_method:
            alt_method = getattr(self, alt_method)
            logger.debug("Dispatching to %s instead", alt_method)
            return self._inspect_call(alt_method)
        return func(self, *args, **kwargs)
    return decorator(dispatcher)

def mixed_response(sync_error_action=None, prefix_error=False,
                   auto_error_formatter=htmlfill_error_formatter, **htmlfill_kwargs):
    """
    Use this on the submit handler action. Used in conjunction with dispatch_on:
    
    class SomeController(BaseController):

        @dispatch_on(POST='create_comment')
        def comment(self):
            # Do something with the comment
        
        @mixed_response('comment')
        def create_comment(self, id):
            # Do something if its a post to comment
    
    much of this is lifted from the @validate decorator
    """
    def dec(fn):
        
        sea = sync_error_action or fn.__name__
        
        def new(self, *args, **kwargs):
            
            accept = request.headers.get('Accept','').lower()
            was_xhr = request.headers.get('X-Requested-With','').lower() == 'xmlhttprequest'
            
            self.is_async = was_xhr or 'text/html' not in accept
            
            logger.debug('Figuring out type of request. Accept header: "%s"; Was xhr? %s. Is async? %s' % (accept, was_xhr, self.is_async))
            
            params = request.params
            
            if self.is_async:
                @ajax
                def run_async():
                    return fn(self, *args, **kwargs)
                return run_async()
            
            else:
                errs = {}
                
                def append_client_exception(ce):
                    if ce.field:
                        errs[ce.field] = ce.msg
                    else:
                        errs['_general'] = ce.msg
                    
                try:
                    val = fn(self, *args, **kwargs)
                    
                    # if result is a dictionary with a url specified, redirect there.
                    if isinstance(val, dict) and 'url' in val:
                        from pylons.controllers.util import redirect
                        return redirect(val['url'])
                    return val
                
                except formencode.Invalid, e:
                    errs = e.unpack_errors(False, '.', '-')
                except ClientException, e:
                    append_client_exception(e)
                except CompoundException, e:
                    for ce in e.exceptions:
                        append_client_exception(e.exceptions)
                
                if errs:
                    request.environ['REQUEST_METHOD'] = 'GET'
                    
                    self._py_object.tmpl_context.form_errors = errs
        
                    request.environ['pylons.routes_dict']['action'] = sea
                    response = self._dispatch_call()
        
                    htmlfill_kwargs2 = htmlfill_kwargs.copy()
                    htmlfill_kwargs2.setdefault('encoding', request.charset)
                    htmlfill_kwargs2.setdefault('prefix_error', prefix_error)
                    htmlfill_kwargs2.setdefault('auto_error_formatter', auto_error_formatter)
                    
                    return htmlfill.render(response, defaults=params, errors=errs,
                                           **htmlfill_kwargs2)
        return new
    return dec

def render_response(*args, **kw):
    """
    override pylons render_response so that we can supply
        defaults to a form using htmlfill. form_defaults can
        either be passed in as part of the keyword dict or
        on the c variable (ie, c.form_defaults = dict(...))
    """
    form_defaults = kw.pop('form_defaults', False)
    # the prepare_form method puts the defaults on c.form_defaults
    if not form_defaults and c.form_defaults:
        form_defaults = c.form_defaults
        
    content = render_mako(*args, **kw)
    
    def formatter_that_doesnt_suck(error):
        return 'no suckage'
    
    # pylons does htmlfill.render on pages that have errors, so don't do it here (pylons.decorators.__init__.py line 183)
    if not c.form_errors:
        if form_defaults:
            content = htmlfill.render(content, defaults=form_defaults, encoding="utf-8")
    return content