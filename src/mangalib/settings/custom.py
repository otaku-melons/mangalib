from pydantic import BaseModel

from ..modules.enums import ImageServerType

class CustomSettingsModel(BaseModel):
	"""Custom parser settings model."""

	token: str | None
	images_server: ImageServerType
	add_moderation_status: bool
	add_free_publication_date: bool
