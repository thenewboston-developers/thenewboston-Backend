import yaml


def yaml_coerce(value):
    if isinstance(value, str):
        return yaml.load(f'dummy: {value}', Loader=yaml.SafeLoader)['dummy']

    return value


def identity_decorator(callable_):
    return callable_


class NullObject:

    def __getattr__(self, name):
        return None


null_object = NullObject()


def swallow_exception(callable_, *args, **kwargs):
    try:
        callable_(*args, **kwargs)
    except Exception:
        pass
