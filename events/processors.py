import re
import dateparser
import events.utils as utils


def parse_start_time(fields):
    fields['start_time'] = dateparser.parse(fields['start_time'])


def add_end_time(fields):
    fields['end_time'] = fields['start_time'].replace(hour=23, minute=59)


def localize(timezone):
    def _localize(fields):
        for time in ('start_time', 'end_time'):
            if fields[time].tzinfo is None:
                fields[time] = timezone.localize(fields[time])
    return _localize


def add_root(*url_keys):
    def _add_root(fields):
        for key in url_keys:
            fields[key] = utils.add_root(fields[key])
    return _add_root


def fetch_category_from_url(regexp):
    def _fetch_category_from_url(fields):
        origin_url = fields['origin_url']
        match = re.search(regexp, origin_url)
        if match:
            fields['categories'] = (match.group(1), )
        else:
            fields['categories'] = ()
    return _fetch_category_from_url


def add_prefix(prefix, keys):
    def _add_prefix(fields):
        for key in keys:
            fields[key] = ''.join((prefix, fields[key]))
    return _add_prefix
