from django.core.exceptions import NON_FIELD_ERRORS
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.fields import get_error_detail
from rest_framework.views import exception_handler

SENTINEL = object()


class ThenewbostonError(Exception):
    pass


class ProgrammingError(ThenewbostonError):
    pass


class ThenewbostonRuntimeError(ThenewbostonError):
    pass


class ThenewbostonValueError(ThenewbostonError, ValueError):
    pass


def convert_django_validation_error(exception: DjangoValidationError):
    details = get_error_detail(exception)
    if not isinstance(details, dict):
        details = {'non_field_errors': details}

    if (non_field_errors := details.pop(NON_FIELD_ERRORS, SENTINEL)) is not SENTINEL:
        details.setdefault('non_field_errors', []).extend(non_field_errors)

    return ValidationError(details)


def custom_exception_handler(exc, context):
    """
    This overrides the default exception handler to
    include a human-readable message AND an error code,
    so that clients can respond programmatically.

    Original implementation copied from https://stackoverflow.com/a/50301325/1952977
    """
    if isinstance(exc, DjangoValidationError):
        exc = convert_django_validation_error(exc)

    if isinstance(exc, APIException):
        exc.detail = exc.get_full_details()

    return exception_handler(exc, context)
