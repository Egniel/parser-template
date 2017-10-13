from datetime import datetime
from datetime import timedelta
import re
import itertools

from funcy import get_in
import requests
from django.conf import settings
from bs4 import BeautifulSoup


class ResponseIsNot200Error(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


get_format_standart_regexps = {
    '%a': r'(?P<weekday_short>Mon|Tue|Wed|Thu|Fri|Sat|Sun)',
    '%A': (r'(?P<weekday>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sun'
           'day)'),
    '%w': r'(?P<weekday_digit>[0-6])',
    '%d': r'(?P<day>\d\d?)',
    '%b': r'(?P<month_short>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)',
    '%B': (r'(?P<month>January|February|March|April|May|June|July|August|Septe'
           'mber|October|November|December)'),
    '%m': r'(?P<month_digit>\d\d)',
    '%y': r'(?P<year_short>\d\d)',
    '%Y': r'(?P<year>\d\d\d\d)',
    '%H': r'(?P<hour>\d\d?)',
    '%I': r'(?P<hour_short>\d\d?)',
    '%p': r'(?P<period>AM|PM|am|pm)',
    '%M': r'(?P<minute>\d\d)',
    '%S': r'(?P<second>\d\d)',
    '%f': r'(?P<microsecond>\d\d\d\d\d\d)',
    '%z': r'(?P<UTC>[+-]\d\d\d\d)',
    '%Z': r'(?P<time_zone>UTC|EST|CST)',
    '%j': r'(?P<day_of_year>\d\d\d)',
    '%U': r'(?P<week_of_year_sunday>\d\d)',
    '%W': r'(?P<day_of_year_monday>\d\d)',
    # '%c': r'(?P<full_date>Tue Aug 16 21:30:00 1988)',
    '%x': r'(?P<date>\d\d[/.-]\d\d[/.-]\d\d)',
    '%X': r'(?P<time>\d\d:\d\d:\d\d)',
}


def add_root(url):
    if not url:
        return None
    if '://' not in url:
        if url[0] is not '/':
            url = '/' + url
        return settings.ROOT_URL + url
    else:
        return url


def get_format(string, replace_order, *, regexps=get_format_standart_regexps):
    """Return given string and valid datetime.strptime format.

    Function use regexps described in 'regexps' dict (as values) to search
    matches in given 'string'. When it does match anything it will
    replace match with key of matched regexp.
    Matching ocurrs by order described in 'replace_order' tuple.
    'replace_order' tuple must contain keys for 'regexps' dictionary
    in format "{key}". Like so you describe two things in one time:
      regular expression to search (it takes from 'regexps' dict by this key);
      on what to replace (match will be replaced to this key);

    You also can use look ahead/behind assertion for these values to spefify
    key placement in the 'string'.

    Example:
    --------
    # Used default 'get_format_standart_regexps' table
                                                    # Look behind assertion
    get_format('2017 04 12 05:30', ('{%Y}', '{%d}', '(?<=:){%M}'))
    # Will return
    ('2017 04 12 05:30', '%Y %d 12 05:%M')

    ## Another example

    get_format('13:00 2017 October 12', ('(?<={%B}){%m}', '{%d}', '{%Y}'))
    # Will return
                             # \/ This is misstake of your order.
    ('13:00 2017 October 12', '%d:00 %Y October %m')


    Params:
    -------
    string : str
        String to get format from.
    replace_order : tuple of str
        A list of formatted strings. Must only contain keys described in
        'regexps' dictionary.
    regexps : dict
        A dictionary of regular expressions. Contain data in following format:
            key - regular string;
            value - regular expression;
    """
    datetime_format = string

    for element in replace_order:
        # For order element using look ahead/behind assertion
        if len(element) > 2:
            datetime_format = re.sub(
                element.format(**regexps),
                # Get key name from regexp with look ahead/behind assertion
                re.sub(r'\([^)]*\)|{|}', '', element),
                datetime_format,
                1
            )
        # For strightforward key
        else:
            datetime_format = re.sub(
                regexps.get(element), element, datetime_format, 1)

    # Auto complete Keys not described in replace_order
    for format_sym, regex in regexps.items():
        datetime_format = re.sub(regex, format_sym, datetime_format, 1)

    return string, datetime_format


def get_soup(url, *, method='get', parser='html.parser', **kwargs):
    url = add_root(url)

    page = getattr(requests, method)(url, **kwargs)
    if page.status_code != 200:
        raise ResponseIsNot200Error(
            'Response from \'{}\' is not 200'.format(page.url))

    return BeautifulSoup(page.content, parser)


def get_in_select(soup, css_selector, default=None, *attrs_path, limit=1):
    """Return regular bs4.select_one value or it's attr if attrs_path defined.

    Arguments
    ---------
    css_selector : str
        Css selector for element to match in soup.
    default : any, optional
        Value to return in any except cases (no select found, no attr)
    attrs_path : tuple, optional
        Regular 'funcy.get_in' path to the value.
        If is None then regular select_one value returned.
    limit : int
        If None - function will return regular 'select' value.
        See BeautifulSoup docs of 'select' for more.
    """
    if limit is 1:
        select = soup.select_one(css_selector)
    else:
        return soup.select(css_selector, limit=limit)

    if select is None:
        return default

    if attrs_path:
        # Try to get attr from bs4_tag.attrs dictionalry (for tag.href etc).
        select_attr = get_in(select, attrs_path)
        if select_attr is None:
            # Otherwise return regular attr or default (for tag.text etc).
            return get_in(select.__dict__, attrs_path, default)
        else:
            return select_attr

    return select


def date_range_generator(
        start_date, end_date, *, format_=None, timezone_obj=None):
    if format_:
        start_date = datetime.strptime(start_date, format_)
        if not end_date:
            end_date = start_date.replace(hour=23, minute=59)
        else:
            end_date = datetime.strptime(end_date, format_)
    if timezone_obj:
        start_date = timezone_obj.localize(start_date)
        end_date = timezone_obj.localize(end_date)

    yield start_date
    start_date = start_date.replace(hour=00, minute=00)

    for day in range((end_date - start_date).days):
        yield start_date + timedelta(days=day)


def fetch_elements_on_page_generator(url, selector):
    """Yield all elements from site page matched by 'selector' selector."""
    soup = get_soup(url)

    for element in soup.select(selector):
        yield element


def fetch_elements_on_page_by_url_until_generator(
        url_template, selector, *, until, state=True, start_page=1):
    """Yield all elements from site page matched by 'selector' selector.

    Generator iterates over site pages by 'url_template', yileds all elements
    matched by 'selector', until element specified by 'until' selector
    is found (or not found depending on 'state' value).

    Parameters
    ----------
    url_template : str
        Template string with format input '{page}' for specifying page.
    selector : str
        BeautifulSoup selector for link search. All matches will be yielded,
        so you must spefify selector referring directly to elements you search.
    until : str
        BeautifulSoup selector for condition element search. Condition element
        specifies when to stop iterating over pages.
    state : bool
        Specifies trigger for iteration ending.
        True: iterate until 'until' element is currently found on page,
        False: iterate until 'until' element is currently not found on page.
    start_page : int
        Site's start page number.
    """
    for page in itertools.count(start_page):
        soup = get_soup(url_template.format(page=page))

        for element in soup.select(selector):
            yield element

        condition_element = soup.select_one(until)
        if bool(condition_element) != state:
            break


def update_fields_by_get_in_select(
        soup, fields, fields_to_update=None, fields_to_ignore=None):
    """Update sent 'fields' dict with 'get_in_select' function.

    Dict suppose to contain arguments for 'get_in_select' function
    (except first), which will be sent to it and replaced with function return
    value.
    You can specify which fields to update by use 'fields_to_update' or
    'fields_to_ignore' parameters.
    Generaly function will search elements in soup using css selectors,
    and take attributes from matched elements.

    Params
    ------
    soup : BeautifulSoup
        BeautifulSoup object, supposed to represend page.
    fields : dict of tuples
        Dict to update, with tuple values containing data for 'get_in_select'
        function. Tuple's data will be unpacked to 'get_in_select' function
        and replace with returned value.
        See 'get_in_select' docs for more.
    fields_to_update : tuple
        A list of fields to update. If None - all fields will be updated
        (Except fields listed in fields_to_ignore).
    fields_to_ignore : tuple
        A list of fields to ignore. Used when fields_to_update is None to
        specifie which fields to not update.
    """
    if fields_to_update:
        for field_name in fields_to_update:
            fields[field_name] = get_in_select(
                soup, *fields[field_name])
    else:
        for field_name in fields:
            if fields_to_ignore and field_name in fields_to_ignore:
                continue
            fields[field_name] = get_in_select(
                soup, *fields[field_name])
