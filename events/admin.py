from celery import states
from django.conf import settings
from django.contrib import admin
from django.utils.translation import ugettext_lazy as _

from django_celery_results.admin import TaskResultAdmin
from django_celery_results.models import TaskResult
from events.models import Event, EventCategory
from rangefilter.filter import DateRangeFilter

admin.site.unregister(TaskResult)

ALL_STATES = sorted(states.ALL_STATES)


class StatusFilter(admin.SimpleListFilter):
    title = 'status'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return sorted(zip(ALL_STATES, ALL_STATES))

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


class CustomTaskResultAdmin(TaskResultAdmin):
    list_filter = [
        StatusFilter,
    ]


class PostedIdFilter(admin.SimpleListFilter):
    title = 'Posted'
    parameter_name = 'posted'

    def lookups(self, request, model_admin):
        return (
            ('posted', 'Posted'),
            ('not_posted', 'Not posted'),

        )

    def queryset(self, request, queryset):
        if self.value() == 'posted':
            return queryset.exclude(posted_id=0)
        elif self.value() == 'not_posted':
            return queryset.filter(posted_id=0)
        else:
            return queryset


class EventAdmin(admin.ModelAdmin):
    searching_fields = [
        'title_{}'.format(lang.replace('-', '_'))
        for lang in settings.MODELTRANSLATION_LANGUAGES]
    search_fields = searching_fields
    list_filter = [
        PostedIdFilter,
        ('start_time', DateRangeFilter),
        'city',
        'categories',
        'origin',
        'place_title',
    ]
    list_display = [
        'start_time',
        'end_time',
        'city',
        'place',
        'title_name',
        'category',
        'origin',
    ]
    ordering = ('start_time',)
    actions = ['reset_posted_ids']

    def reset_posted_ids(self, request, queryset):
        queryset.update(posted_id=0)
        self.message_user(request, _('Posted ids were reset'))

    reset_posted_ids.short_description = _('Reset posted ids')

    def place(self, obj):
        return obj.place_title

    def title_name(self, obj):
        return obj.title

    def category(self, obj):
        return [
            category.title
            for category in obj.categories.all().order_by('title')
        ]

    place.short_description = 'Место'
    title_name.short_description = 'Название'
    category.short_description = 'Категории'


admin.site.register(TaskResult, CustomTaskResultAdmin)
admin.site.register(Event, EventAdmin)
admin.site.register(EventCategory)
