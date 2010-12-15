# Custom exception base
class AppException(Exception):
    """
    General purpose error.
    
    These will be caught by middleware and will result in 500 errors to the client.
    """
    def __init__(self, msg, code=None, field=None, value=None):
        self.msg = msg
        self.code = code
        self.field = field
        self.value = value

    def __str__(self):
        return '%s: %s (%s)' % (self.__class__.__name__, self.msg, self.code)

##
## Custom Exceptions
##

class ClientException(AppException):
    """
    Use ClientException when you have an error that the client should see. If it makes it
    through the entire pylons stack, ajax will handle the exception and return a
    status code in the 400 range based on ClientException.code. i.e. NOT_FOUND -> 404 etc
    """
    pass

class CompoundException(AppException):
    """
    Use this when you want to throw more than one ClientException. ajax will properly
    handle this thing.
    """
    def __init__(self, msg, code=None):
        super(CompoundException, self).__init__(msg, code)
        self.exceptions = []
    
    def add(self, exception):
        self.exceptions.append(exception)
    
    @property
    def has_exceptions(self):
        return len(self.exceptions) > 0
    
    def __str__(self):
        return '%s: %s (%s) (%s)' % (self.__repr__(), self.msg, self.code, [str(e) for e in self.exceptions])

class ApiPrologueException(Exception):
    def __init__(self, http_response_code, msg, error_code=None):
        self.http_response_code = http_response_code
        self.msg = msg
        self.error_code = error_code
        
    def __str__(self):
        return 'str'

class ApiValueException(Exception):
    """
    Used in the enforce decorator to deal with type coercion issues.
    """
    def __init__(self, errors, code=None):
        self.errors = errors
        self.code = code
    
    def __str__(self):
        return 'ApiValueException(%s: %s)' % (self.code, self.errors)
    def __repr__(self):
        return str(self)
    
##
## Error codes
##

INVALID     = 1
MISMATCH    = 2
NO_DEFAULT  = 4
FAIL        = 8
NOT_FOUND   = 16
UNSET       = 32
INCOMPLETE  = 64
EXTERNAL    = 128
DUPLICATE   = 256
FORBIDDEN   = 512
