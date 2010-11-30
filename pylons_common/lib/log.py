import logging
import inspect
import pylons
import os

"""
generally, to log from a module, you should do the following:

    from pylons_common.lib.log import logger

then to log, call:

    logger.debug("blah")
    logger.info("blah")
    logger.warning("blah")
    logger.exception("blah")
"""

logger = None

def log(log_obj, level, message, **kwargs):
    """
    Log to logger.info with a special context prefix that includes:
    - First 10 characters of the session id, if available (else '-' * 10)
    - Caller class name, if the caller was a class method, or the last atom of the module name.
    - The function/method name of the caller

    :param message: Message to send to the logs, after context prefix
    """
    frame = inspect.currentframe().f_back.f_back
    fn_name = frame.f_code.co_name
    # Any variable called 'self' in the local scope of the frame is probably an instance
    instance = frame.f_locals.get('self')
    class_name = instance and hasattr(instance, '__class__') and instance.__class__.__name__
    # If we can't find a suitable 'self' var, this might be a static classmethod, in which case
    # the first arg would be a reference to the class definition.
    if not class_name:
        first_arg_name = frame.f_code.co_varnames and frame.f_code.co_varnames[0] or ''
        first_arg = frame.f_locals.get(first_arg_name)
        if first_arg and inspect.isclass(first_arg):
            class_name = first_arg.__name__
    # If we can't resolve a class at all (either instantiated or static), use the module name.
    if not class_name:
        module = frame.f_globals['__name__']
        module = module.rsplit('.')[-1]

    # Get the first 10 characters of the pylons session ID, if available.
    sid = hasattr(pylons.session, 'id') and pylons.session.id or '-' * 32
    sid = sid[0:10]

    prefix = '%s %s.%s: ' % (sid, class_name or module, fn_name)

    ## Alternate context prefix
    #filename = frame.f_code.co_filename
    #filename = '/'.join(filename.split(os.sep)[-3:])
    #prefix = '%s %04d %s: ' % (sid, line_number, filename)

    del frame

    if isinstance(message, unicode):
        message = message.encode('utf-8')
    elif isinstance(message, str):
        pass
    elif hasattr(message, '__repr__'):
        message = message.__repr__()
    else:
        message = str(message)

    return getattr(log_obj, 'original_'+level)(prefix+message, **kwargs)

def create_logger(name):
    """
    allow other processes to override the default logger. 
    """
    l = logging.getLogger(name)

    def log_level(log_obj, level):
        return lambda message, **kwargs: log(log_obj, level, message, **kwargs)

    # Replace each requested level method (ie logger.[level]()) with
    # our own prefix-adding function.  Requires some hairy closures.
    for level in ['info','warn','warning','error']:
        lvl = '%s' % level
        setattr(l, 'original_'+level, getattr(l, level))
        setattr(l, level, log_level(l, level))

    return l

def set_default_logger(name):
    """
    allow other processes to override the default logger. 
    """
    global logger
    logger = create_logger(name)
    return logger
