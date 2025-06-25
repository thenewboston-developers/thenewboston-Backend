from django.forms.models import model_to_dict


def model_to_dict_with_id(instance):
    return dict(model_to_dict(instance), id=instance.id)
