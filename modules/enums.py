from enum import Enum

class ImagesServersTypes(Enum):
	"""Перечисление типов серверов изображений."""

	Main = "main"
	Secondary = "secondary"
	Compress = "compress"
	Download = "download"
	Crop = "crop"