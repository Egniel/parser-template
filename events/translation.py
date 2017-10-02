from modeltranslation.decorators import register
from modeltranslation.translator import TranslationOptions

from events.models import Event


@register(Event)
class EventTranslationOptions(TranslationOptions):
    fields = ('title', 'description', 'origin_url', 'booking_url')
