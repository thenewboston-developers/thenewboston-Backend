from django.db import models


class Item(models.Model):
    description = models.TextField()
    image = models.ImageField(upload_to='images/')
    name = models.CharField(max_length=200)
    price_amount = models.PositiveBigIntegerField()
    price_core = models.ForeignKey('cores.Core', on_delete=models.CASCADE)
    quantity = models.PositiveBigIntegerField()

    class Meta:
        abstract = True
