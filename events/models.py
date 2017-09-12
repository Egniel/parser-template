from django.db import models


class Event(models.Model):
    title = models.CharField(max_length=128, verbose_name='заголовок')
    language = models.CharField(
        verbose_name='язык', max_length=128, default='Language')
    place_title = models.CharField(max_length=128, verbose_name='название')
    city = models.CharField(
        max_length=128, default='London', verbose_name='город')
    address = models.CharField(
        max_length=512, verbose_name='address', null=True)
    start_time = models.DateTimeField('время начала', null=True)
    end_time = models.DateTimeField('время завершения', null=True)
    cover = models.CharField(
        max_length=2048, verbose_name='изображение', blank=True, null=True)
    category = models.ManyToManyField(
        'EventCategory', verbose_name='категория')
    description = models.CharField(
        max_length=4096, verbose_name='описание', blank=True, null=True)
    origin_url = models.CharField(
        max_length=2048, verbose_name='origin url', blank=True, null=True)
    booking_url = models.CharField(max_length=1024, blank=True, null=True)
    posted_id = models.IntegerField(default=0)
    origin = models.CharField(max_length=300, default="origin")

    def __str__(self):
        return self.title


class EventCategory(models.Model):
    title = models.CharField(max_length=128, verbose_name='имя')
    remote_id = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'категория событий'
        verbose_name_plural = 'категории событий'

    def __str__(self):
        return '%s' % self.title
