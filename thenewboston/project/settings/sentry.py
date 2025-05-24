if SENTRY_DSN:  # type: ignore # noqa: F821
    import logging

    import sentry_sdk
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    logging_integration = LoggingIntegration(
        level=logging.DEBUG,  # Breadcrumbs level
        event_level=SENTRY_EVENT_LEVEL,  # type: ignore # noqa: F821
    )
    # TODO(dmu) LOW: Do we need to add AsyncioIntegration() explicitly or it added automatically?
    integrations = [logging_integration, DjangoIntegration(), AsyncioIntegration()]

    sentry_sdk.init(
        dsn=SENTRY_DSN,  # type: ignore # noqa: F821
        environment=ENV_NAME,  # type: ignore # noqa: F821
        integrations=integrations,
        enable_tracing=False,  # Disable performance monitoring
        attach_stacktrace=True,
        send_default_pii=True,
        in_app_include=['thenewboston'],
        max_request_body_size='always',
        max_value_length=10240,  # 10Kb
    )
