from collections.abc import Sequence
from datetime import datetime
from typing import Literal, override

from dublib.web_requestor import WebRequestor
from dublib.web_requestor.config.authorization import Bearer

from melon.core.base.source_operator import BaseSourceOperator

from .custom import CustomSettingsModel
from .modules.enums import ImagesServersTypes
from .modules.structs import ImageServerData

class SourceOperator(BaseSourceOperator[CustomSettingsModel]):
	"""Оператор источника."""

	#==========================================================================================#
	# >>>>> СВОЙСТВА <<<<< #
	#==========================================================================================#

	@property
	def api_domain(self) -> str:
		"""Домен для API."""

		if self.__site_id in (2, 4):
			return "hapi.hentaicdn.org"

		return "api.cdnlibs.org"

	@property
	def site_id(self) -> Literal[1, 2, 3, 4] | None:
		"""ID официального сайта."""

		return self.__site_id

	#==========================================================================================#
	# >>>>> PRIVATE METHODS <<<<< #
	#==========================================================================================#

	def __string_to_date(self, date_str: str) -> datetime:
		"""
		Парсит строковое представление даты и времени **MangaLib** в объект.

		:param date_str: Строка с датой и временем.
		:type date_str: str
		:return: Объектное представление даты и времени.
		:rtype: datetime
		"""

		pattern: str = "%Y-%m-%dT%H:%M:%S.%fZ"

		return datetime.strptime(date_str, pattern)

	#==========================================================================================#
	# >>>>> OVERRIDABLE METHODS <<<<< #
	#==========================================================================================#

	@override
	def _authorize(self):
		"""
		Выполняется после `_InitializeRequestor()` и обёрнут для отлова исключений `TokenExpiredError`.

		Используется для установки авторизации на основе заголовка _Authorization_.
		"""

		Token: str | None = self.settings.custom.token
		if not Token: return

		Authorizator = Bearer()
		Authorizator.set_jwt(Token)
		self.requestor.config.headers.authorization.set_authorization_method(Authorizator)

	@override
	def _collect_slugs(self, period: int | None = None, filters: str | None = None, pages: int | None = None) -> Sequence[str]:
		"""
		Собирает список алиасов тайтлов по заданным параметрам.

		:param period: Количество часов до текущего момента, составляющее период получения данных.
		:type period: int | None
		:param filters: Строка, описывающая параметры фильтрации.
		:type filters: str | None
		:param pages: Requested pages count.
		:type pages: int | None
		:return: Набор собранных алиасов.
		:rtype: Sequence[str]
		"""

		Updates = []
		IsUpdatePeriodOut = False
		Page = 1
		Period = period or 24
		UpdatesCount = 0

		CurrentDate = datetime.now()

		while not IsUpdatePeriodOut:
			Response = self.requestor.get(f"https://{self.api_domain}/api/latest-updates?page={Page}")

			if Response.ok and Response.json:
				UpdatesPage = Response.json["data"]

				for UpdateNote in UpdatesPage:
					Delta = CurrentDate - self.__string_to_date(
						UpdateNote["last_item_at"],
					)

					if Delta.total_seconds() / 3600 <= Period:
						Updates.append(UpdateNote["slug_url"])
						UpdatesCount += 1

					else:
						IsUpdatePeriodOut = True

			else:
				IsUpdatePeriodOut = True
				self.portals.request_error(Response, f"Unable to request updates page {Page}.")

			if not IsUpdatePeriodOut:
				self.portals.collect_progress_by_page(Page)
				Page += 1

			if Page == pages: break

		return Updates

	@override
	def _export_custom_settings_model(self) -> type[CustomSettingsModel]:
		"""
		Экспортирует модель кастомных настроек парсера. Модель должна быть унаследована от `CustomSettingsModel`.

		:return: Модель кастомных настроек парсера.
		:rtype: type[CustomSettingsModel]
		"""

		return CustomSettingsModel

	@override
	def _initialize_requestor(self) -> WebRequestor:
		"""
		Инициализирует модуль WEB-запросов.

		:return: Оператор запросов.
		:rtype: WebRequestor
		"""

		WebRequestorObject = super()._initialize_requestor()
		WebRequestorObject.config.headers.add("site-id", 1)

		return WebRequestorObject

	@override
	def _is_title_exists(self, slug: str) -> bool | None:
		"""
		Проверяет, существует ли тайтл на сервере.

		:param slug: Алиас тайтла.
		:type slug: str
		:return: Возвращает статус существования файла на сервере или `None` при невозможности проверки.
		:rtype: bool | None
		"""

		Response = self.requestor.get(f"https://{self.api_domain}/api/manga/{slug}")

		if Response.ok: return True
		if Response.status_code == 404: return False

		return None

	@override
	def _extract_slug_from_string(self, string: str) -> str | None:
		"""
		Парсит алиас тайтла из переданной строки. Может использоваться для обработки тайтлов по ссылкам.

		:param string: Строка, из которой требуется получить алиас.
		:type string: str
		:return: Алиас или `None` в случае неудачи или отсутствия имплементации.
		:rtype: str | None
		"""

		string = string.split("?")[0]
		string = string.split("/")[-1]

		return string

	@override
	def _post_init(self):
		"""Execute after instance initialization."""

		self.__sites: dict[str, Literal[1, 2, 3, 4]] = {
			"mangalib.me": 1,
			"slashlib.me": 2,
			"v2.shlib.life": 2,
			"hentailib.me": 4,
		}
		self.__site_id: Literal[1, 2, 3, 4] | None = self.get_site_id()

	@override
	def _post_mirror_changing(self, mirror: str | None):
		"""
		Выполняется после изменения зеркала.

		:param mirror: Домен зеркала.
		:type mirror: str | None
		"""

		self.__site_id = self.get_site_id(mirror)

		if self.__site_id:

			if self.__site_id in (2, 4) and not self.settings.custom.token:
				self.portals.authorization_required(f"Domain \"{mirror}\" requires authorization.")

			self.requestor.config.headers.set("site-id", self.__site_id)
		else:
			self.requestor.config.headers.remove("site-id")

	#==========================================================================================#
	# >>>>> PUBLIC METHODS <<<<< #
	#==========================================================================================#

	def get_images_servers(self, server_type: ImagesServersTypes | None = None, site_id: Literal[1, 2, 3, 4] | None = None) -> tuple[ImageServerData, ...]:
		"""
		Получает последовательность доменов серверов изображений.

		:param server_type: Тип сервера изображений. По умолчанию определяется настройками парсера.
		:type server_type: ImagesServersTypes | None
		:param site_id: ID сайта, для которого запрашиваются домены серверов. По умолчанию определяется на основе манифеста.
		:type site_id: Literal[1, 2, 3, 4] | None
		:return: Последовательность данных доменов.
		:rtype: tuple[ImageServerData, ...]
		"""

		if server_type is None: server_type = self.settings.custom.images_server
		if site_id is None: site_id = self.site_id

		url: str = f"https://{self.api_domain}/api/constants?fields[]=imageServers"
		response = self.requestor.get(url)

		if not response.ok or not response.json:
			self.portals.request_error(response, "Unable to request site constants.")

		data: dict = response.json["data"]
		servers_data: list[dict] = data["imageServers"]
		servers: list[ImageServerData] = []

		for server_data in servers_data:
			domain: str = server_data["url"]
			domain = domain.replace("https://", "")

			servers.append(ImageServerData(
				server_type = ImagesServersTypes(server_data["id"]),
				label = server_data["label"],
				domain = domain,
				sites = tuple(server_data["site_ids"]),
			))


		servers = list(filter(lambda server: server.server_type is server_type, servers))
		servers = list(filter(lambda server: site_id in server.sites, servers))

		return tuple(servers)

	def get_site_id(self, site: str | None = None) -> Literal[1, 2, 3, 4] | None:
		"""
		Определяет целочисленный идентификатор сайта.

		:param site: Домен сайта (по умолчанию берётся из манифеста).
		:type site: str
		:return: ID сайта или `None` при невозможности определения.
		:rtype: Literal[1, 2, 3, 4] | None
		"""

		if not site:
			site = self.manifest.domain

		for domain in self.__sites:
			if domain in site:
				return self.__sites[domain]

		return None
