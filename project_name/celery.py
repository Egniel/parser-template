import os
import celery
import raven
from django.conf import settings
from raven.contrib.celery import register_signal, register_logger_signal

# set the default Django settings module for the 'celery' program.
os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE', '{}.settings'.format(__spec__.parent))  # noqa


class Celery(celery.Celery):

    def on_configure(self):
        client = raven.Client(settings.SENTRY_URL)  # noqa

        # register a custom filter to filter out duplicate logs
        register_logger_signal(client)

        # hook into the Celery error handler
        register_signal(client)

        client.tags_context(
            dict(PROJECT_GIT_REMOTE=os.environ.get('PROJECT_GIT_REMOTE')),
        )


app = Celery(__name__)
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
