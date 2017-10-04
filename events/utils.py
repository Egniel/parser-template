from datetime import datetime
from datetime import timedelta
import re
import itertools

import requests
from requests import RequestException, Timeout, ConnectionError
from django.conf import settings
from bs4 import BeautifulSoup


def add_root(url):
    if not url:
        return None
    if '://' not in url:
        if url[0] is not '/':
            url = '/' + url
        return settings.ROOT_URL + url
    else:
        return url


def get_format(string, order, *, defaults={}):
    if not defaults:
        defaults.update({
            '%a': r'(?P<weekday_short>Mon|Tue|Wed|Thu|Fri|Sat|Sun)',
            '%A': r'(?P<weekday>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)',
            '%w': r'(?P<weekday_digit>[0-6])',
            '%d': r'(?P<day>\d\d?)',
            '%b': r'(?P<month_short>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)',
            '%B': r'(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)',
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
        })

    format_ = string

    for element in order:
        # For regexs
        if len(element) > 2:
            format_ = re.sub(
                element.format(**defaults),
                # Find a better way
                re.sub(r'\([^)]*\)|{|}', '', element),
                format_,
                1
            )
        # For strightforward key
        else:
            format_ = re.sub(defaults.get(element), element, format_, 1)

    # Keys not described in order
    for format_sym, regex in defaults.items():
        format_ = re.sub(regex, format_sym, format_, 1)

    return string, format_


def get_soup(url, method='get', params=None, parser='html.parser'):
    url = add_root(url)
    if url is None:
        return None

    try:
        page = getattr(requests, method)(url, params=params)
    except (RequestException, ConnectionError, Timeout):
        return None
    if page.status_code != 200:
        return None

    return BeautifulSoup(page.content, parser)


def safe_select_one(soup, css_selector, attr=None, default=None, limit=1):
    '''Return regular bs4.select_one value or attr value if attr defined.

    Arguments
    ---------
    attr : str, optional
        Attribute to get. If is None then regular select_one value returned.
    default : any, optional
        Value to return in any except cases (no select found, no attr)
    '''
    if css_selector is None:
        return default

    if limit != 1:
        select = soup.select(css_selector, limit=limit)
    else:
        select = soup.select_one(css_selector)

    if select is None:
        return default

    if attr:
        # Try to get attr from bs4_tag.attrs dictionalry(for tag.href etc).
        select_attr = select.get(attr)
        if select_attr is None:
            # Otherwise return regular attr or default(for tag.text etc).
            return getattr(select, attr, default)
        else:
            return select_attr

    return select


def date_range_generator(start_date, end_date, *, format_=None, timezone=None,
                         timezone_obj=None):
    if format_:
        start_date = datetime.strptime(start_date, format_)
        if not end_date:
            end_date = start_date.replace(hour=23, minute=59)
        else:
            end_date = datetime.strptime(end_date, format_)
    if timezone:
        start_date = pytz.timezone(timezone).localize(start_date)
        end_date = pytz.timezone(timezone).localize(end_date)
    elif timezone_obj:
        print('Localized')
        start_date = timezone_obj.localize(start_date)
        end_date = timezone_obj.localize(end_date)

    for day in range((end_date - start_date).days + 1):
        yield start_date + timedelta(days=day)


def fetch_elements_on_page_generator(url, selector):
    soup = get_soup(url)

    for element in soup.select(selector):
        yield element


def fetch_elements_on_page_by_url_until_generator(
        url_template, selector, *, until, state=True, start_page=1):
    """Yield all elements on site page matched by 'selector' selector.

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


def fetch_elements_on_page_by_url_until_generator(
        url_template, selector, *, until, state=True, start_page=1):
    for page in itertools.count(start_page):
        soup = get_soup(url_template.format(page=page))

        for element in soup.select(selector):
            yield element

        condition_element = soup.select_one(until)
        if bool(condition_element) != state:
            break


def update_fields_by_select_match(
        soup, fields, fields_to_update=None, fields_to_ignore=None):
    """Update sent 'fields' dict with data matched on page using bs4 selectors.

    Params
    ------
    fields : dict
        Dict of fields to update, with tuple values containing following data:
            first : css string selector referring directly to element.
            second(optional) : attribute to get from selected object.
            default(optional) : default value to set if selector returned None
                or attribute does not exist.
    fields_to_update : tuple
        A list of fields to update. If None - all fields will be updated
            (Except fields listed in fields_to_ignore).
    fields_to_ignore : tuple
        A list of fields to ignore. Used when fields_to_update is None to
            specifie which fields to not update.
    """

    if fields_to_update:
        for field_name in fields_to_update:
            fields[field_name] = safe_select_one(
                soup, *fields[field_name])
    else:
        for field_name in fields:
            if fields_to_ignore and field_name in fields_to_ignore:
                continue
            fields[field_name] = safe_select_one(
                soup, *fields[field_name])
