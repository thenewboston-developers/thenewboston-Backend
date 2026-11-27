from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count
from django.http import Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from rest_framework.exceptions import APIException

from . import services
from .admin_forms import (
    AssignPlayerForm,
    CaptainForm,
    CreateTribeForm,
    EnrollPlayerForm,
    RemovePlayerForm,
    RemoveTribeForm,
    TournamentForm,
)
from .models import ActionReceipt, Activity, MoneyEntry, Tournament, TournamentParticipant
from .rules import MAX_MEMBERS


def _error_text(error):
    detail = getattr(error, 'detail', None)
    if detail is None:
        return '; '.join(error.messages) if hasattr(error, 'messages') else str(error)
    if isinstance(detail, dict):
        return '; '.join(f'{field}: {value}' for field, value in detail.items())
    if isinstance(detail, list):
        return '; '.join(str(item) for item in detail)
    return str(detail)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    form = TournamentForm
    change_form_template = 'admin/tribes/tournament/change_form.html'
    list_display = ('title', 'status', 'starts_at', 'ends_at', 'roster_size', 'max_players', 'roster_link')
    list_filter = ('status',)
    search_fields = ('title',)
    ordering = ('-starts_at', '-pk')
    readonly_fields = ('status', 'roster_size', 'currency', 'total_deposited', 'total_withdrawn', 'system_revenue')
    actions = None

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_participant_count=Count('participants'))

    def get_fieldsets(self, request, obj=None):
        fieldsets = [(None, {'fields': ('title', 'starts_at', 'ends_at', 'max_players')})]
        if obj:
            fieldsets.extend(
                [
                    ('Status', {'fields': ('status', 'roster_size')}),
                    (
                        'Accounting (read only)',
                        {'fields': ('currency', 'total_deposited', 'total_withdrawn', 'system_revenue')},
                    ),
                ]
            )
        return fieldsets

    @admin.display(description='Enrolled players', ordering='_participant_count')
    def roster_size(self, obj):
        return obj._participant_count if hasattr(obj, '_participant_count') else obj.participants.count()

    @admin.display(description='Roster')
    def roster_link(self, obj):
        return format_html('<a href="{}">Manage roster</a>', reverse('admin:tribes_tournament_roster', args=[obj.pk]))

    def has_change_permission(self, request, obj=None):
        allowed = super().has_change_permission(request, obj)
        return allowed and (obj is None or (obj.status == 'upcoming' and obj.starts_at > timezone.now()))

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        values = {field: form.cleaned_data[field] for field in ('title', 'starts_at', 'ends_at', 'max_players')}
        if change:
            saved = services.update_tournament(obj.pk, actor=request.user, **values)
        else:
            saved = services.create_tournament(actor=request.user, **values)
        obj.__dict__.update(saved.__dict__)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        context = dict(extra_context or {})
        context['timezone_name'] = timezone.get_current_timezone_name()
        if object_id:
            context['roster_url'] = reverse('admin:tribes_tournament_roster', args=[object_id])
        try:
            return super().changeform_view(request, object_id, form_url, context)
        except (ValidationError, APIException) as error:
            if request.method != 'POST':
                raise
            self.message_user(request, _error_text(error), messages.ERROR)
            return HttpResponseRedirect(request.path)

    def get_urls(self):
        return [
            path(
                '<int:object_id>/roster/', self.admin_site.admin_view(self.roster_view), name='tribes_tournament_roster'
            ),
        ] + super().get_urls()

    def _roster_forms(self, tournament, participants, operation=None, data=None):
        definitions = {
            'enroll': (EnrollPlayerForm, {'tournament': tournament}),
            'create_tribe': (CreateTribeForm, {'tournament': tournament, 'participants': participants}),
            'assign': (AssignPlayerForm, {'tournament': tournament, 'participants': participants}),
            'captain': (CaptainForm, {'tournament': tournament, 'participants': participants}),
            'remove_player': (RemovePlayerForm, {'participants': participants}),
            'remove_tribe': (RemoveTribeForm, {'tournament': tournament}),
        }
        return {
            name: form(data=data if operation == name else None, prefix=name, **kwargs)
            for name, (form, kwargs) in definitions.items()
        }

    def _apply_roster_action(self, request, tournament, operation, data):
        actor = request.user
        tournament_id = tournament.pk
        if operation == 'enroll':
            user = data['username']
            services.add_participant(tournament_id, user.pk, actor=actor)
            if data['tribe_id']:
                services.assign_participant(tournament_id, user.pk, int(data['tribe_id']), actor=actor)
            return f'Enrolled {user.username} (user {user.pk}); tribe {data["tribe_id"] or "unassigned"}.'
        if operation == 'create_tribe':
            services.create_tribe(tournament_id, name=data['name'], founder_id=int(data['founder_id']), actor=actor)
            return f'Created tribe {data["name"]}; captain user {data["founder_id"]}.'
        if operation == 'assign':
            tribe_id = int(data['tribe_id']) if data['tribe_id'] else None
            services.assign_participant(tournament_id, int(data['user_id']), tribe_id, actor=actor)
            return f'Assigned user {data["user_id"]} to tribe {tribe_id or "unassigned"}.'
        if operation == 'captain':
            services.set_tribe_captain(tournament_id, int(data['tribe_id']), int(data['user_id']), actor=actor)
            return f'Set user {data["user_id"]} as captain of tribe {data["tribe_id"]}.'
        if operation == 'remove_player':
            services.remove_participant(tournament_id, int(data['user_id']), actor=actor)
            return f'Removed user {data["user_id"]} from the tournament.'
        services.remove_tribe(tournament_id, int(data['tribe_id']), actor=actor)
        return f'Removed tribe {data["tribe_id"]}; its players remain enrolled and unassigned.'

    def roster_view(self, request, object_id):
        tournament = self.get_object(request, object_id)
        if tournament is None:
            raise Http404
        if not self.has_view_or_change_permission(request, tournament):
            raise PermissionDenied
        can_manage = self.has_change_permission(request, tournament)
        if request.method == 'POST' and not can_manage:
            raise PermissionDenied
        participants = list(TournamentParticipant.objects.filter(tournament=tournament).select_related('user'))
        participants.sort(key=lambda participant: participant.user.username.casefold())
        operation = request.POST.get('operation') if request.method == 'POST' else None
        forms = self._roster_forms(tournament, participants, operation, request.POST)
        if request.method == 'POST':
            if operation not in forms:
                self.message_user(request, 'Choose one of the roster actions below.', messages.ERROR)
            elif forms[operation].is_valid():
                try:
                    with transaction.atomic():
                        description = self._apply_roster_action(
                            request, tournament, operation, forms[operation].cleaned_data
                        )
                        self.log_change(request, tournament, description)
                except (ValidationError, APIException) as error:
                    forms[operation].add_error(None, _error_text(error))
                else:
                    self.message_user(request, description, messages.SUCCESS)
                    return HttpResponseRedirect(request.path)
        assignments = {
            member['id']: tribe for tribe in tournament.state.get('tribes', []) for member in tribe['members']
        }
        tribes = [
            {
                **tribe,
                'captain_name': next(
                    (member['username'] for member in tribe['members'] if member['id'] == tribe['founder_id']),
                    'No captain',
                ),
            }
            for tribe in tournament.state.get('tribes', [])
        ]
        context = {
            **self.admin_site.each_context(request),
            'title': f'Roster: {tournament.title}',
            'opts': self.model._meta,
            'original': tournament,
            'tournament': tournament,
            'can_manage': can_manage,
            'is_locked': tournament.status != 'upcoming' or tournament.starts_at <= timezone.now(),
            'participant_count': len(participants),
            'tribes': tribes,
            'unassigned': [participant.user for participant in participants if participant.user_id not in assignments],
            'max_tribe_members': MAX_MEMBERS,
            'forms': forms,
            'change_url': reverse('admin:tribes_tournament_change', args=[object_id]),
            'media': self.media,
            'timezone_name': timezone.get_current_timezone_name(),
        }
        request.current_app = self.admin_site.name
        return TemplateResponse(request, 'admin/tribes/tournament/roster.html', context)


@admin.register(TournamentParticipant)
class TournamentParticipantAdmin(ReadOnlyAdmin):
    list_display = ('id', 'tournament', 'user')
    list_select_related = ('tournament', 'user')
    search_fields = ('tournament__title', 'user__username')


@admin.register(MoneyEntry)
class MoneyEntryAdmin(ReadOnlyAdmin):
    list_display = ('id', 'tournament', 'wallet', 'amount', 'reason', 'created_at')
    list_filter = ('reason',)
    list_select_related = ('tournament', 'wallet')


@admin.register(ActionReceipt)
class ActionReceiptAdmin(ReadOnlyAdmin):
    list_display = ('id', 'tournament', 'actor', 'action', 'request_id', 'created_at')
    list_select_related = ('tournament', 'actor')


@admin.register(Activity)
class ActivityAdmin(ReadOnlyAdmin):
    list_display = ('id', 'tournament', 'tribe_id', 'user', 'text', 'created_at')
    list_select_related = ('tournament', 'user')
