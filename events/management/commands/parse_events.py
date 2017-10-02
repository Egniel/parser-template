from django.core.management.base import BaseCommand

from events.tasks import parse_events


class Command(BaseCommand):
    def handle(self, *args, **options):
        parse_events()
