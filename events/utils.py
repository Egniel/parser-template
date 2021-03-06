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


def get_robots_txt(base_url=settings.ROOT_URL):
    requests.get('/'.join((base_url, 'robots.txt')))


@contextmanager
def set_locale(locale_):
    initial_locale = '.'.join(locale.getlocale())
    # TODO make better.
    locale_ = locale.normalize(locale_ + '.utf8')
    yield locale.setlocale(locale.LC_ALL, locale_)
    locale.setlocale(locale.LC_ALL, initial_locale)


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


# TODO: Simplify.
def parse_weeks(string, delimiters=('-')):
    """Return list of all weeks from 'string' enclude week-ranges.

    Parameters:
    -----------
    String : str
        String to get week days from.
    delimiters : tuple of str
        tuple of delimiters which specify that two weeks are week-range.
    """
    # 'calendar' uses current locale.
    week_regexp = '|'.join((
        '|'.join(calendar.day_abbr).lower(),
        '|'.join(calendar.day_name).lower(),
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
        yield (dates[0], dates[-1])
        return  # Raises stop iteration

    # start time
    yield (dates[0], dates[0].replace(hour=23, minute=59))

    for date in dates[1:-1]:
        yield (date, date.replace(hour=23, minute=59))

    # end time
    yield (dates[-1].replace(hour=0, minute=0), dates[-1])


def get_weekday_by_int(weekday_int):
    return calendar.day_name[weekday_int].lower()


def extract_time_from_str(str_with_time):
    fetched_times = []
    hour = re.search(r'(?<!:|\d)\d?\d(?=:\d\d|[AaPp][Mm])', str_with_time)
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


def add_root(root_url=settings.ROOT_URL, url):
    if not url:
        return None
    if '://' not in url:
        if url[0] is not '/':
            url = '/' + url
        return root_url + url
    else:
        return url


def get_soup(url, *, method='get', parser='html.parser', **kwargs):
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


def getattr_in_soup(soup, attr, default=None):
    if soup is None:
        return default

    # Try to get attr from bs4_tag.attrs dictionary(for tag.href etc).
    soup_attr = soup.get(attr)
    if soup_attr is None:
        # Otherwise return regular attr or default(for tag.text etc).
        return getattr(soup, attr, default)
    else:
        return soup_attr
