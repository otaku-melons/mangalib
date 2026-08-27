from pydantic.dataclasses import dataclass

from melon.core.base.parsers.components.settings import CustomSettingsTemplate

@dataclass(frozen = True)
class CustomSettingsModel(CustomSettingsTemplate):
	"""Кастомные параметры парсера."""

	token: str | None
	server: str
	add_moderation_status: bool
	add_free_publication_date: bool