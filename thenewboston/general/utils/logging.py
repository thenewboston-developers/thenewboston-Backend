import asyncio
import logging
import time
from functools import wraps
from itertools import chain


class log:
    def __init__(
        self,
        name=None,
        level=logging.DEBUG,
        is_method=False,
        with_arguments=False,
        with_return_value=False,
        logger_=None,
        exception_log_level=logging.ERROR,
    ):
        self.name = name
        self.level = level
        self.is_method = is_method
        self.with_arguments = with_arguments
        self.with_return_value = with_return_value
        self.logger = logger_ or logging.getLogger(__name__)
        self.exception_log_level = exception_log_level

        self.callable_name = None
        self._context_start_time = None

    def make_span_representation(self, args=None, kwargs=None):
        if name := self.name:
            return name

        assert args is not None
        assert kwargs is not None

        is_method = self.is_method
        if self.with_arguments:
            arguments_str = ', '.join(
                chain(
                    (repr(arg) for arg in (args[1:] if is_method else args)),
                    (f'{key}={repr(value)}' for key, value in kwargs.items()),
                ),
            )
        else:
            arguments_str = '...'

        representation = f'{self.callable_name}({arguments_str})'
        if is_method:
            representation = f'<{args[0].__class__.__name__} instance>.{representation}'

        return representation

    def log_entering(self, args=None, kwargs=None):
        self.logger.log(self.level, 'Calling %s', self.make_span_representation(args, kwargs))

    def log_exception(self, duration, args=None, kwargs=None):
        self.logger.log(
            self.exception_log_level,
            'Error in %s call (in %.6f seconds)',
            self.make_span_representation(args, kwargs),
            duration,
            exc_info=True,
        )

    def log_exiting(self, duration, result, args=None, kwargs=None):
        return_value_str = f': {repr(result)}' if self.with_return_value else ''
        self.logger.log(
            self.level,
            'Returned from %s (in %.6f seconds)%s',
            self.make_span_representation(args, kwargs),
            duration,
            return_value_str,
        )

    def __call__(self, callable_):
        self.callable_name = callable_.__name__

        @wraps(callable_)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            self.log_entering(args, kwargs)
            try:
                result = callable_(*args, **kwargs)
            except Exception:
                self.log_exception(time.time() - start, args, kwargs)
                raise

            self.log_exiting(time.time() - start, result, args, kwargs)
            return result

        @wraps(callable_)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            self.log_entering(args, kwargs)
            try:
                result = await callable_(*args, **kwargs)
            except Exception:
                self.log_exception(time.time() - start, args, kwargs)
                raise

            self.log_exiting(time.time() - start, result, args, kwargs)
            return result

        return async_wrapper if asyncio.iscoroutinefunction(callable_) else sync_wrapper

    def __enter__(self):
        self._context_start_time = time.time()
        self.name = self.name or 'context'
        self.log_entering()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        duration = time.time() - self._context_start_time
        if exc_type:
            self.log_exception(duration)
        else:
            self.log_exiting(duration, None)
