from django.db import models


class AssetPair(models.Model):
    primary_currency = models.ForeignKey('cores.Core', on_delete=models.CASCADE, related_name='primary_asset_pairs')
    secondary_currency = models.ForeignKey(
        'cores.Core', on_delete=models.CASCADE, related_name='secondary_asset_pairs'
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['primary_currency', 'secondary_currency'], name='unique_asset_pair')
        ]

    def __str__(self):
        return f'{self.primary_currency.ticker}-{self.secondary_currency.ticker}'
