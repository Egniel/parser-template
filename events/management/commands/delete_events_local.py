from distutils.util import strtobool

from django.core.management.base import BaseCommand
from events.models import Event


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        q = Event.objects.all()
        print('Found {} events '.format(len(q),))

        if strtobool(input('Do you want to delete these objects? [y/n]: ')):
            print(q.delete())
        else:
            print('Aborting')
