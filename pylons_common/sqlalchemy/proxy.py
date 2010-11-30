import pylons
import time
from sqlalchemy.interfaces import ConnectionProxy

class _fake_context(object):
    pass
class TimerProxy(ConnectionProxy):
    def __init__(self, *args, **kw):
        super(TimerProxy, self).__init__(*args, **kw)
        print 'TimeProxy init %s' % self 
    
    def cursor_execute(self, execute, cursor, statement, parameters, context, executemany):
        
        #TODO: figure out cleanest way to pass vars in and out of this. Context prolly not it.
        try:
            c = pylons.tmpl_context
            show_debug = c.show_debug
            c.queries
            c.query_time
        except TypeError:
            c = _fake_context()
            show_debug = False
            c.queries = None
            c.query_time = ''

        if not show_debug:
            return super(TimerProxy, self).cursor_execute(execute, cursor, statement, parameters, context, executemany)

        now = time.time()
        try:
            if not c.queries:
                c.queries = []

            q_params = parameters
            if not executemany:
                q_params = [parameters]

            def decode_params(d):
                for key in d:
                    val = d[key]
                    if isinstance(val, str):
                        d[key] = val.decode('utf-8', 'replace')
                return d

            for params in q_params:
                if params is not None:
                    quoted_params = dict((param, quote(val)) for param, val in params.iteritems())
                    st = [statement.decode('utf-8', 'replace') % decode_params(quoted_params), 0]
                else:
                    st = [statement.decode('utf-8', 'replace'), 0]
                c.queries.append(st)

            r = execute(cursor, statement, parameters, context)
        except Exception, e:
           raise e
        
        else:
            if c.query_time == '':
                c.query_time = 0
            c.query_time += time.time() - now
        
            partial_time = (time.time() - now)/len(q_params)
            for i in range(len(q_params)):
                c.queries[-(i+1)][1] = partial_time
        
        return r

def quote(p):
    return quoters.get(type(p), defaultq)(p)

quoters = {
    bool: lambda s: 'true' if s else 'false',
    int: str,
    float: str,
    long: str,
    str: lambda s: "'%s'" % (s,),
    unicode: lambda s: u"'%s'" % (s,),
    list: lambda s: "(" + ",".join(quote(e) for e in s) + ")"
}

def defaultq(p):
    return u"'%s'" % (unicode(p))