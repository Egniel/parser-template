import logging
import json
from datetime import datetime
from datetime import timedelta

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.core import serializers
from django.utils import timezone
from django.utils.translation import override
from requests import RequestException, Timeout

from events.encoders import ObjectWithTimestampEncoder
from events.models import Event, EventCategory
from {{ project_name }}.celery import app


curr_timezone = timezone.get_default_timezone()

current_date = timezone.now()

logger = logging.getLogger('{{ project_name }}')

root_url = settings.ROOT_URL


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
