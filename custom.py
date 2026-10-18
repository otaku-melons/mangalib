from pydantic import BaseModel

from .modules.enums import ImagesServersTypes

class CustomSettingsModel(BaseModel):
	"""Custom parser settings model."""

	token: str | None
	images_server: ImagesServersTypes
	add_moderation_status: bool
	add_free_publication_date: bool
