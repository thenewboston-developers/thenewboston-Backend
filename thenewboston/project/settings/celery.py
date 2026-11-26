from celery.schedules import crontab

CELERY_BROKER_URL = 'redis://localhost:6379'
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    'sweep_tribes': {'task': 'tasks.sweep_tribes', 'schedule': 30},
    'expire_blackjack_hands': {
        'task': 'tasks.expire_blackjack_hands',
        'schedule': 60,
    },
    'expire_video_poker_hands': {
        'task': 'tasks.expire_video_poker_hands',
        'schedule': 60,
    },
    'reconcile_casino': {
        'task': 'tasks.reconcile_casino',
        'schedule': 60,
    },
    'deliver_product_analytics': {
        'task': 'tasks.deliver_product_analytics',
        'schedule': 15,
    },
    'delete_expired_guest_games': {
        'task': 'tasks.delete_expired_guest_games',
        'schedule': 60 * 60,
    },
    'sweep_checkers_matches': {
        'task': 'tasks.sweep_checkers_matches',
        'schedule': 10.0,
    },
    'sweep_dots_and_boxes_matches': {
        'task': 'tasks.sweep_dots_and_boxes_matches',
        'schedule': 10.0,
    },
    'sweep_hex_matches': {
        'task': 'tasks.sweep_hex_matches',
        'schedule': 10.0,
    },
    'sweep_battleship_matches': {
        'task': 'tasks.sweep_battleship_matches',
        'schedule': 15,
    },
    'sweep_backgammon_matches': {
        'task': 'tasks.sweep_backgammon_matches',
        'schedule': 15,
    },
    'sweep_reversi_matches': {
        'task': 'tasks.sweep_reversi_matches',
        'schedule': 15,
    },
    'capture_connect_five_elo_snapshots': {
        'task': 'tasks.capture_connect_five_elo_snapshots',
        'schedule': crontab(hour=23, minute=59),
    },
    'delete_unattached_post_images': {
        'task': 'tasks.delete_unattached_post_images',
        'schedule': 60 * 60,  # 1 hour
    },
    'expire_let_it_ride_hands': {
        'task': 'tasks.expire_let_it_ride_hands',
        'schedule': 30,
    },
    'expire_connect_five_challenges': {
        'task': 'tasks.expire_connect_five_challenges',
        'schedule': 30,
    },
    'sweep_mancala_matches': {
        'task': 'tasks.sweep_mancala_matches',
        'schedule': 15,
    },
    'sweep_connect_five_timeouts': {
        'task': 'tasks.sweep_connect_five_timeouts',
        'schedule': 15,
    },
    'update_trade_history': {
        'task': 'tasks.update_trade_history',
        'schedule': 60 * 10,  # 10 minutes
    },
}
