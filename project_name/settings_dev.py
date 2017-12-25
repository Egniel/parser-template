from . import settings
import os

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': os.environ.get('POSTGRES_DB', 'parser'),
        'USER': os.environ.get('POSTGRES_USER', 'postgres'),
        'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    },
}

CELERY_RESULT_BACKEND = 'django-db'

for dev_app in (
            'django_celery_beat',
            'django_celery_results',
            'rangefilter',
            'raven.contrib.django.raven_compat',
        ):
    if dev_app not in settings.INSTALLED_APPS:
        settings.INSTALLED_APPS.append(dev_app)
