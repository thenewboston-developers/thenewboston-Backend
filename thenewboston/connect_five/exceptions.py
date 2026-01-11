from rest_framework.exceptions import APIException


class ConflictError(APIException):
    status_code = 409
    default_detail = 'Conflict.'
    default_code = 'conflict'


class GoneError(APIException):
    status_code = 410
    default_detail = 'Resource is no longer available.'
    default_code = 'gone'
