from events.tasks import parse_events, post_events
from events.actions import send_pre_action_notification

try:
    from events.tasks import app  # noqa
except ImportError:
    import celery as app  # noqa


@app.task(name='events.parse_events_with_pre_action')
def parse_events_with_pre_action():
    send_pre_action_notification(action='PARSE_EVENTS')
    parse_events.delay()


@app.task(name='events.post_events_with_pre_action')
def post_events_with_pre_action():
    send_pre_action_notification(action='POST_EVENTS')
    post_events.delay()
