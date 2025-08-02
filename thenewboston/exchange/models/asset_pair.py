from django.db.models import CASCADE, ForeignKey, UniqueConstraint

from thenewboston.general.models.custom_model import CustomModel


class AssetPair(CustomModel):
    primary_currency = ForeignKey('currencies.Currency', on_delete=CASCADE, related_name='primary_asset_pairs')
    secondary_currency = ForeignKey('currencies.Currency', on_delete=CASCADE, related_name='secondary_asset_pairs')

    class Meta:
        constraints = [UniqueConstraint(fields=['primary_currency', 'secondary_currency'], name='unique_asset_pair')]

    def __str__(self):
        return f'{self.primary_currency.ticker}-{self.secondary_currency.ticker}'
