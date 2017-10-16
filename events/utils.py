from datetime import datetime
from datetime import timedelta
import re
import itertools

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

    datetime_format = string
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


def pop_from_str_by_regexp(string, regexp, default=None):
    match = re.search(regexp, string)
    if match:
        match = match.group()
        return string.replace(match, ''), match
    else:
        return string, default


def complement_each_other(
        pieces, fetch_order, regexps=get_format_standart_regexps):
    dictified_pieces = []

    # Transfer strings to dict
    for piece in pieces:
        matched_keys = []
        current_piece_dict = {}
        dictified_pieces.append(current_piece_dict)

        for regexp_key in fetch_order:
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

            piece, match = pop_from_str_by_regexp(piece, regexp)

            if match:
                current_piece_dict[regexp_key] = match
                matched_keys.append(regexp_key)

    for piece_dict in dictified_pieces:
        for another_piece_dict in dictified_pieces:
            if piece_dict is not another_piece_dict:
                for key in another_piece_dict:
                    if key not in piece_dict:
                        piece_dict[key] = another_piece_dict[key]

    return tuple(
            (' '.join(piece_dict.keys()), ' '.join(piece_dict.values()))
            for piece_dict in dictified_pieces
        )


def get_soup(url, *, method='get', parser='html.parser', **kwargs):
    url = add_root(url)

    page = getattr(requests, method)(url, **kwargs)
    if page.status_code != 200:
        raise ResponseIsNot200Error(
            'Response from \'{}\' is not 200'.format(page.url))

    return BeautifulSoup(page.content, parser)


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


def getattr_in_select(soup, css_selector, attr=None, default=None, limit=1):
    '''Return regular bs4.select_one value or attr value if attr defined.

    Arguments
    ---------
    attr : str, optional
        Attribute to get. If is None then regular select_one value returned.
    default : any, optional
        Value to return in any except cases (no select found, no attr)
    '''
    if limit is 1:
        select = soup.select_one(css_selector)
    else:
        return soup.select(css_selector, limit=limit)

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
            fields[field_name] = getattr_in_select(
                soup, *fields[field_name])
    else:
        for field_name in fields:
            if fields_to_ignore and field_name in fields_to_ignore:
                continue
            fields[field_name] = getattr_in_select(
                soup, *fields[field_name])


def validate_event_fields(fields, *other_field_names):
    """Check that 'fields' dict contain all required fields of Event model."""
    # At least one must exist
    if not fields.get('address') and fields.get('place_title'):
        return False

    for field_name in EVENT_REQUIRED_FIELDS:
        if not fields.get(field_name):
            return False

    for field_name in other_field_names:
        if not fields.get(field_name):
            return False

    return True


def dump_to_db(
        fields, language=settings.DEFAULT_LANGUAGE, dates=None, timezone=None):
    if timezone:
        fields['start_time'] = timezone.localize(fields['start_time'])
        fields['end_time'] = timezone.localize(fields['end_time'])

    categories = fields.pop('categories')

    if not dates:
        dates = date_range_generator(fields['start_time'], fields['end_time'])

    with translation.override(language):
        for date_and_time in dates:
            event_obj, created = Event.objects.update_or_create(
                origin_url=fields['origin_url'],
                start_time=date_and_time,
                end_time=fields.pop(
                    'end_time',
                    # Otherwise use default:
                    date_and_time.replace(hour=23, minute=59)),
                defaults=fields,
            )

            if created and categories:
                for category in categories:
                    event_obj.categories.add(
                        EventCategory.objects.get_or_create(title=category)[0])
