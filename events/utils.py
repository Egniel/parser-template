from datetime import datetime
from datetime import timedelta
from datetime import time
import re
import itertools
import calendar
import locale
from contextlib import contextmanager

import requests
from django.conf import settings
from bs4 import BeautifulSoup
from django.utils import translation
from django.db.models.fields import NOT_PROVIDED

from events.models import Event
from events.models import EventCategory

EVENT_REQUIRED_FIELDS = tuple(
    field.name
    for field in Event._meta.fields if (
        field.blank is False and
        field.null is False and
        field.default is NOT_PROVIDED
        )
)


REQUIRED_DIRECTIVES = (
    ('%Y', '%y'),
    ('%b', '%B', '%m'),
    ('%d',),
)

last_get_format_language = None


class DateIsNotValidError(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class ResponseIsNot200Error(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


@contextmanager
def set_locale(locale_):
    initial_locale = '.'.join(locale.getlocale())
    locale_ = locale.normalize(locale_ + '.utf8')
    yield locale.setlocale(locale.LC_ALL, locale_)
    locale.setlocale(locale.LC_ALL, initial_locale)


# TODO move everything relative to 'get_format' in one class
def get_locale_depending_format_regexps(locale_=None):
    if locale_ is None:
        locale_ = '.'.join(locale.getlocale())

    with set_locale(locale_):
        locale_depending_format_regexps = {
            '%a': '|'.join(calendar.day_abbr).lower(),
            '%A': '|'.join(calendar.day_name).lower(),
            '%b': '|'.join(calendar.month_abbr[1:]).lower(),
            '%B': '|'.join(calendar.month_name[1:]).lower(),
        }

    return locale_depending_format_regexps

def update_get_format_standart_regexps(language=None): # noqa
    if language is None:
        language = locale.getlocale()[0]

    global last_get_format_language
    if language is not last_get_format_language:
        get_format_standart_regexps.update(
            get_locale_depending_format_regexps(language)
            )
        last_get_format_language = language

get_format_standart_regexps = {  # noqa
    '%w': r'(?P<weekday_digit>[0-6])',
    '%d': r'(?P<day>\d?\d)',
    '%m': r'(?P<month_digit>\d?\d)',
    '%y': r'(?P<year_short>\d\d)',
    '%Y': r'(?P<year>\d\d\d\d)',
    '%H': r'(?P<hour>\d?\d)',
    '%I': r'(?P<hour_short>\d?\d)',
    '%p': r'(?P<period>[aA][mM]|[pP][mM])',
    '%M': r'(?P<minute>\d?\d)',
    '%S': r'(?P<second>\d?\d)',
    '%f': r'(?P<microsecond>\d\d\d\d\d\d)',
    '%z': r'(?P<UTC>[+-]\d\d\d\d)',
    '%Z': r'(?P<time_zone>UTC|EST|CST)',
    '%j': r'(?P<day_of_year>\d\d\d)',
    '%U': r'(?P<week_of_year_sunday>\d\d)',
    '%W': r'(?P<day_of_year_monday>\d\d)',
    # '%c': r'(?P<full_date>Tue Aug 16 21:30:00 1988)',
    '%x': r'(?P<date>\d\d[/.-]\d\d[/.-]\d\d)',
    '%X': r'(?P<time>\d?\d:\d?\d:\d?\d)',
}
update_get_format_standart_regexps()


def get_format(
      string, replace_order, *, regexps=get_format_standart_regexps, **kwargs):
    """Return valid datetime.strptime format by given string and order.

    Function iterates over 'replace_order' tuple (which is a tuple of valid
    keys for 'regexps' dictionary), on each iteration it uses current
    'replace_order' element to get regular expression from 'regexps' dict, and
    try to find match in 'string' by given regular expression. If match is
    found, then whole match will be replaced with a key of regular expression
    that was used to find match. You can describe one 'replace_order' for few
    different format types. You also can use look ahead/behind assertion to
    specify where key supposed to be in the 'string'.

    Params:
    -------
    string : str
        String to get format from.
    replace_order : tuple of str
        tuple of valid keys for 'regexps' dictionary. Must only contain keys
        described in 'regexps' dictionary, keys also can be represented as
        regular expressions.
    regexps : dict
        A dictionary of regular expressions. Contain data in following format:
            key - simple string;
            value - regular expression;
    """
    if kwargs:
        regexps.update(kwargs)

    datetime_format = string.lower()
    matched_keys = []

    for regexp_key in replace_order:
        # If regexp_key is represented as regular expression:
        if '{' in regexp_key:
            # Fill format replacement fields ('{%key}') with regexps.
            regexp = regexp_key.format(**regexps)
            # Extract key name from regexp
            # By replacing anything in '()' and symbols '{', '}' to ''.
            regexp_key = re.sub(r'\([^)]*\)|{|}', '', regexp_key)
        else:
            # Otherwise 'regexp_key' is a regular key, just get regexp.
            regexp = regexps.get(regexp_key)

        # Don't process keys which are already matched.
        if regexp_key in matched_keys:
            continue

        datetime_format = re.sub(
            regexp,  # Find match.
            regexp_key,  # Replace to key.
            datetime_format,
            count=1  # Replace only first match.
        )

        matched_keys.append(regexp_key)

    return datetime_format


def pop_from_str_by_regexp(string, regexp, default=None, count=0):
    """Pop 'count' amout of matches from given 'string'.

    Return:
    ------
    Poped string and list of matches or
    (if match not found) given string and default.
    """
    matches = re.findall(regexp, string)
    if matches:
        if count is 0:
            return re.sub(regexp, '', string), matches
        else:
            return re.sub(regexp, '', string, count=count), matches[:count]
    else:
        return string, default


def date_str_to_dict(
      string, match_order, *, regexps=get_format_standart_regexps, **kwargs):
    """Return dictified date where keys are dt.strptime directives.

    Params:
    -------
    string : str
        String to dictify.
    match_order : tuple of str
        tuple of valid keys for 'regexps' dictionary. Must only contain keys
        described in 'regexps' dictionary, keys also can be represented as
        regular expressions. kwargs are updating regexps.
    regexps : dict
        A dictionary of regular expressions. Contain data in following format:
            key - simple string;
            value - regular expression;
    """
    if kwargs:
        regexps.update(kwargs)

    string = string.lower()
    matched_keys = []
    dictified_date = {}

    for regexp_key in match_order:
        # If regexp_key is represented as regular expression:
        if '{' in regexp_key:
            # Fill format replacement fields ('{%key}') with regexps.
            regexp = regexp_key.format(**regexps)
            # Extract key name from regexp
            # By replacing anything in '()' and symbols '{', '}' to ''.
            regexp_key = re.sub(r'\([^)]*\)|{|}', '', regexp_key)
        else:
            # Otherwise 'regexp_key' is a regular key, just get regexp.
            regexp = regexps.get(regexp_key)
            if not regexp:
                raise ValueError('Invalid regexp key {}'.format(regexp_key))

        # Don't process keys which are already matched.
        if regexp_key in matched_keys:
            continue

        # Pop first match
        string, match = pop_from_str_by_regexp(string, regexp, count=1)

        if match:
            dictified_date[regexp_key] = match[0]
            matched_keys.append(regexp_key)

        matched_keys.append(regexp_key)

    return dictified_date


def get_str_and_format(date_str, match_order, format_order=None):
    """Return formatted string and valid datetime.strptime format for it."""
    if not format_order:
        # TODO Just use ordered dict for 'date_str_to_dict' function.
        # Order of elements in return string and format.
        format_order = (
            '%a',  # Week day (short)
            '%A',  # Week day
            '%w',  # Week day (int)
            '%Y',  # Year (full \d\d\d\d)
            '%y',  # Year (short \d\d)
            '%b',  # Month (short)
            '%B',  # Month
            '%m',  # Month
            '%d',  # Day
            '%H',  # Hour
            '%I',  # Hour (12-hour clock)
            '%M',  # Minute
            '%S',  # Second
            '%p',  # Period (pm, am)
            '%f',  # Microsecond
            '%z',  # Timezone (int)
            '%Z',  # Timezone (UTC, EST, CST)
            '%j',  # Day of year
            '%U',  # Week of year (sunday first)
            '%W',  # Week of year (monday first)
            # '%c': r'(?P<full_date>Tue Aug 16 21:30:00 1988)',
            '%x',  # Date in format \d\d.\d\d.\d\d (depending on locale)
            '%X',  # Time in format \d\d:\d\d:\d\d (depending on locale)
        )

    date_map = date_str_to_dict(date_str, match_order)
    directives = []
    values = []
    for directive in format_order:
        if directive in date_map:
            directives.append(directive)
            values.append(date_map[directive])

    return (' '.join(values), ' '.join(directives))


def complement_each_other(
        date_pieces, match_order, regexps=get_format_standart_regexps):
    dictified_date_pieces = []

    # Transfer strings to dict
    for piece in date_pieces:
        dictified_date_pieces.append(date_str_to_dict(piece, match_order))

    complicated_dates = []
    # Update each other dict in dictified_date_pieces with not existing keys.
    for dictified_date_piece in dictified_date_pieces:
        supplementing_date_dict = dictified_date_piece.copy()

        for dictified_another_date_piece in dictified_date_pieces:
            if dictified_date_piece is not dictified_another_date_piece:
                for key, value in dictified_another_date_piece.items():
                    if key not in supplementing_date_dict:
                        supplementing_date_dict[key] = value

        complicated_dates.append(supplementing_date_dict)

    return complicated_dates


def get_weeks_between_two_enclude(start_day, end_day):
    # Get locale depending week names.
    week_abbrs = list(day_abbr.lower() for day_abbr in calendar.day_abbr)
    week_names = list(day_name.lower() for day_name in calendar.day_name)

    # Lead to single format.
    start_day = start_day.lower()
    end_day = end_day.lower()
    if start_day in week_abbrs:
        start_day = week_names[week_abbrs.index(start_day)]
    if end_day in week_abbrs:
        end_day = week_names[week_abbrs.index(end_day)]

    # Get indexes to use them in slices.
    start_day_index = week_names.index(start_day)
    end_day_index = week_names.index(end_day)

    if end_day_index >= start_day_index:
        return week_names[start_day_index:end_day_index + 1]
    else:
        return week_names[start_day_index:] + week_names[:end_day_index + 1]


def parse_weeks(string, delimiters=('-')):
    """Return list of all weeks from 'string'.

    Parameters:
    -----------
    String : str
        String to get week days from.
    delimiters : tuple of str
        tuple of delimiters which specify that two weeks are week-range.
    """
    week_regexp = '|'.join((
        get_format_standart_regexps.get('%A'),
        get_format_standart_regexps.get('%a'),
    ))

    string = string.lower()
    handled_weeks = []

    # Get all weeks.
    matched_weeks_objects = re.finditer(week_regexp, string)
    prev_match_obj = next(matched_weeks_objects, None)
    if not prev_match_obj:
        return
    first_iteration = True
    for curr_match_obj in matched_weeks_objects:
        # Try to find delimiter right between two weeks
        # to detect if it is a week-range.
        delimiter_match = None
        for delimiter in delimiters:
            delimiter_match = re.fullmatch(
                # Delimiter with possibe spaces.
                r' ?{} ?'.format(delimiter),
                # Text between curr and previous matched weeks.
                string[prev_match_obj.end():curr_match_obj.start()]
            )
            # Stop after first match
            if delimiter_match:
                break

        if delimiter_match:
            handled_weeks.extend(
                get_weeks_between_two_enclude(
                    prev_match_obj.group(),
                    curr_match_obj.group()
                )
            )
        else:
            # Special case for first iteration.
            if first_iteration:
                handled_weeks.append(prev_match_obj.group())
                first_iteration = False
            handled_weeks.append(curr_match_obj.group())

    return handled_weeks


def date_range_generator(start_date, end_date):
    """Yield all dates between two enclude edges."""
    for day in range((end_date - start_date).days + 1):
        yield start_date + timedelta(days=day)


def datetime_range_generator(start_date, end_date, **time_kwargs):
    """Yield all 'datetime's between two dates enclude edges."""
    yield start_date

    if time_kwargs:
        date_between = datetime.combine(start_date.date(), time(**time_kwargs))
    else:
        date_between = start_date

    for day in range(1, (end_date.date() - start_date.date()).days):
        yield date_between + timedelta(days=day)

    yield end_date


def date_dicts_to_datetime(date_dicts_list):
    curr_year = datetime.now().year

    transformed_dates = []
    for date_dict in date_dicts_list:
        # TODO Not a proper way %x and %X will break this.
        if '%Y' not in date_dict and '%y' not in date_dict:
            date_dict['%Y'] = curr_year

        for directives in REQUIRED_DIRECTIVES:
            # At least one key must exist.
            for key in directives:
                if key in date_dict:
                    break
            else:
                raise DateIsNotValidError(
                    'Missing some of directives: {}'.format(directives))

        transformed_dates.append(
            datetime.strptime(
                ' '.join(date_dict.values()),
                ' '.join(date_dict.keys())
            )
        )

    return transformed_dates


def parse_date(date_str, match_order):
    date_str = date_str_to_dict(date_str, match_order)
    return date_dicts_to_datetime(date_str)[0]


def parse_dates(dates_str_list, match_order, with_autocomplementing=False):
    if with_autocomplementing:
        dictified_dates = complement_each_other(dates_str_list)
    else:
        dictified_dates = tuple(
            date_str_to_dict(date_str, match_order)
            for date_str in dates_str_list
        )

    return date_dicts_to_datetime(dictified_dates)


def parse_date_range(start_and_end, match_order, with_autocomplementing=False):
    if len(start_and_end) != 2:
        raise AttributeError(
            'Unexpected lenth of start_and_end iterable. '
            'Expected lenth 2, got {}.'.format(
                len(start_and_end))
        )
    if with_autocomplementing:
        dictified_dates = complement_each_other(start_and_end)
    else:
        dictified_dates = tuple(
            date_str_to_dict(date_str, match_order)
            for date_str in start_and_end
        )

    return datetime_range_generator(
        *date_dicts_to_datetime(dictified_dates)
    )


def get_weekday_by_int(weekday_int):
    week_names = list(day_name.lower() for day_name in calendar.day_name)
    return week_names[weekday_int]


def add_root(url):
    if not url:
        return None
    if '://' not in url:
        if url[0] is not '/':
            url = '/' + url
        return settings.ROOT_URL + url
    else:
        return url


def get_soup(url, *, method='get', parser='html.parser', **kwargs):
    url = add_root(url)

    page = getattr(requests, method)(url, **kwargs)
    if page.status_code != 200:
        raise ResponseIsNot200Error(
            'Response from \'{}\' is not 200'.format(page.url))

    return BeautifulSoup(page.content, parser)


def date_range_generator(start_date, end_date):
    """Yield all dates between two enclude edges."""
    for day in range((end_date - start_date).days + 1):
        yield start_date + timedelta(days=day)


def datetime_range_generator(start_date, end_date, **time_kwargs):
    """Yield all 'datetime's between two dates enclude edges."""
    yield start_date

    if time_kwargs:
        date_between = datetime.combine(start_date.date(), time(**time_kwargs))
    else:
        date_between = start_date

    for day in range(1, (end_date.date() - start_date.date()).days):
        yield date_between + timedelta(days=day)

    yield end_date


def fetch_from_page_generator(url, selector):
    """Yield all elements from site page matched by 'selector' selector."""
    soup = get_soup(url)

    for element in soup.select(selector):
        yield element


def fetch_from_page_until_by_url_generator(
                               url_template, selector, *, until, start_page=1):
    """Yield all elements from site page matched by 'selector' selector.

    Generator iterates over site pages using 'url_template' (which have to
    contain 'page' format's replacement field), yileds all elements matched by
    'selector', until 'until' function returns 'True' (soup of current page
    passed on every iteration of function).

    Parameters
    ----------
    url_template : str
        Template string with format input '{page}' for specifying page.
    selector : str
        Selector for bs4 'select' method used for elements search. All matches
        will be yielded, so you must spefify selector referring directly to
        elements you want to get.
    until : function
        Function which will be called at the end of every page iteration. Soup
        of current page will be passed as only argumet, return value used to
        verify continue iteration or not (True - continue, False - stop).
        Supposed to be used to search some elements on page which will be only
        either on every page except last, either only on last page to use them
        as triggers to stop iterating.
    start_page : int
        Page number to start iterate from.
    """
    for page in itertools.count(start_page):
        soup = get_soup(url_template.format(page=page))

        for element in soup.select(selector):
            yield element

        if not until(soup):
            break


def getattr_in_select(soup, css_selector, attr=None, default=None):
    '''Return regular bs4.select_one value or attr value if attr defined.

    Arguments
    ---------
    soup : BeautifulSoup
        Page soup to search elements in.
    attr : str, optional
        Attribute to get. If is None then regular select_one value will be
        returned.
    default : any, optional
        Value to return in any except cases (no select found, no attr).
    '''
    select = soup.select_one(css_selector)

    if select is None:
        return default

    if attr:
        # Try to get attr from bs4_tag.attrs dictionary(for tag.href etc).
        select_attr = select.get(attr)
        if select_attr is None:
            # Otherwise return regular attr or default(for tag.text etc).
            return getattr(select, attr, default)
        else:
            return select_attr

    return select


def get_fields_by_select_match(soup, fields):
    """Return dict of 'getattr_in_select' results by given 'fields' dict.

    Params
    ------
    soup : BeautifulSoup
        Page soup to search elements in.
    fields : dictionary
        Dictionary where key - name of field, value - tuple of arguments for
        'getattr_in_select' function.
    """
    return {
        field_name: getattr_in_select(soup, *fields[field_name])
        for field_name in fields
        }


def validate_event_fields(fields, ignore=(), *other_field_names):
    """Check that 'fields' dict contain all required fields of Event model."""
    # At least one must exist
    if not fields.get('address') and not fields.get('place_title'):
        return False

    # Validate fields which are required for 'Event' model.
    # (fields which can't be null, blank, and have no defaults)
    for field_name in EVENT_REQUIRED_FIELDS:
        # Check that field exists and has value,
        if field_name not in ignore and not fields.get(field_name):
            return False

    # Validate your castom fields.
    for field_name in other_field_names:
        if not fields.get(field_name):
            return False

    return True


def dump_to_db(
        fields, language=settings.DEFAULT_LANGUAGE, dates=None, timezone=None):
    if timezone:
        if dates:
            dates = tuple(timezone.localize(date) for date in dates)
        else:
            fields['start_time'] = timezone.localize(fields['start_time'])
            fields['end_time'] = timezone.localize(fields['end_time'])

    if dates:
        # If given 'dates' is a list of simgle dates
        # (not of tuples of start and end time)
        if dates and not hasattr(dates[0], '__iter__'):
            dates = tuple(
                (start_date, start_date.replace(hour=23, minute=59))
                for start_date in dates
                )
    else:
        dates = date_range_generator(fields.pop('start_time'),
                                     fields.pop('end_time'))

    categories = fields.pop('categories', None)
    with translation.override(language):
        for start_time, end_time in dates:
            event_obj, created = Event.objects.update_or_create(
                origin_url=fields['origin_url'],
                start_time=start_time,
                end_time=end_time,
                defaults=fields,
            )

            if created and categories:
                for category in categories:
                    event_obj.categories.add(
                        EventCategory.objects.get_or_create(title=category)[0])
