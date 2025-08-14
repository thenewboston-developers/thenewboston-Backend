import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class UsernameValidator:
    min_length = 2
    max_length = 150

    reserved_words = {'admin', 'support', 'moderator', 'thenewboston', 'ia'}

    def __call__(self, username):
        if len(username) < self.min_length:
            raise ValidationError(
                _(f'Username must be at least {self.min_length} characters long.'), code='username_too_short'
            )

        if len(username) > self.max_length:
            raise ValidationError(
                _(f'Username cannot be longer than {self.max_length} characters.'), code='username_too_long'
            )

        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            raise ValidationError(
                _('Username can only contain letters, numbers, and underscores.'), code='invalid_characters'
            )

        if username.startswith('_') or username.endswith('_'):
            raise ValidationError(_('Username cannot start or end with an underscore.'), code='invalid_start_end')

        if '__' in username:
            raise ValidationError(_('Username cannot contain consecutive underscores.'), code='consecutive_special')

        if username.lower() in self.reserved_words:
            raise ValidationError(_('This username is reserved and cannot be used.'), code='reserved_username')

        return username


username_validator = UsernameValidator()
