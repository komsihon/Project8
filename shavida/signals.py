
def kick_my_other_sessions(sender, request=None, user=None, **kwargs):
    from tracking.models import Visitor
    from django.contrib.sessions.models import Session
    keys = []
    for v in Visitor.objects.filter(user=request.user).exclude(session_key=request.session.session_key):
        keys.append(v.session_key)
        v.user = None
        v.save()
    Session.objects.filter(session_key__in=keys).delete()
