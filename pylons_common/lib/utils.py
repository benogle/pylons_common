import base64
import uuid as uuid_mod
from pylons_common.lib.log import create_logger
logger = create_logger('pylons_common.lib.utils')

class forgiving_dict_accessor(dict):
    """
    Allow accessing a dictionary with dot-notation, returning None if the attribute doesn't exist.
    """
    def __getattr__(self, attr):
        parent = super(self.__class__, self)
        if hasattr(parent, 'get') and callable(parent.get):
            return parent.get(attr)
        else:
            return super(self.__class__, self).__getitem__(attr)

    def __setattr__(self, attr, value):
        super(self.__class__, self).__setitem__(attr, value)

class dict_accessor(dict):
    """
    Allow accessing a dictionary content also using dot-notation.
    """
    def __getattr__(self, attr):
        return super(dict_accessor, self).__getitem__(attr)

    def __setattr__(self, attr, value):
        super(dict_accessor, self).__setitem__(attr, value)

def objectify(d, forgiving=False):
    """
    Return an object version of the dictionary passed in.
    Works recursively.
    """
    if type(d) is dict:
        if forgiving:
            o = forgiving_dict_accessor()
        else:
            o = dict_accessor()
        for key, value in d.iteritems():
            o[str(key)] = objectify(value)
        return o
    elif type(d) is list:
        l = [] 
        for value in d:
            l.append(objectify(value))
        return l
    else:
        return d

def extract(d, keys):
    """
    Creates a new dict that is a subset of d based on passed in keys.
    """
    return dict((k, d[k]) for k in keys if k in d)

def itemize(obj, *attrs):
    """
    pulls attributes from an object and puts them into a dictionary
    """
    return dict([(attr, getattr(obj, attr)) for attr in attrs])

def uuid():
    """
    create a 22 char globally unique identifier
    """
    u = uuid_mod.uuid4()
    b = base64.b32encode(u.bytes)
                     
    b = b[0:22] # lose the "==" that finishes a base64 value
    return b.decode('utf-8')

def pluralize(num, if_many, if_one, if_zero=None):
    """
    returns the proper string based on the number passed.
    
    s = pluralize(1, "sites", "site")
    
    s would be 'site'
    """
    text = if_many
    
    if num == 0 and if_zero:
        text = if_zero
    elif num == 1:
        text = if_one
    
    return text.replace(u'{0}', unicode(num))