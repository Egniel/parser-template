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

import events.utils as utils
from events.encoders import ObjectWithTimestampEncoder
from events.models import Event
from events.models import EventCategory
from {{ project_name }}.celery import app


curr_timezone = timezone.get_default_timezone()

logger = logging.getLogger('{{ project_name }}')


@app.task()
def process_event_page(url, category):
    print('Started')
    soup = utils.get_soup(url)

    fields = dict(
        title=('.item-name', 'text'),
        place_title=('.item-venue', 'text'),
        dates=('.start-date'),
        start_time=('.start-date', 'text'),
        description=('.tituloIntermedia + div', 'text', ''),
        cover=('[alt="Img"]', 'src'),
    )

    utils.update_fields_by_get_in_select(soup, fields)

    fields['end_time'] = fields['start_time']
    fields['city'] = settings.CITY
    fields['origin_url'] = url
    fields['booking_url'] = url

    if utils.validate_event_fields(fields) is False:
        print('Not valid')
        return

    fields['categories'] = (category,)
    fields['start_time'] = dateparser.parse(fields['start_time'])

    fields['dates'] = tuple(
        dateparser.parse(date)
        for date in fields['dates']
    )

    utils.dump_to_db(fields, timezone=curr_timezone)
    print('Done')


@app.task(name='events.post_events')
def post_events():
    suffix_url = "/events/multilanguage-events/"
    url = settings.MIDDLEWARE_STORAGE_URL + suffix_url

    qs = Event.objects.filter(
        posted_id=0
    )
    posted_counter = 0

    logger.debug('Trying to post {} events'.format(qs.count()))

    for event in qs:
        event_json_data = serializers.serialize(
            'json', [event, ], cls=ObjectWithTimestampEncoder,
            use_natural_foreign_keys=True,
        )
        event_data = json.loads(event_json_data)[0]
        payload = event_data.get('fields')

        try:
            r = requests.post(url, json=payload)
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
