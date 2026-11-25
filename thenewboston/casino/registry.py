"""Game apps register their own immutable rules in AppConfig.ready(). No database work occurs here."""

from types import MappingProxyType

from .contracts import GameDefinition, GameRules


class GameRegistry:
    def __init__(self):
        self._games = {}
        self._rules = {}
        self.rules = MappingProxyType(self._rules)

    @property
    def games(self):
        return tuple(sorted(self._games.values(), key=lambda game: (game.catalog_order, game.game)))

    def register(self, definition: GameDefinition):
        if not isinstance(definition.game, str) or not definition.game:
            raise ValueError('A casino game needs a nonempty string identity.')
        existing = self._games.get(definition.game)
        if existing is definition:
            # Django may call ready() again when rebuilding the installed-app registry in tests.
            return
        if existing is not None:
            raise ValueError(f'Casino game {definition.game!r} is already registered.')
        if not isinstance(definition.rules, tuple) or not definition.rules:
            raise ValueError('A casino game needs an identity and an immutable tuple of rules.')
        versions = set()
        for rules in definition.rules:
            if not isinstance(rules, GameRules) or rules.game != definition.game:
                raise ValueError('Registered rules must implement the game contract and match their game identity.')
            if type(rules.version) is not int or rules.version < 1 or rules.version in versions:
                raise ValueError('Casino rules versions must be unique positive integers.')
            if (
                type(rules.catalog_multiplier) is not int
                or type(rules.max_multiplier) is not int
                or not 1 < rules.catalog_multiplier <= rules.max_multiplier
            ):
                raise ValueError('Casino multiplier metadata is invalid.')
            if not 0 <= rules.house_edge < 1:
                raise ValueError('Casino house edge metadata is invalid.')
            versions.add(rules.version)
        if (
            type(definition.default_version) is not int
            or definition.default_version not in versions
            or type(definition.default_min_bet) is not int
            or definition.default_min_bet < 1
        ):
            raise ValueError('Casino catalog defaults must reference installed rules and a positive minimum.')
        # Validate the entire descriptor before publishing any version.
        self._games[definition.game] = definition
        for rules in definition.rules:
            self._rules[(definition.game, rules.version)] = rules

    def get_rules(self, game, version):
        try:
            return self._rules[(game, version)]
        except (KeyError, TypeError) as exc:
            raise ValueError('Unsupported game or rules version.') from exc


registry = GameRegistry()
get_rules = registry.get_rules
