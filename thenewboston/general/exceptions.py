class ThenewbostonError(Exception):
    pass


class ProgrammingError(ThenewbostonError):
    pass


class ThenewbostonRuntimeError(ThenewbostonError):
    pass


class ThenewbostonValueError(ThenewbostonError, ValueError):
    pass
