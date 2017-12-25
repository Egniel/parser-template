import json
import logging

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.core import serializers
from django.utils import timezone
from django.utils import translation
from requests import ConnectionError, RequestException, Timeout

import events.utils as utils
from events.encoders import ObjectWithTimestampEncoder
from events.models import Event, EventCategory
import events.processors as processors
import dateparser
from {{ project_name }}.celery import app

curr_timezone = timezone.get_default_timezone()

logger = logging.getLogger('{{ project_name }}')


def validate_event_fields(fields, ignore=()):
    """Check that 'fields' dict contain all required fields of Event model."""
    # At least one must exist
    if 'address' not in ignore and 'place_title' not in ignore:
        if not fields.get('address') and not fields.get('place_title'):
            return False, 'address or place_title'

    return validate_fields(Event, fields, ignore)


@app.task(name='events.dump_to_db')
def dump_to_db(fields, dates=None):
    if not dates:
        dates = utils.datetime_range_generator(fields.pop('start_time'),
                                               fields.pop('end_time'),
                                               hour=0, minute=0)
        dates = dt_range_to_pairs_of_start_end_time(dates)

    categories = fields.pop('categories', None)
    with translation.override(settings.DEFAULT_LANGUAGE):
        for start_time, end_time in dates:
            event_obj, created = utils.safe_update_or_create(
                Event,
                origin_url=fields['origin_url'],
                start_time=start_time,
                end_time=end_time,
                defaults=fields,
            )
            if created and categories:
                event_obj.categories.add(
                    safe_update_or_create(
                        EventCategory, title=category_name)[0]
                )


@app.task(name='events.parse_events')
def parse_events():
    utils.get_robots_txt()


@app.task(name='events.post_events')
def post_events():
    suffix_url = "/events/multilanguage-events/"
    url = settings.MIDDLEWARE_STORAGE_URL + suffix_url

    qs = Event.objects.filter(
        posted_id=0
    )
    posted_counter = 0

    logger.debug('Trying to post {} events'.format(qs.count()))

    headers = {
        'Authorization': 'Token {}'.format(settings.MIDDLEWARE_AUTH_TOKEN) }
    for event in qs:
        event_json_data = serializers.serialize(
            'json', [event, ], cls=ObjectWithTimestampEncoder,
            use_natural_foreign_keys=True,
        )
        event_data = json.loads(event_json_data)[0]
        payload = event_data.get('fields')

        try:
            r = requests.post(url, json=payload, headers=headers)
        except (RequestException, ConnectionError, Timeout):
            logger.debug(
                "We've problem with continue posting, posted {} events".format(
                    posted_counter))
            continue

        if r.status_code == 201:
            event.posted_id = r.json().get('id')
            event.save()
            posted_counter += 1
        else:
            logger.debug(
                '[{}] Posting problem with event id #{}, {}'.format(
                    r.status_code, event.id, r.content))
    logger.debug('Successfully posted {} events'.format(posted_counter))
