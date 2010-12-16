
from pylons_common.lib.log import create_logger
logger = create_logger('pylons_common.lib.datetime')
from datetime import datetime, timedelta

DATE_FORMAT_ACCEPT = [u'%Y-%m-%d %H:%M:%S', u'%Y-%m-%d', u'%m-%d-%Y', u'%m/%d/%Y', u'%m.%d.%Y', u'%b %d, %Y']

popular_timezones = [u'US/Eastern', u'US/Central', u'US/Mountain', u'US/Pacific', u'US/Alaska', u'US/Hawaii', u'US/Samoa',
                     u'Europe/London', u'Europe/Paris', u'Europe/Istanbul', u'Europe/Moscow',
                     u'America/Puerto_Rico', u'America/Buenos_Aires', u'America/Sao_Paulo',
                     u'Asia/Dubai', u'Asia/Calcutta', u'Asia/Rangoon', u'Asia/Bangkok', u'Asia/Hong_Kong', u'Asia/Tokyo',
                     u'Australia/Brisbane', u'Australia/Sydney',
                     u'Pacific/Fiji']

def convert_date(value):
    """
    converts a string into a datetime object
    """
    
    if not value:
        return None
    
    if isinstance(value, datetime):
        return value
    
    def try_parse(val, format):
        try:
            dt = datetime.strptime(val, format)
        except ValueError:
            dt = None
        return dt
    
    converted_value = None
    for format in DATE_FORMAT_ACCEPT:
        converted_value = converted_value or try_parse(value, format)
    if not converted_value:
        raise ValueError('Cannot convert supposed date %s' % value)
    
    return converted_value

def get_timezones():
    import pytz
    
    timezones = {0:u'UTC'}
    for tzname in pytz.common_timezones:
        tzname = tzname.decode('utf-8')
        tz = pytz.timezone(tzname)
        
        dt = datetime.utcnow()

        # in theory, this is more elegant, but tz.dst (timezone daylight savings - 0 if off 1 if on) is returning 0 for everything
        #offset = tz.utcoffset(dt) - tz.dst(dt)

        # we do this try/except to avoid the possibility that pytz fails at localization
        # see https://bugs.launchpad.net/pytz/+bug/207500
        try:
            offset = dt.replace(tzinfo=pytz.utc) - tz.localize(dt)
            seconds = offset.days * 86400 + offset.seconds
            minutes = seconds / 60
            hours = minutes / 60
    
            # adjust for offsets that are greater than 12 hours (these are repeats of other offsets)
            if hours > 12:
                hours = hours - 24
            elif hours < -11:
                hours = hours + 24
            
            this_tz = timezones.get(hours, None)
            if not this_tz:
                timezones[hours] = tzname
            elif tzname in popular_timezones:
                # overwrite timezones with popular ones if equivalent
                timezones[hours] = tzname
        except:
            logger.exception("Localization failure for timezone " + tzname)

    return timezones

def relative_date_str(date, now=None, time=False): 
    '''
    Will return a string like 'Today', 'Tomorrow' etc.
    '''
    if not now:	now = datetime.utcnow()
    
    if not date: return 'unknown'

    diff = date.date() - now.date()

    def day_time(day_str):
        return '%s%s' % (day_str, time and ' at %s' % date.strftime("%I:%M %p") or '')
    
    if diff.days == 0:
        return day_time('Today')
    elif diff.days == -1:
        return day_time('Yesterday')
    elif diff.days == 1:
        return day_time('Tomorrow')
    
    elif diff.days < 0 and diff.days >= -7:#Within one week back
        return '%s ago' % pluralize(-diff.days, '{0} days', '1 day')
    elif diff.days > 0 and diff.days < 7:#Within one week back
        return 'in %s' % pluralize(diff.days, '{0} days', '1 day')
    else:
        return date.strftime("%b %e, %Y")## on 10/03/1980