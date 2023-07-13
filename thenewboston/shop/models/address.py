from django.db import models

from thenewboston.general.models import CreatedModified


class Address(CreatedModified):
    owner = models.ForeignKey('users.User', related_name='addresses', on_delete=models.CASCADE)
    address_1 = models.CharField(max_length=255)
    address_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=50)
    state = models.CharField(max_length=50)
    country = models.CharField(max_length=50)
    zip_code = models.CharField(max_length=10)

    def __str__(self):
        address_2_line = f', {self.address_2}' if self.address_2 else ''
        return f'{self.address_1}{address_2_line}, {self.city}, {self.state}, {self.country}, {self.zip_code}'
