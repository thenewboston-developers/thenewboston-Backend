if SENTRY_DSN:  # type: ignore # noqa: F821
    import logging

    import sentry_sdk
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber

    from thenewboston.general.utils.sentry import hide_tokens_from_sentry

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
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,  # type: ignore # noqa: F821
        attach_stacktrace=True,
        event_scrubber=EventScrubber(
            denylist=[*DEFAULT_DENYLIST, 'x-guest-token', 'http_x_guest_token'], recursive=True
        ),
        send_default_pii=True,
        in_app_include=['thenewboston'],
        max_request_body_size='always',
        max_value_length=10240,  # 10Kb
        before_send=hide_tokens_from_sentry,
        before_send_transaction=hide_tokens_from_sentry,
    )
