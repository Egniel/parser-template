from datetime import datetime
from datetime import timedelta
import re
import itertools
import calendar
import locale
from contextlib import contextmanager

import requests
from django.conf import settings
from bs4 import BeautifulSoup


def unite(*args):
    united = {}
    for dictionary in args:
        for key, value in dictionary.items():
            united[key] = value
    return united


def process(fields, processors):
    for processor in processors:
        processor(fields)
    return fields


@contextmanager
def set_locale(locale_):
    initial_locale = '.'.join(locale.getlocale())
    # TODO make better.
    locale_ = locale.normalize(locale_ + '.utf8')
    yield locale.setlocale(locale.LC_ALL, locale_)
    locale.setlocale(locale.LC_ALL, initial_locale)


REQUIRED_DIRECTIVES = (
    ('%Y', '%y'),
    ('%b', '%B', '%m'),
    ('%d', '%X'),
)

CURR_REGEXPS_LOCALE = None

class DateIsNotValidError(Exception):  # noqa
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

def get_locale_depending_datetime_regexps(locale_=None):  # noqa
    if locale_ is None:
        locale_ = '.'.join(locale.getlocale())

    with set_locale(locale_):
        locale_depending_datetime_regexps = {
            '%a': '|'.join(calendar.day_abbr).lower(),
            '%A': '|'.join(calendar.day_name).lower(),
            '%b': '|'.join(calendar.month_abbr[1:]).lower(),
            '%B': '|'.join(calendar.month_name[1:]).lower(),
        }

    return locale_depending_datetime_regexps

def update_get_format_standart_regexps(language=None): # noqa
    if language is None:
        language = locale.getlocale()[0]

    global CURR_REGEXPS_LOCALE
    if language != CURR_REGEXPS_LOCALE:
        DATETIME_REGEXPS.update(
            get_locale_depending_datetime_regexps(language)
            )
        CURR_REGEXPS_LOCALE = language

DATETIME_REGEXPS = {  # noqa
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
update_get_format_standart_regexps(settings.DEFAULT_LANGUAGE)


def get_format(
      string, replace_order, *, regexps=DATETIME_REGEXPS, **kwargs):
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


def render_regexps_co(string, regexps, directives=None, **extensions):
    """Return iterator which yields matched directives in format (dir, match).

    Function purpose is to render 'regexps' which supposed to be a associate
    structure of 'key: regular_expression_which_represents_key'.

    Function uses regular expressions described in 'regexps' dictionary(as
    values) to search matches in string. If match found it yielded as tuple of
    '(key_of_regular_expression_which_was_used_to_find match, match)'. If
    'directives' passed then only keys described in 'directives' are rendered.

    Parameters:
    -----------
    string : str
        String to search in.
    regexps : dict
        Dictionary of possible directives and regular expression which
        represent directive.
    directives : iterable
        Iterable(list, tuple any other) of directives to render.
    **extensions : directive=regular expression
        Extensions for regexps dictionary for single call. Source dictionary
        will not change(care, regular copy, not deep).

    Send:
    -----
    You can used 'send' method to pass additional directives to render.

    Note:
    -----
    Function is a coroutine which can be used as regular generator-function.
    """
    if extensions:
        regexps = regexps.copy()
        regexps.update(extensions)

    string = string.lower()
    matched_directives = []

    if not directives:
        directives = regexps.keys()

    directives = list(directives)

    for directive in directives:
        # Represented as regular expression:
        if '{' in directive:
            # TODO add description of feature to docstring
            # Fill format replacement fields ('{%key}') with regexps.
            regexp = directive.format(**regexps)
            # Extract key name from regexp
            directive = re.sub(r'\([^)]*\)|{|}', '', directive)
        else:
            # Otherwise 'regexp_key' is a regular key, just get regexp.
            regexp = regexps.get(directive)
            if not regexp:
                raise ValueError('Invalid directive {}'.format(directive))

        # Don't process keys which are already matched.
        if directive in matched_directives:
            continue

        # Pop first match
        string, match = pop_from_str_by_regexp(string, regexp, count=1)

        if match:
            matched_directives.append(directive)
            sent_directive = yield (directive, match[0])
            if sent_directive:
                directives.append(sent_directive)


def date_str_to_dict(string, directives):
    """Return dictified date where keys are dt.strptime directives.

    Params:
    -------
    string : str
        String to dictify.
    directives : str
        str of valid dt.strptime directives separated by space.
    """
    return dict(render_regexps_co(
        string, DATETIME_REGEXPS, directives.split(' ')))


def complement_each_other(date_pieces, directives):
    dictified_date_pieces = []

    # Transfer strings to dict
    for piece in date_pieces:
        dictified_date_pieces.append(date_str_to_dict(piece, directives))

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
    week_names = list(day_name.lower() for day_name in calendar.day_name)

    start_day, end_day = start_day.lower(), end_day.lower()
    start_day_index = end_day_index = None

    for weekday_name in week_names:
        if start_day in weekday_name:
            start_day_index = week_names.index(weekday_name)
        if end_day in weekday_name:
            end_day_index = week_names.index(weekday_name)

    if start_day_index is None or end_day_index is None:
        raise ValueError('Some of week names are not valid: {}'.format(
            (start_day, end_day)))

    if end_day_index >= start_day_index:
        return week_names[start_day_index:end_day_index + 1]
    else:
        return week_names[start_day_index:] + week_names[:end_day_index + 1]


def parse_weeks(string, delimiters=('-')):
    """Return list of all weeks from 'string' enclude week-ranges.

    Parameters:
    -----------
    String : str
        String to get week days from.
    delimiters : tuple of str
        tuple of delimiters which specify that two weeks are week-range.
    """
    week_regexp = '|'.join((
        DATETIME_REGEXPS.get('%A'),
        DATETIME_REGEXPS.get('%a'),
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
        # Set time which will be used for every 'between' date by urself.
        date_between = start_date.replace(**time_kwargs)
    else:
        # Use 'start_date's time otherwise.
        date_between = start_date

    for day in range(1, (end_date.date() - start_date.date()).days):
        yield date_between + timedelta(days=day)

    yield end_date


def dt_range_to_pairs_of_start_end_time(dates):
    dates = list(dates)

    if dates[0].date() == dates[-1].date():
        return (dates[0], dates[-1])

    # start time
    yield (dates[0], dates[0].replace(hour=23, minute=59))

    for date in dates[1:-1]:
        yield (date, date.replace(hour=23, minute=59))

    # end time
    yield (dates[-1].replace(hour=0, minute=0), dates[-1])


def date_dicts_to_datetime(date_dicts_list):
    curr_year = str(datetime.now().year)

    transformed_dates = []
    for date_dict in date_dicts_list:
        # TODO Not a proper way. %x and %X will break this.
        if '%Y' not in date_dict and '%y' not in date_dict:
            date_dict['%Y'] = curr_year

        for directives_list in REQUIRED_DIRECTIVES:
            # At least one key must exist.
            for directive in directives_list:
                if directive in date_dict:
                    break
            # Successfully completed iteration means that 'date_dict'
            # does not contain any of required directives.
            else:
                raise DateIsNotValidError(
                    'Missing some of directives: {}'.format(directives_list))

        transformed_dates.append(
            datetime.strptime(
                ' '.join(date_dict.values()),
                ' '.join(date_dict.keys())
            )
        )

    return transformed_dates


def parse_date(date_str, directives):
    date_dict = date_str_to_dict(date_str, directives)
    return date_dicts_to_datetime((date_dict,))[0]


def parse_dates(dates_str_list, directives, with_autocomplementing=False):
    if with_autocomplementing:
        dictified_dates = complement_each_other(dates_str_list, directives)
    else:
        dictified_dates = tuple(
            date_str_to_dict(date_str, directives)
            for date_str in dates_str_list
        )

    return date_dicts_to_datetime(dictified_dates)


def get_weekday_by_int(weekday_int):
    return calendar.day_name[weekday_int].lower()


def extract_time_from_str(str_with_time):
    fetched_times = []
    hour = re.search(r'(?<!:|\d)\d?\d(?=:|[AaPp][Mm])', str_with_time)
    while hour:
        shift = hour.end()
        # Check for minutes after hour.
        if str_with_time[shift:shift + 1] is ':':
            minute = re.search(r'\d\d', str_with_time[shift:shift + 3])
            minute = minute.group() if minute else '00'
        else:
            minute = '00'

        time = ':'.join((hour.group(), minute))

        fetched_times.append(time)

        # Find next.
        str_with_time = str_with_time[shift:]
        hour = re.search(
            r'(?<!:|\d)\d?\d(?=:|[AaPp][Mm])',
            str_with_time
        )

    return fetched_times


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

    res = getattr(requests, method)(url, **kwargs)
    if res.status_code != 200:
        raise requests.ConnectionError(
            'Response from \'{}\' is not 200'.format(res.url))

    return BeautifulSoup(res.content, parser)


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


def render_dict_by_func(func, render_dict, args_before=(), args_after=()):
    """
    Apply 'func' to 'render_dict' values. Return dict of rendered values.
    """
    return {
        field_name: func(*args_before, *render_dict[field_name], *args_after)
        for field_name in render_dict
        }
