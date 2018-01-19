import json
import logging

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.core import serializers
from django.utils import timezone
from requests import ConnectionError, RequestException, Timeout

import events.utils as utils
from events.encoders import ObjectWithTimestampEncoder
from events.models import Event
import dateparser
from {{ project_name }}.celery import app


curr_timezone = timezone.get_default_timezone()

logger = logging.getLogger('{{ project_name }}')


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
        'Authorization': 'Token {}'.format(settings.MIDDLEWARE_AUTH_TOKEN)}
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
