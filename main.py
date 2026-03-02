from Source.Core.Base.SourceOperator import BaseSourceOperator

from dublib.Engine.Bus import ExecutionStatus
from dublib.WebRequestor import WebRequestor

from urllib.parse import urlparse
from datetime import datetime
from time import sleep

class SourceOperator(BaseSourceOperator):
	"""Оператор источника."""

	#==========================================================================================#
	# >>>>> СВОЙСТВА <<<<< #
	#==========================================================================================#

	@property
	def api_domain(self) -> str:
		"""Домен для API."""

		return "api.cdnlibs.org"

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def __IsSlideLink(self, link: str, servers: list[str]) -> bool:
		"""
		Проверяет, ведёт ли ссылка на слайд.
			link – ссылка на изображение;
			servers – список серверов изображений.
		"""

		for Server in servers:
			if Server in link: return True

		return False
	
	def __ParseSlideLink(self, link: str, servers: list[str]) -> tuple[str]:
		"""
		Парсит ссылку на слайд.
			link – ссылка на изображение;
			servers – список серверов изображений.
		"""

		OriginalServer = None
		URI = None

		for Server in servers:

			if Server in link:
				OriginalServer = Server
				URI = link.replace(OriginalServer, "")

		return (OriginalServer, URI)

	def __StringToDate(self, date_str: str) -> datetime:
		"""
		Преобразует строковое время в объектную реализацию.
			date_str – строковая интерпретация.
		"""

		DatePattern = "%Y-%m-%dT%H:%M:%S.%fZ"

		return datetime.strptime(date_str, DatePattern)

	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def _InitializeRequestor(self) -> WebRequestor:
		"""Инициализирует модуль WEB-запросов."""

		WebRequestorObject = super()._InitializeRequestor()
		if self._Settings.custom["token"]: WebRequestorObject.config.add_header("Authorization", self._Settings.custom["token"])

		return WebRequestorObject

	def _PostInitMethod(self):
		"""Метод, выполняющийся после инициализации объекта."""

		self.__Sites = {
			"mangalib.me": 1,
			"slashlib.me": 2,
			"hentailib.me": 4
		}

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

		Servers = list()
		CurrentSiteID = self.get_site_id()
		URL = f"https://{self.api_domain}/api/constants?fields[]=imageServers"
		Headers = {
			"Authorization": self._Settings.custom["token"],
			"Referer": f"https://{self._Manifest.site}/"
		}
		Response = self._Requestor.get(URL, headers = Headers)

		if Response.status_code == 200:
			Data = Response.json["data"]["imageServers"]
			sleep(self._Settings.common.delay)

			for ServerData in Data:

				if server_id:
					if ServerData["id"] == server_id and CurrentSiteID in ServerData["site_ids"]: Servers.append(ServerData["url"])
					elif ServerData["id"] == server_id and all_sites: Servers.append(ServerData["url"])

				else:
					if CurrentSiteID in ServerData["site_ids"] or all_sites: Servers.append(ServerData["url"])

		else:
			self._Portals.request_error(Response, "Unable to request site constants.")

		return Servers

	def get_site_id(self, site: str = None) -> int | None:
		"""
		Возвращает целочисленный идентификатор сайта.

		:param site: Домен сайта (по умолчанию берётся из манифеста).
		:type site: str
		:return: ID сайта или `None` при ошибке.
		:rtype: int | None
		"""

		if not site: site = self._Manifest.site
		SiteID = None

		for Domain in self.__Sites.keys():
			if Domain in site:
				SiteID = self.__Sites[Domain]
				break
		
		return SiteID

	#==========================================================================================#
	# >>>>> КЛЮЧЕВЫЕ ПУБЛИЧНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def collect(self, period: int | None = None, filters: str | None = None, pages: int | None = None) -> tuple[str]:
		"""
		Собирает список алиасов тайтлов по заданным параметрам.

		:param period: Количество часов до текущего момента, составляющее период получения данных.
		:type period: int | None
		:param filters: Строка, описывающая фильтрацию (подробнее в README.md парсера).
		:type filters: str | None
		:param pages: Количество запрашиваемых страниц каталога.
		:type pages: int | None
		:return: Набор собранных алиасов.
		:rtype: tuple[str]
		"""

		Updates = list()
		IsUpdatePeriodOut = False
		Page = 1
		UpdatesCount = 0
		Headers = {
			"Site-Id": str(self.get_site_id())
		}
		CurrentDate = datetime.now()

		while not IsUpdatePeriodOut:
			Response = self._Requestor.get(f"https://{self.api_domain}/api/latest-updates?page={Page}", headers = Headers)

			if Response.status_code == 200:
				UpdatesPage = Response.json["data"]

				for UpdateNote in UpdatesPage:
					Delta = CurrentDate - self.__StringToDate(UpdateNote["last_item_at"])
					
					if Delta.total_seconds() / 3600 <= period:
						Updates.append(UpdateNote["slug_url"])
						UpdatesCount += 1

					else:
						IsUpdatePeriodOut = True

			else:
				IsUpdatePeriodOut = True
				self._Portals.request_error(Response, f"Unable to request updates page {Page}.")


			if not IsUpdatePeriodOut:
				self._Portals.collect_progress_by_page(Page)
				Page += 1
				sleep(self._Settings.common.delay)

		return Updates
	
	def get_slug_from_string(self, data: str) -> ExecutionStatus:
		"""
		Получает алиас тайтла из переданной строки. Может использоваться для обработки тайтлов по ссылкам.

		:param data: Строка, из которой требуется получить алиас.
		:type data: str
		:return: Контейнер ответа. Значение должно содержать строку-алиас или `None`, если получить алиас не удалось.
		В данные статуса также помещается логический ключ _implemented_, говорящий об определении метода в парсере. Отсутствие ключа интерпретируется как наличие имплементации.
		:rtype: ExecutionStatus
		"""

		Status = ExecutionStatus()
		Status["implemented"] = True
		data = data.split("?")[0]
		data = data.split("/")[-1]
		Status.value = data

		return Status
	
	def image(self, url: str) -> ExecutionStatus:
		"""
		Скачивает изображение по ссылке и сохраняет во временный каталог парсера.

		:param url: Ссылка на изображение.
		:type url: str
		:return: Статус выполнение, значение в котором должно содержать имя файла.
		:rtype: ExecutionStatus
		"""

		Result = self._ImagesDownloader.temp_image(url)
		
		if not Result:
			Servers = self.get_images_servers(all_sites = True)

			if self.__IsSlideLink(url, Servers):
				OriginalServer, ImageURI = self.__ParseSlideLink(url, Servers)
				Servers.remove(OriginalServer)
				sleep(self._Settings.common.delay)

				for Server in Servers:
					Link = Server + ImageURI
					Result = self._ImagesDownloader.temp_image(Link)
					
					if Result: break
					elif Server != Servers[-1]: sleep(self._Settings.common.delay)

		return Result