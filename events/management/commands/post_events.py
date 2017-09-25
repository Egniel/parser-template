from django.core.management.base import BaseCommand

from events.tasks import post_events


class Command(BaseCommand):
    def handle(self, *args, **options):
        post_events.delay()
