import logging

import requests
from celery.task import task
from django.conf import settings

from events.models import Event, EventCategory

logger = logging.getLogger('{{ project_name }}')


@task(name='events.post_events')
def post_events():
    suffix_url = "/events/"
    url = settings.MIDDLEWARE_STORAGE_URL + suffix_url

    qs = Event.objects.filter(
        posted_id=0
    )
    posted_counter = 0

    logger.debug('Trying to post {} events'.format(qs.count()))

    for event in qs:

        payload = {
            'title': event.title,
            'place_title': event.place_title,
            'address': event.address,
            'city': event.city,
            'description': event.description[:4095],
            'start_time': int(event.start_time.timestamp()),
            'end_time': int(event.end_time.timestamp()),
            'origin_url': event.origin_url,
            'booking_url': event.booking_url,
            'origin': event.origin,
            'cover': event.cover,
            # 'category': event.category, # Until we dont have cat mapping
            'language': settings.LANGUAGE_ID,
        }

        try:
            r = requests.post(url, json=payload)
        except:
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
