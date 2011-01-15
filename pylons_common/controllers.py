from pylons import request, response

import simplejson
from sqlalchemy import sqlalchemy as sa

from pylons_common.lib.exceptions import *
from pylons_common.web.response import ajax, FORMAT_JSON
import time, sys, cgi

from pylons_common.lib.log import create_logger
logger = create_logger('pylons_common.controllers')

__all__ = ['ApiMixin']
# api modules can define ID_PARAM to connect the id request.param to a function
# parameter on the functions in the module. 
ID_CONNECTOR_PARAM = 'ID_PARAM'
REAL_USER_PARAM = 'real_user'

# Map HTTP methods to module functions.
# eg PUT /api/v1/campaign/abc123 calls campaign.create
http_to_functions = {
    'get':    'get',
    'put':    'create',
    'post':   'edit',
    'delete': 'deactivate'
}

class ApiMixin(object):
    """
    Will look for self.
      API_MODULE_BASE
      API_SIGNATURE_BASE
      Session
    """
    ID_CONNECTOR_PARAM = ID_CONNECTOR_PARAM
    REAL_USER_PARAM = REAL_USER_PARAM 

    def log_call(self, real_user, auth_type, version, module, function, request_params, response_code, message, run_time, domain, user_agent):
        logger.info('Ran %s.%s in %d ms' % (module, function, run_time))
    
    def authenticate(self):
        """
        override this!
        """
        return None, None, None

    def prologue(self, real_user, user, version, module, function=None, eid=None, id=None):
        """
        Gather all data necessary to properly execute the target API function.
        If anything fatal occurs here, an ApiPrologueException is thrown,
        which ultimately results in the API call being aborted
        
        """
        # Allow a more RESTful usage, such as DELETE /api/v1/campaign/abc123 HTTP/1.1
        # instead of GET /api/v1/campaign/delete/abc123 HTTP/1.1
        if not function:
            function = request.method.lower()
            function = http_to_functions.get(function)
        
        # Determine requested webservice version
        # All we're expecting is an int in str form, don't need a try/catch here
        # Just test for int
        try:
            version = int(version)
        except ValueError, e:
            raise ApiPrologueException(501, "Invalid version '%s'" % version, INVALID)

        # Find the requested function in the API.  If not found, bail out.
        fn = import_symbol('.'.join([self.API_MODULE_BASE, module]), function)
        
        # Map the id url part to a parameter name in the function. e.g. a function
        # on the ad module might set ID_PARAM = 'ad'. Then the user could specify
        # def edit(blah, ad, blah2=False)
        # And the id field in the url will get passed into the ad parameter.
        id_param = import_symbol('.'.join([self.API_MODULE_BASE, module]), ID_CONNECTOR_PARAM)
        
        try:
            sig = get_sig(version, self.API_SIGNATURE_BASE, module, function)
        except ImportError:
            raise ApiPrologueException(501, "Version %d not implemented yet" % (version), NOT_FOUND)
            
        # Instantiate the shim class, which may contain an 'input' and/or 'output' function
        # to mangle the args to- and return value from- the underlying API method.
        if not (fn and sig):
            raise ApiPrologueException(501, "%s.%s not implemented" % (module, function), NOT_FOUND)

        shim = sig()

        signature = hasattr(fn, 'original_varnames') and fn.original_varnames or fn.func_code.co_varnames
        
        args = {}
        if id_param and id_param in signature and id:
            args[id_param] = id
        
        # args can override
        args.update(dict(request.params.iteritems()))
        
        # Pass in the current user, if that's a valid argument to this function
        # Put the users in here so we dont open a giant security hole.
        if 'user' in signature:
            args.update(user=user)
            #if not user:
            #    raise ApiPrologueException(401, "You need to be logged in to make this call", FORBIDDEN)
        # This is pretty magic...
        if self.REAL_USER_PARAM in signature:
            args[self.REAL_USER_PARAM] = real_user
        
        #redundant, but jam in users:
        shim.user = user
        shim.real_user = real_user

        if hasattr(shim, 'input'):
            args = shim.input(args)
        
        return fn, args, id_param, shim
    
    def epilogue(self, shim, results):
        """
        If the sig defines an output function, transform results with it.
        
        """
        if hasattr(shim, 'output'):
            results = shim.output(results)
        else:
            results = default_return_fn(results)

        return results
    
    @ajax
    def dispatch(self, version, module, function=None, eid=None, id=None):
        
        start_time = time.time()
        
        api_response = None
        response_code = 200
        message = None
        
        params = dict(request.params)
        domain = request.environ.get("X_FORWARDED_FOR", request.environ["REMOTE_ADDR"]) or request.headers.get('Origin')
        real_user = auth_type = api_function = request_params = None
        app_exception = None
        run_time = 0    
        
        try:
            user, real_user, auth_type = self.authenticate()
            
            fn, args, id_param, shim = self.prologue(real_user, user, version, module, function=function, eid=eid, id=id)
            api_function = u'.'.join([fn.__module__, module, fn.__name__])
            
            results = fn(**args)
            api_response = self.epilogue(shim, results)
            
            if args.has_key(id_param):
                params[id_param] = args[id_param]
            
            for k, v in params.items():
                # field storage breaks the api logged json.
                if isinstance(v, cgi.FieldStorage):
                    params[k] = repr(v)
            
            request_params = unicode(simplejson.dumps(params))
            
        except ApiPrologueException, (e):
            # if they specified a wrong version, bad function, etc. Things that arent imlpemented...
            response_code = e.http_response_code
            message = e.msg
            api_response = fail(e.http_response_code, e.msg, e.error_code)
        
        except ApiValueException, (e):
            # At least one value passed to the API couldn't be converted to the expected type.  Communicate this.
            response_code = 500
            message = unicode(simplejson.dumps(e.errors))
            api_response = {'errors': e.errors}
        
        except Exception, (e):
            # MUST rollback any changes. Importante
            self.Session.rollback()
            
            response_code = 500
            message = unicode(e)
            app_exception = e
        
        finally:
            run_time = int((time.time() - start_time) * 1000)
            
            self.log_call(real_user, auth_type,
                          unicode(version), module, function, request_params,
                          response_code, message, run_time, unicode(domain),
                          unicode(request.headers.get('User-Agent')))
            
            logger.info('Committing')
            self.Session.commit()
            
            #reraise any exceptions so that the error middleware can handle them
            if app_exception:
                raise
        
        response.status = response_code
        response.headers['X-Runtime-Ms'] = u'%d' % run_time
        return api_response

##
## Helper functions
##

def default_return_fn(results):
    if hasattr(results, '__class__'):
        klass = results.__class__
        if type(klass) is sa.ext.declarative.DeclarativeMeta:
            if hasattr(klass, 'eid'):
                return {'%s_eid' % klass.__name__.lower() : results.eid}
            elif hasattr(klass, 'id'):
                return {'%s_id' % klass.__name__.lower() : results.id}
    return results

def fail(http_code, message, error_code):
    response.status = http_code
    return {'errors': [{'message': message, 'code': error_code}]}

def get_sig(version, base, module_name, function_name):
    vm_name = 'v%d' % version
    path = '.'.join([base, vm_name])
    vm = __import__(path, fromlist=[vm_name])
    sig = getattr(getattr(vm, module_name, None), function_name, None)
    return sig
    
def import_symbol(module_name, symbol_name):
    logger.debug('Attempting to import %s from %s' % (symbol_name, module_name))
    module = sys.modules.get(module_name)
    if not module:
        try:
            __import__(module_name, level=0)
            logger.debug('Import success')
        except ImportError, e:
            logger.debug('Import FAIL')
            pass
        module = sys.modules.get(module_name)
    return getattr(module, symbol_name, None)


