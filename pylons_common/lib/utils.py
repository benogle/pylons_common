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