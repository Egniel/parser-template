from django.core.management.base import BaseCommand
from events.models import Event


class Command(BaseCommand):
    def handle(self, *args, **options):
        print('Removed {} events'.format(Event.objects.all().delete()))
