from django.conf import settings
from django.db import models


class Event(models.Model):
    title = models.CharField(
        max_length=128, verbose_name='заголовок')
    place_title = models.CharField(
        max_length=128, verbose_name='название', blank=True, null=True)
    city = models.CharField(
        max_length=128, verbose_name='город')
    address = models.CharField(
        max_length=512, verbose_name='address', blank=True, null=True)
    start_time = models.DateTimeField('время начала')
    end_time = models.DateTimeField('время завершения')
    cover = models.CharField(
        max_length=2048, verbose_name='изображение', blank=True, null=True)
    categories = models.ManyToManyField(
        'EventCategory', verbose_name='категории')
    description = models.CharField(
        max_length=4096, verbose_name='описание', blank=True, null=True)
    origin_url = models.CharField(
        max_length=2048, verbose_name='origin url')
    posted_id = models.IntegerField(default=0)
    origin = models.CharField(max_length=300,
                              default=settings.ORIGIN)
    booking_url = models.CharField(max_length=512, blank=True, null=True)
    free = models.BooleanField(default=False)

    def __str__(self):
        return 'Title: {}, Date: {}'.format(self.title, self.start_time)


class EventCategory(models.Model):
    title = models.CharField(max_length=128, verbose_name='имя')

    def natural_key(self):
        return self.title

    class Meta:
        orderings = ['title']
        verbose_name = 'категория событий'
        verbose_name_plural = 'категории событий'

    def __str__(self):
        return self.title
