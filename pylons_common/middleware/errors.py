import pylons, sys
from weberror import errormiddleware, collector, reporter
from weberror.evalexception import EvalException, get_debug_count, DebugInfo
from weberror.errormiddleware import ErrorMiddleware, handle_exception
from pylons.middleware import head_html, footer_html, media_path, report_libs
from pylons.error import template_error_formatters
from webob import Request, Response
import simplejson as json
import traceback

import smtplib
from socket import sslerror #if desired

from paste import fileapp, registry

from pylons_common.lib import exceptions
from pylons_common.lib.log import create_logger
logger = create_logger('pylons_common.middleware.errors')

"""
Whats going here? This is Error middleware.

We have a VanillaErrorMiddleware, DebugErrorMiddleware and VariableErrorHandler.

- VanillaErrorMiddleware is a weberror.errormiddleware.ErrorMiddleware
  - Its __call__ method will be run on requests from non-admins or when not in production
  - It is extended so we can call handle_async_exception() on async requests.
  
- DebugErrorMiddleware is a weberror.evalexception.EvalException
  - It provides more information for debug purposes.
  - __call__ method (and in turn our overriden respond() method) called on requests from
    admins or when in dev.
  - Extended so we can handle errors properly on async requests.

Our app's entry point make_app() will create a VariableErrorHandler. VariableErrorHandler
will create a VanillaErrorMiddleware and a DebugErrorMiddleware. Then, depending on the request
it will call one or the other. For non-engineer requests on production, VanillaErrorMiddleware
is called. All other requests go through the debug middleware.

VariableErrorHandler also creates an weberror.reporter.EmailReporter which is what emails us
any errors 'WebApps'. Both the VanillaErrorMiddleware and the DebugErrorMiddleware use this
EmailReporter.

The chosen middleware object's (a VanillaErrorMiddleware or DebugErrorMiddleware) __call__
method is called on every request regardless if there is an error or not.

The middleware knows if the request is async or not via environ['is_async'] which is set by the
response.ajax decorator. Because it is set by the response.ajax decorator, we dont know if
the response is supposed to be async until _after_ the request's controller.action
method is called. That is why I check is_async right before I return the exception's resopnse.
"""

def handle_async_exception(exc_info, environ, debug_info=None):
    """
    This will generate json for exceptions. If the middleware object specifies debug_info,
    the client will get more info like where in what file the exception happened.
    
    DebugErrorMiddleware will specify debug_info
    """
    type, exception, trace = exc_info
    
    result = {
        'status': 'fail',
        'errors': [{
            'message': debug_info and str(exception) or 'Internal Server Error',
            'code': exceptions.FAIL
        }]
    }
    
    if debug_info:
        # get bottom of the trace for the location that raised the error.
        last_trace = trace
        while last_trace.tb_next:
            last_trace = last_trace.tb_next
        
        result['debug'] = {
            'message': str(exception),
            'url': debug_info.view_uri,
            'file': last_trace.tb_frame.f_code.co_filename,
            'line': last_trace.tb_lineno,
            'exception_type': str(type),
            'trace': traceback.format_tb(trace)
        }
    
    return json.dumps(result)

class VanillaErrorMiddleware(ErrorMiddleware):
    def __call__(self, environ, start_response):
        """
        This is straight copied from the original ErrorMiddleware code. Unfortunately they
        didnt separate out the actual exception handling into a function, so I must override...
        
        basically just adds the handle_async_exception() call
        """
        # We want to be careful about not sending headers twice,
        # and the content type that the app has committed to (if there
        # is an exception in the iterator body of the response)
        if environ.get('paste.throw_errors'):
            return self.application(environ, start_response)
        environ['paste.throw_errors'] = True

        try:
            __traceback_supplement__ = errormiddleware.Supplement, self, environ
            sr_checker = errormiddleware.ResponseStartChecker(start_response)
            app_iter = self.application(environ, sr_checker)
            return self.make_catching_iter(app_iter, environ, sr_checker)
        except:
            exc_info = sys.exc_info()
            try:
                
                #is_async is set by the @ajax decorator
                if environ.get('is_async', None):
                    start_response('500 Internal Server Error',
                               [('content-type', 'application/json; charset=utf8')],
                               exc_info)
                    response = handle_async_exception(exc_info, environ)
                else:
                    start_response('500 Internal Server Error',
                               [('content-type', 'text/html; charset=utf8')],
                               exc_info)
                    # @@: it would be nice to deal with bad content types here
                    response = self.exception_handler(exc_info, environ)
                
                if isinstance(response, unicode):
                    response = response.encode('utf8')
                return [response]
            finally:
                # clean up locals...
                exc_info = None

class DebugErrorMiddleware(EvalException):
    
    def respond(self, environ, start_response):
        """
        This is straight copied from the original ErrorMiddleware code. Unfortunately they
        didnt separate out the actual exception handling into a function, so I must override...
        
        basically just adds the handle_async_exception() call
        """
        req = Request(environ)
        if req.environ.get('paste.throw_errors'):
            return self.application(environ, start_response)
        base_path = req.application_url + '/_debug'
        req.environ['paste.throw_errors'] = True
        started = []
        
        def detect_start_response(status, headers, exc_info=None):
            try:
                return start_response(status, headers, exc_info)
            except:
                raise
            else:
                started.append(True)
        try:
            __traceback_supplement__ = errormiddleware.Supplement, self, environ
            app_iter = self.application(environ, detect_start_response)
            
            # Don't create a list from a paste.fileapp object 
            if isinstance(app_iter, fileapp._FileIter): 
                return app_iter
            
            try:
                return_iter = list(app_iter)
                return return_iter
            finally:
                if hasattr(app_iter, 'close'):
                    app_iter.close()
        except:
            exc_info = sys.exc_info()
            
            is_async = environ.get('is_async', None) == True
            content_type = is_async and 'application/json' or 'text/html'
            
            # Tell the Registry to save its StackedObjectProxies current state
            # for later restoration
            registry.restorer.save_registry_state(environ)

            count = get_debug_count(environ)
            view_uri = self.make_view_url(environ, base_path, count)
            if not started:
                headers = [('content-type', content_type)]
                headers.append(('X-Debug-URL', view_uri))
                start_response('500 Internal Server Error',
                               headers,
                               exc_info)
            
            environ['wsgi.errors'].write('Debug at: %s\n' % view_uri)

            exc_data = collector.collect_exception(*exc_info)
            exc_data.view_url = view_uri
            if self.reporters:
                for reporter in self.reporters:
                    reporter.report(exc_data)
            
            debug_info = DebugInfo(count, exc_info, exc_data, base_path,
                                   environ, view_uri, self.error_template,
                                   self.templating_formatters, self.head_html,
                                   self.footer_html, self.libraries)
            assert count not in self.debug_infos
            self.debug_infos[count] = debug_info

            if is_async:
                return [handle_async_exception(exc_info, environ, debug_info=debug_info)]
            
            # @@: it would be nice to deal with bad content types here
            return debug_info.content()
    
class VariableErrorHandler(object):
    """
    This handler is basically a copy of pylons.middleware.ErrorHandler, but with a runtime
    switch instead of a init-time one.  It wraps the app in both DebugErrorMiddleware
    (admin errors) and VanillaErrorMiddleware (unprivileged user "glossy" errors), and passes
    control to one or the other on a per-request basis, depending on phase (dev, staging,
    prod) and privilege level (admin or not).

    Note that this middleware only works if instantiated before (ergo runs after) SessionHandler,
    because it relies on the session introduced by that layer of middleware.

    This requires a change from the default pylons middleware stack, and means that errors
    encountered in middleware traditionally installed above the ErrorHandler (SessionMiddleware,
    CacheMiddleware) will NOT be handled by it in this setup.
    """
    def __init__(self, app, global_conf, **errorware):
        """
        Lifted verbatim from ErrorHandler, but unconditionally instantiating
        both types of error handlers, and setting them on self.
        """
        if 'error_template' in errorware:
            del errorware['error_template']
            warnings.warn(pylons.legacy.error_template_warning,
                          DeprecationWarning, 2)
        
        # Pylons is messy. errorware is from pylons.config['pylons.errorware'].
        # When debug in the ini file is False, Pylons config will read from the ini the smtp
        # auth, the error to address ('email_to'), and the error from address ('error_email_from').
        #
        # In debug, errorware will only have errorware['debug']=True. This is important as the
        # code in ErrorMiddleware will try to populate the to address and the error from address 
        # when they dont exist with values from global_conf (NOT app_conf!). But the obscenely
        # confusing part is that ErrorMiddleware uses DIFFERENT keys for these email addresses
        # than the pylons.config module! F. Bottom line: ignore the __init__ in ErrorMiddleware.
        # All our error config happens in pylons.config and is passed in via errorware.
        reporters = self.get_reporters(errorware)
        
        # This should suppress the auto email in VanillaErrorMiddleware
        # We need to do this so cause we have our own in reporters above.
        errorware['error_email'] = '' 
        
        footer = footer_html % (pylons.config.get('traceback_host', 
                                                  'pylonshq.com'),
                                pylons.__version__)
        py_media = dict(pylons=media_path)
        self.admin_error_app = DebugErrorMiddleware(app, global_conf=global_conf, 
                            templating_formatters=template_error_formatters,
                            media_paths=py_media, head_html=head_html, 
                            footer_html=footer,
                            libraries=report_libs, reporters=reporters)
        self.glossy_error_app = VanillaErrorMiddleware(app, global_conf, reporters=reporters, **errorware)
    
    def get_reporters(self, errorware):
        """
        Both middleware objects support the concept of 'reporters'. This will create the
        email reporter that will send up webapp emails.
        """
        from paste.util import converters
        
        error_email = errorware.get('error_email')
        error_email = converters.aslist(error_email)
        
        from_address = errorware.get('from_address')
        
        smtp_server = errorware.get('smtp_server', 'localhost')
        smtp_username = errorware.get('smtp_username')
        smtp_password = errorware.get('smtp_password')
        smtp_port= errorware.get('smtp_port')
        smtp_use_tls = converters.asbool(errorware.get('smtp_use_tls'))
        subject_prefix = errorware.get('error_subject_prefix')
        
        class ComEmailReporter(reporter.EmailReporter):
            #TODO: using smtp_port from outside. Ghetto.
            def report(self, exc_data):
                logger.info('Emailed about error %s' % exc_data)
                msg = self.assemble_email(exc_data)
                if smtp_port:
                    server = smtplib.SMTP(self.smtp_server, smtp_port)
                else:
                    server = smtplib.SMTP(self.smtp_server)
                if self.smtp_use_tls:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                if self.smtp_username and self.smtp_password:
                    server.login(self.smtp_username, self.smtp_password)
                ## FIXME: this should check the return value from this function:
                result = server.sendmail(self.from_address,
                                self.to_addresses, msg.as_string())
                try:
                    server.quit()
                except sslerror:
                    # sslerror is raised in tls connections on closing sometimes
                    pass
        
        # emails will not be sent in dev. 
        if error_email:
            return [ComEmailReporter(
                to_addresses=error_email,
                from_address=from_address,
                smtp_server=smtp_server,
                smtp_username=smtp_username,
                smtp_password=smtp_password,
                smtp_use_tls=smtp_use_tls,
                subject_prefix=subject_prefix)]
        
        return []
    
    def __call__(self, environ, start_response):
        """
        Select error handler based on app-specific variables.
        Note that this method wraps the core application and gets called on
        EVERY REQUEST, whether or not an exception is thrown.  It simply
        chooses which piece of middleware gets this request next, and it's up
        to that middleware to try/except and handle errors if they occur.
        """
        session = environ.get('beaker.session')
        show_debug = bool(session and session.get('show_debug') or False)
        
        # Only show glossy (unhelpful) errors to non-admins on production or staging.
        # Admins always see admin errors (full stack trace, debug tools, etc),
        # as does anyone on non-production phases (staging, dev).
        #
        # Note, glossy_error_app doesnt just show the glossy error. In fact it shows no
        # error. It handles only logging of the errors (emailing us). The actual unhelpful error
        # is shown by the StatusCodeRedirect middleware which redirects to our error.py
        # controller's document action. -bogle
        if not show_debug:
            return self.glossy_error_app(environ, start_response)
        else:
            # Set redirect control key to False in this call's environ so engineers don't
            # get meaningless glossy errors. pylons.middleware.StatusCodeRedirect uses this
            # for a cutout.
            environ['pylons.status_code_redirect'] = False
            return self.admin_error_app(environ, start_response)
