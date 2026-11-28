from datetime import timedelta

from django import forms
from django.contrib.admin.widgets import AdminSplitDateTime
from django.contrib.auth import get_user_model
from django.utils import timezone

from .images import MAX_COVER_BYTES, validate_cover_image
from .models import Tournament, TournamentParticipant


class TournamentCoverField(forms.ImageField):
    def to_python(self, data):
        if data and getattr(data, 'size', 0) > MAX_COVER_BYTES:
            raise forms.ValidationError('Choose an image no larger than 10 MB.')
        image = super().to_python(data)
        return validate_cover_image(image) if image else image


class TournamentForm(forms.ModelForm):
    cover_image = TournamentCoverField(
        required=False,
        help_text='Optional JPEG, PNG, or WebP, up to 10 MB. Resized to fit 1600 pixels and saved as JPEG.',
    )
    ends_at = forms.SplitDateTimeField(
        required=False,
        widget=AdminSplitDateTime(),
        help_text='Leave blank to end seven days after the start.',
    )

    class Meta:
        model = Tournament
        fields = ('title', 'cover_image', 'starts_at', 'ends_at', 'max_players')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        zone = timezone.get_current_timezone_name()
        if 'starts_at' in self.fields:
            self.fields['starts_at'].help_text = f'Enter the date and time in {zone}. Rosters lock at this time.'
        if 'ends_at' in self.fields:
            self.fields['ends_at'].help_text += f' Dates and times use {zone}.'
        if 'max_players' in self.fields:
            self.fields['max_players'].min_value = 1
            self.fields['max_players'].max_value = 10000

    def clean(self):
        data = super().clean()
        starts_at = data.get('starts_at')
        if starts_at:
            if starts_at <= timezone.now():
                self.add_error('starts_at', 'Choose a start time in the future so the roster can be prepared.')
            data['ends_at'] = data.get('ends_at') or starts_at + timedelta(days=7)
            if data['ends_at'] <= starts_at:
                self.add_error('ends_at', 'The tournament must end after it starts.')
        max_players = data.get('max_players')
        if max_players is not None:
            if max_players < 1:
                self.add_error('max_players', 'Allow at least one player.')
            elif max_players > 10000:
                self.add_error('max_players', 'Allow at most 10,000 players.')
            elif (
                self.instance.pk
                and max_players < TournamentParticipant.objects.filter(tournament=self.instance).count()
            ):
                self.add_error(
                    'max_players', 'Remove enrolled players before lowering the limit below the current roster.'
                )
        return data


def tribe_choices(tournament, include_unassigned=True):
    choices = [('', 'Unassigned')] if include_unassigned else []
    return choices + [(str(tribe['id']), tribe['name']) for tribe in tournament.state.get('tribes', [])]


class EnrollPlayerForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        label='Registered username',
        help_text='Enter an existing active account username. Matching is case-insensitive.',
    )
    tribe_id = forms.ChoiceField(required=False, label='Assign to tribe')

    def __init__(self, *args, tournament, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tribe_id'].choices = tribe_choices(tournament)

    def clean_username(self):
        matches = list(
            get_user_model().objects.filter(username__iexact=self.cleaned_data['username'], is_active=True)[:2]
        )
        if not matches:
            raise forms.ValidationError('No active registered user has that username.')
        if len(matches) > 1:
            raise forms.ValidationError(
                'More than one account matches that username. Resolve the duplicate accounts first.'
            )
        return matches[0]


class CreateTribeForm(forms.Form):
    name = forms.CharField(max_length=40, label='Tribe name')
    founder_id = forms.ChoiceField(
        label='Captain', help_text='Enroll a player first, then choose an unassigned player.'
    )

    def __init__(self, *args, tournament, participants, **kwargs):
        super().__init__(*args, **kwargs)
        assigned = {member['id'] for tribe in tournament.state.get('tribes', []) for member in tribe['members']}
        self.fields['founder_id'].choices = [('', 'Choose a captain')] + [
            (str(participant.user_id), participant.user.username)
            for participant in participants
            if participant.user_id not in assigned
        ]


class AssignPlayerForm(forms.Form):
    user_id = forms.ChoiceField(label='Enrolled player')
    tribe_id = forms.ChoiceField(required=False, label='Assign to tribe')

    def __init__(self, *args, tournament, participants, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user_id'].choices = [(str(p.user_id), p.user.username) for p in participants]
        self.fields['tribe_id'].choices = tribe_choices(tournament)


class RemovePlayerForm(forms.Form):
    user_id = forms.ChoiceField(label='Enrolled player')

    def __init__(self, *args, participants, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user_id'].choices = [(str(p.user_id), p.user.username) for p in participants]


class CaptainForm(forms.Form):
    tribe_id = forms.ChoiceField(label='Tribe')
    user_id = forms.ChoiceField(label='New captain', help_text='Choose a player already assigned to this tribe.')

    def __init__(self, *args, tournament, participants, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tribe_id'].choices = tribe_choices(tournament, include_unassigned=False)
        self.fields['user_id'].choices = [(str(p.user_id), p.user.username) for p in participants]


class RemoveTribeForm(forms.Form):
    tribe_id = forms.ChoiceField(label='Tribe')
    confirm = forms.BooleanField(label='Remove this tribe and leave its players enrolled but unassigned')

    def __init__(self, *args, tournament, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tribe_id'].choices = tribe_choices(tournament, include_unassigned=False)
