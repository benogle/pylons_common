from pylons_common.lib.log import create_logger
logger = create_logger('pylons_common.web.validation')

from pylons_common.lib.utils import objectify

def validate(validation_class, fill_out_args=False, allow_extra_fields=True, **kwargs):
    
    args = kwargs
    if fill_out_args:
        
        def get_val(kw, f):
            if f in kwargs: return kwargs[f]
            return ''
        
        args = dict([(f, get_val(kwargs, f)) for f in validation_class.fields.keys()])
    
    params = validation_class(allow_extra_fields=allow_extra_fields).to_python(args)
    
    params = dict([(k, params[k]) for k in params.keys() if k in kwargs and validation_class.fields])
    
    return objectify(params)