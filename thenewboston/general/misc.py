from django.db.models import FloatField, Func


class ExtractEpoch(Func):
    function = 'EXTRACT'
    template = '%(function)s(EPOCH FROM %(expressions)s)'
    output_field = FloatField()
