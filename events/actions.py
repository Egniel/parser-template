import logging
from datetime import datetime

import requests

from django.conf import settings
from events.models import Event

logger = logging.getLogger('{{ project_name }}')


def send_pre_action_notification(action):
    """
    {
        "action_type": "POST_EVENTS",
        "origin": {
            "domain": "www.asdasdasd.ru"
        },
        "datetime": "123456789",
        "total": 120,
        "not_posted": 75
    }
    """

    url = '/'.join((settings.PMC_BASE_URL, settings.PMC_PRE_ACTION))
    for origin in Event.objects.values_list('origin', flat=True).distinct():
        data = {
            'action_type': '{}'.format(action),
            'origin': {
                'domain': '{}'.format(origin),
            },
            'datetime': int(datetime.now().timestamp()),
            'total': Event.objects.filter(origin=origin).count(),
            'not_posted': Event.objects.filter(
                origin=origin, posted_id=0).count()
        }
        response = requests.post(url, json=data)
        if response.status_code != 201:
            logger.warning('Error while posting action!', response.text)
