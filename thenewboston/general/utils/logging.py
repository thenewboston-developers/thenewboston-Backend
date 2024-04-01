import functools
import logging
import time
from itertools import chain

logger = logging.getLogger(__name__)


def log(level=logging.DEBUG, is_method=False, with_arguments=False, logger_=None, exception_log_level=logging.ERROR):
    logger_ = logger_ or logger

    def decorator(func_or_meth):

        @functools.wraps(func_or_meth)
        def wrapper(*args, **kwargs):
            func_or_meth_name = func_or_meth.__name__
            amended_args = args[1:] if is_method else args

            if with_arguments:
                arguments_repr = ', '.join(
                    chain((repr(arg) for arg in amended_args),
                          (f'{key}={repr(value)}' for key, value in kwargs.items()))
                )
            else:
                arguments_repr = '...'

            func_repr = f'{func_or_meth_name}({arguments_repr})'

            logger_.log(level, 'Calling %s', func_repr)
            start = time.time()
            try:
                result = func_or_meth(*args, **kwargs)
            except Exception:
                end = time.time()
                logger_.log(
                    exception_log_level, 'Error in %s call (in %.6f seconds)', func_repr, end - start, exc_info=True
                )
                raise

            end = time.time()
            logger_.log(level, 'Returned from %s (in %.6f seconds)', func_repr, end - start)
            return result

        return wrapper

    return decorator
