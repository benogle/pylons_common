from pylons_common.lib.exceptions import *

from pylons_common.lib.date import convert_date

from pylons_common.lib.log import create_logger
logger = create_logger('pylons_common.lib.decorators')

__all__ = ['zipargs', 'stackable', 'enforce']

def zipargs(decorated_fn):
    """
    This will zip up the positional args into kwargs. This makes handling them in
    decorators easier. Call on the inner deocrator function, and pass in the outer's
    arg. Outer function must be @stackable. Convolution. Apologies.
    """
    def decorator(fn):
        def new(*args, **kwargs):
            
            # Get the original func's param names. If this is the outer decorator, decorated_fn.func_code.co_varnames
            # will have the inner decorator's names ('args', 'kwargs'). The inner decorator should
            # attach original_varnames to the function
            varnames = hasattr(decorated_fn, 'original_varnames') and decorated_fn.original_varnames or decorated_fn.func_code.co_varnames
            
            dargs = dict(zip(varnames, args))
            dargs.update(kwargs)
            
            return fn(**dargs)
        
        return new
    
    return decorator

def stackable(fn):
    """
    This will make a decorator 'stackable' in that we can get the original function's params.
    """
    def new(*args, **kwargs):
        
        decorated_fn = args[0]
        newfn = fn(*args, **kwargs)
        if decorated_fn:
            # We need to pass the original_varnames into every fn we return in these decorators so
            # the dispatch controller has access to the original function's arg names.
            # Do this in @auth due to decorator stacking.
            newfn.func_name = decorated_fn.func_name
            newfn.original_varnames = hasattr(decorated_fn, 'original_varnames') and decorated_fn.original_varnames or decorated_fn.func_code.co_varnames
        return newfn
    
    return new

##
### Decorators for api functions
##

def enforce(Session, **types):
    """
    Assumes all arguments are unicode strings, and converts or resolves them to more complex objects.
    If a type of the form [Type] is specified, the arguments will be interpreted as a comma-delimited
    list of strings that will be converted to a list of complex objects. 
    """
    
    from datetime import datetime
    
    @stackable
    def decorator(fn):
        
        @zipargs(fn)
        def new(**kwargs):
            from sqlalchemy.ext import declarative

            errors = []
            
            def convert(arg_name, arg_type, arg_value):
                converted_value = arg_value
                try:
                    if arg_type is file:
                        if type(arg_value) is not file:
                            if hasattr(arg_value, 'file'):
                                converted_value = arg_value.file
                            else:
                                raise ValueError("Value must be an open file object, or uploaded file.")
                    if arg_type == 'filedict':
                        if type(arg_value) is not dict:
                            if hasattr(arg_value, 'file'):
                                converted_value = {'file': arg_value.file}
                            else:
                                raise ValueError("Value must be an open file object, or uploaded file.")
                            
                            if hasattr(arg_value, 'filename'):
                                converted_value['filename'] = arg_value.filename
                    elif arg_type is int:
                        converted_value = int(arg_value)
                    elif arg_type is float:
                        converted_value = float(arg_value)
                    elif arg_type is datetime:
                        converted_value = convert_date(arg_value)
                    elif type(arg_type) is declarative.DeclarativeMeta:
                        if type(type(arg_value)) is not declarative.DeclarativeMeta:
                            
                            is_int = True
                            try:
                                arg_value = int(arg_value)
                            except ValueError, e:
                                is_int = False
                            
                            if not is_int and hasattr(arg_type, 'eid'):
                                field = arg_type.eid
                                if arg_value is str:
                                    arg_value = arg_value.decode('utf-8')
                                else:
                                    arg_value = unicode(arg_value)
                            else:
                                field = arg_type.id
                                arg_value = int(arg_value)
                            converted_value = Session.query(arg_type).filter(field == arg_value).first() 
                    elif arg_type is str:
                        if type(arg_value) is unicode:
                            converted_value = arg_value.encode('utf-8')
                        else:
                            converted_value = str(arg_value)
                    elif arg_type is unicode:
                        if type(arg_value) is str:
                            converted_value = arg_value.decode('utf-8')
                        else:
                            converted_value = unicode(arg_value)
                    elif arg_type is bool:
                        if type(arg_value) is not bool:
                            arg_value = arg_value.encode('utf-8').lower()
                            if arg_value in ['t','true','1','y','yes','on']:
                                converted_value = True
                            elif arg_value in ['f','false','0','n','no']:
                                converted_value = False
                            else:
                                raise ValueError('Value must be true or false')
                except (ValueError, TypeError), e:
                    errors.append((e, arg_name, arg_value))
                
                return converted_value

            for name, value in kwargs.iteritems():
                if name in types and value is not None:             
                    t = types[name]
                    if type(type(value)) is declarative.DeclarativeMeta or isinstance(value, list):
                        kwargs[name] = convert(name, t, value)
                    # If the type is a list, this means that we want to 
                    # return a list of objects of the type at index 0 in the list                        
                    elif isinstance(t, list):
                        if not isinstance(value, list):
                            list_of_values = [s for s in value.split(',') if s]
                            converted_values = []
                            t = t[0]
                            for v in list_of_values:
                                converted_values.append(convert(name, t, v))
                        # If the value was already a list, then it must have
                        # been a list of DB objects, so we didn't need to touch it                       
                        kwargs[name] = converted_values
                    else:
                        kwargs[name] = convert(name, t, value)
            if errors:
                raise ApiValueException([{'value': str(e[2]), 'message':str(e[0]), 'field': e[1]} for e in errors], INVALID)
            else:
                return fn(**kwargs)
            
        return new
    return decorator