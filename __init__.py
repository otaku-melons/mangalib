from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from dublib.web_requestor import WebRequestor
from dublib.web_requestor.config.authorization import Bearer

from melon.core.base.source_operator import BaseSourceOperator

from .settings import CustomSettingsModel

#==========================================================================================#
# >>>>> ВСПОМОГАТЕЛЬНЫЕ СТРУКТУРЫ ДАННЫХ <<<<< #
#==========================================================================================#

@dataclass(frozen = True)
class SlideURI:
	"""URI слайда."""

	server: str
	uri: str

#==========================================================================================#
# >>>>> ОСНОВНОЙ КЛАСС <<<<< #
#==========================================================================================#

class SourceOperator(BaseSourceOperator[CustomSettingsModel]):
	"""Оператор источника."""

	#==========================================================================================#
	# >>>>> СВОЙСТВА <<<<< #
	#==========================================================================================#

	@property
	def api_domain(self) -> str:
		"""Домен для API."""

		if self.__SiteID in (2, 4):
			return "hapi.hentaicdn.org"

		return "api.cdnlibs.org"

	@property
	def site_id(self) -> int | None:
		"""ID официального сайта."""

		return self.__SiteID

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def __StringToDate(self, date_str: str) -> datetime:
		"""
		Парсит строковое представление даты и времени **MangaLib** в объект.

		:param date_str: Строка с датой и временем.
		:type date_str: str
		:return: Объектное представление даты и времени.
		:rtype: datetime
		"""

		DatePattern = "%Y-%m-%dT%H:%M:%S.%fZ"

		return datetime.strptime(date_str, DatePattern)

	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def _CollectSlugs(self, period: int | None = None, filters: str | None = None, pages: int | None = None) -> Sequence[str]:
		"""
		Собирает список алиасов тайтлов по заданным параметрам.

		:param period: Количество часов до текущего момента, составляющее период получения данных.
		:type period: int | None
		:param filters: Строка, описывающая параметры фильтрации.
		:type filters: str | None
		:param pages: Количество запрашиваемых страниц каталога.
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
					Delta = CurrentDate - self.__StringToDate(
						UpdateNote["last_item_at"]
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

	def _InitializeRequestor(self) -> WebRequestor:
		"""
		Инициализирует модуль WEB-запросов.

		:return: Оператор запросов.
		:rtype: WebRequestor
		"""

		WebRequestorObject = super()._InitializeRequestor()
		WebRequestorObject.config.headers.add("site-id", 1)

		return WebRequestorObject

	def _IsTitleExists(self, slug: str) -> bool | None:
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

	def _ParseSlugFromString(self, string: str) -> str | None:
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

	def _PostInitMethod(self):
		"""Метод, выполняющийся после инициализации объекта."""

		self.__Sites: dict[str, int] = {
			"mangalib.me": 1,
			"slashlib.me": 2,
			"v2.shlib.life": 2,
			"hentailib.me": 4
		}
		self.__SiteID: int | None = self.get_site_id()

	def _PostMirrorChanging(self, mirror: str | None):
		"""
		Выполняется после изменения зеркала.

		:param mirror: Домен зеркала.
		:type mirror: str | None
		"""

		self.__SiteID = self.get_site_id(mirror)

		if self.__SiteID:

			if self.__SiteID in (2, 4) and not self.settings.custom.token:
				self.portals.authorization_required(f"Domain \"{mirror}\" requires authorization.")

			self.requestor.config.headers.set("site-id", self.__SiteID)
		else:
			self.requestor.config.headers.remove("site-id")

	def _ReturnCustomSettingsModel(self) -> type[CustomSettingsModel]:

		return CustomSettingsModel

	def _SetAuthorizationMethod(self):
		"""
		Выполняется после `_InitializeRequestor()` и обёрнут для отлова исключений `TokenExpired`.

		Используется для установки авторизации на основе заголовка _Authorization_.
		"""

		Token: str | None = self.settings.custom.token
		if not Token: return

		Authorizator = Bearer()
		Authorizator.set_jwt(Token)
		self.requestor.config.headers.authorization.set_authorization_method(Authorizator)

	#==========================================================================================#
	# >>>>> ПУБЛИЧНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def get_images_servers(self, server_id: str | None = None, all_sites: bool = False) -> list[str]:
		"""
		Возвращает домены серверов хранения изображений.

		:param server_id: ID сервера, для которого получаются домены.
		:type server_id: str | None
		:param all_sites: Указывает, что домены нужно получить для всех сайтов.
		:type all_sites: bool
		:return: Набор доменов.
		:rtype: list[str]
		"""

		Servers = []
		CurrentSiteID = self.get_site_id()
		URL = f"https://{self.api_domain}/api/constants?fields[]=imageServers"

		Response = self.requestor.get(URL)

		if Response.ok and Response.json:
			Data = Response.json["data"]["imageServers"]

			for ServerData in Data:
				if server_id:
					if (
						ServerData["id"] == server_id
						and CurrentSiteID in ServerData["site_ids"]
					):
						Servers.append(ServerData["url"])
					elif ServerData["id"] == server_id and all_sites:
						Servers.append(ServerData["url"])

				else:
					if CurrentSiteID in ServerData["site_ids"] or all_sites:
						Servers.append(ServerData["url"])

		else:
			self.portals.request_error(Response, "Unable to request site constants.")

		return Servers

	def get_site_id(self, site: str | None = None) -> int | None:
		"""
		Возвращает целочисленный идентификатор сайта.

		:param site: Домен сайта (по умолчанию берётся из манифеста).
		:type site: str
		:return: ID сайта или `None` при ошибке.
		:rtype: int | None
		"""

		if not site: site = self.manifest.domain

		for Domain in self.__Sites:
			if Domain in site:
				return self.__Sites[Domain]

		return None