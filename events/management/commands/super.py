from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from events.tasks import post_events


class Command(BaseCommand):
    def handle(self, *args, **options):
        User.objects.create_superuser('user', '', 'nopassword')
