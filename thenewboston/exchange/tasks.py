from thenewboston.project.celery import app


@app.task(name='tasks.update_trade_history')
def update_trade_history_task():
    from .business_logic.trade_history import update_trade_history

    update_trade_history()


@app.task(name='tasks.update_trade_history_for_currency_pair')
def update_trade_history_for_currency_pair_task(asset_pair_id):
    from .models import TradeHistoryItem

    TradeHistoryItem.objects.update_for_currency_pair(asset_pair_id)
