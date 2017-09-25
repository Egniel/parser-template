from django.core.serializers.json import DjangoJSONEncoder
from datetime import datetime


class ObjectWithTimestampEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return int(obj.timestamp())
        return super(ObjectWithTimestampEncoder, self).default(obj)
