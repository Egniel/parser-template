import json
import logging
from datetime import datetime
from datetime import timedelta

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.core import serializers
from django.utils import timezone
from django.utils import translation
from requests import ConnectionError
from requests import RequestException
from requests import Timeout
from django.db.models.fields import NOT_PROVIDED

import events.utils as utils
from events.encoders import ObjectWithTimestampEncoder
from events.models import Event
from events.models import EventCategory
from {{ project_name }}.celery import app


EVENT_REQUIRED_FIELDS = tuple(
    field.name
    for field in Event._meta.fields if (
        field.blank is False and
        field.null is False and
        field.default is NOT_PROVIDED
        )
)


curr_timezone = timezone.get_default_timezone()

logger = logging.getLogger('{{ project_name }}')


def validate_event_fields(fields, ignore=(), *other_field_names):
    """Check that 'fields' dict contain all required fields of Event model."""
    # At least one must exist
    if 'address' not in ignore and 'place_title' not in ignore:
        if not fields.get('address') and not fields.get('place_title'):
            return False

    validation_field_names = list(EVENT_REQUIRED_FIELDS)
    validation_field_names.extend(other_field_names)

    # Validate fields which are required for 'Event' model.
    # (fields which can't be null, blank, and have no defaults)
    for field_name in validation_field_names:
        # Check that field exists and has value,
        if field_name not in ignore and not fields.get(field_name):
            return False

    return True


def dump_to_db(fields, dates=None):
    if not dates:
        dates = utils.datetime_range_generator(fields.pop('start_time'),
                                               fields.pop('end_time'),
                                               hour=0, minute=0)
        dates = dt_range_to_pairs_of_start_end_time(dates)

    categories = fields.pop('categories', None)
    if categories:
        categories = tuple(
            EventCategory.objects.get_or_create(title=category)[0]
            for category in categories
        )

    with translation.override(settings.DEFAULT_LANGUAGE):
        for start_time, end_time in dates:
            event_obj, created = Event.objects.update_or_create(
                origin_url=fields['origin_url'],
                start_time=start_time,
                end_time=end_time,
                defaults=fields,
            )
            if created and categories:
                for category in categories:
                    event_obj.categories.add(category)


@app.task()
def parse_events():
    pass


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
        'Authorization': 'Token {}'.format(settings.MIDDLEWARE_AUTH_TOKEN)
    }
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
