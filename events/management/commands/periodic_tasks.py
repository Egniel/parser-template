import random

from django.core.management.base import BaseCommand
from django_celery_beat.models import CrontabSchedule, PeriodicTask


class Command(BaseCommand):
    def handle(self, *args, **options):
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute=random.randint(0, 59),
            hour=random.randint(0, 23),
            day_of_week='*',
            day_of_month='*',
            month_of_year='*',
        )

        PeriodicTask.objects.update_or_create(
            name='Parse events', defaults=dict(
                crontab=schedule,
                task='events.parse_events_with_pre_action')
        )

        post_schedule, _ = CrontabSchedule.objects.get_or_create(
            minute=schedule.minute,
            hour=(schedule.hour + 2) % 24,
            day_of_week='*',
            day_of_month='*',
            month_of_year='*',
        )
        PeriodicTask.objects.update_or_create(
            name='Post events', defaults=dict(
                crontab=post_schedule,
                task='events.post_events_with_pre_action')
        )
