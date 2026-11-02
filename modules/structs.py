from dataclasses import dataclass
from typing import Literal

from .enums import ImageServerType

@dataclass(frozen = True)
class ImageServerData:
	"""Данные сервера изображений."""

	server_type: ImageServerType
	label: str
	domain: str
	sites: tuple[Literal[1, 2, 3, 4], ...]
