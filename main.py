from Source.Core.Base.Formats.Manga import Branch, Chapter, Types
from Source.Core.Base.Parsers.MangaParser import MangaParser
from Source.Core.Base.Formats.BaseFormat import Statuses

from dublib.Methods.Data import RemoveRecurringSubstrings, Zerotify
from dublib.WebRequestor import WebRequestor

from datetime import datetime
from time import sleep

class Parser(MangaParser):
	"""Парсер."""

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

		self.__TitleSlug = None
		self.__API = "api.cdnlibs.org"
		self.__Sites = {
			"mangalib.me": 1,
			"slashlib.me": 2,
			"hentailib.me": 4
		}

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ ЗАГРУЗКИ ИЗОБРАЖЕНИЙ <<<<< #
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

	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ ПАРСИНГА <<<<< #
	#==========================================================================================#

	def __CheckCorrectDomain(self, data: dict) -> str:
		"""
		Получает возрастной рейтинг.
			data – словарь данных тайтла.
		"""

		Domain = self._Manifest.site

		if self._Title.site:

			if data["site"] != self.__GetSiteID(self._Title.site):
				Domain = self.__GetSiteDomain(data["site"])
				self._Portals.warning(f"Title site changed to \"{Domain}\".")

		return Domain 

	def __GetAgeLimit(self, data: dict) -> int:
		"""
		Получает возрастной рейтинг.
			data – словарь данных тайтла.
		"""

		Rating = None
		RatingString = data["ageRestriction"]["label"].split(" ")[0].replace("+", "").replace("Нет", "")
		if RatingString.isdigit(): Rating = int(RatingString)

		return Rating 

	def __GetAuthors(self, data: dict) -> list[str]:
		"""Получает список авторов."""

		Authors = list()
		for Author in data["authors"]: Authors.append(Author["name"])

		return Authors

	def __GetBranches(self) -> list[Branch]:
		"""Получает содержимое тайтла."""

		Branches: dict[int, Branch] = dict()
		Response = self._Requestor.get(f"https://{self.__API}/api/manga/{self.__TitleSlug}/chapters")
		
		if Response.status_code == 200:
			Data = Response.json["data"]
			sleep(self._Settings.common.delay)

			for CurrentChapterData in Data:

				for BranchData in CurrentChapterData["branches"]:
					BranchID = BranchData["branch_id"]
					if BranchID == None: BranchID = int(str(self._Title.id) + "0")
					if BranchID not in Branches.keys(): Branches[BranchID] = Branch(BranchID)

					ChapterObject = Chapter(self._SystemObjects)
					ChapterObject.set_id(BranchData["id"])
					ChapterObject.set_volume(CurrentChapterData["volume"])
					ChapterObject.set_number(CurrentChapterData["number"])
					ChapterObject.set_name(CurrentChapterData["name"])
					ChapterObject.set_is_paid("restricted_view" in BranchData and not BranchData["restricted_view"]["is_open"])
					ChapterObject.set_workers([sub["name"] for sub in BranchData["teams"]])
					ChapterObject.add_extra_data("moderated", False if "moderation" in BranchData.keys() else True)

					if self._Settings.custom["add_free_publication_date"] and ChapterObject.is_paid:
						ChapterObject.add_extra_data("free-publication-date", BranchData["restricted_view"]["expired_at"])

					Branches[BranchID].add_chapter(ChapterObject)

		else: self._Portals.request_error(Response, "Unable to request chapter.", exception = False)

		for CurrentBranch in Branches.values(): self._Title.add_branch(CurrentBranch)

	def __GetCovers(self, data: dict) -> list[str]:
		"""Получает список обложек."""

		Covers = list()

		if data["cover"]:
			Covers.append({
				"link": data["cover"]["default"],
				"filename": data["cover"]["default"].split("/")[-1]
			})

		if self._Settings.common.sizing_images:
			Covers[0]["width"] = None
			Covers[0]["height"] = None

		return Covers

	def __GetDescription(self, data: dict) -> str | None:
		"""
		Получает описание.
			data – словарь данных тайтла.
		"""

		Description = None
		if "summary" in data.keys(): Description = RemoveRecurringSubstrings(data["summary"], "\n").strip().replace(" \n", "\n")
		Description = Zerotify(Description)

		return Description

	def __GetFranchises(self, data: dict) -> list[str]:
		"""
		Получает список серий.
			data – словарь данных тайтла.
		"""

		Franchises = list()
		for Franchise in data["franchise"]: Franchises.append(Franchise["name"])
		if "Оригинальные работы" in Franchises: Franchises.remove("Оригинальные работы")

		return Franchises

	def __GetGenres(self, data: dict) -> list[str]:
		"""
		Получает список жанров.
			data – словарь данных тайтла.
		"""

		Genres = list()
		for Genre in data["genres"]: Genres.append(Genre["name"])

		return Genres

	def __GetImagesServers(self, server_id: str | None = None, all_sites: bool = False) -> list[str]:
		"""
		Возвращает один или несколько доменов серверов хранения изображений.
			server_id – идентификатор сервера;\n
			all_sites – указывает, что вернуть нужно домены хранилищ изображений для всех сайтов.
		"""

		Servers = list()
		CurrentSiteID = self.__GetSiteID()
		URL = f"https://{self.__API}/api/constants?fields[]=imageServers"
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

	def __GetSiteDomain(self, id: str) -> int | None:
		"""
		Возвращает домен сайта.
			id – целочисленный идентификатор сайта.
		"""

		SiteDomain = None

		for Domain, ID in self.__Sites.items():
			if ID == id: SiteDomain = Domain
		
		return SiteDomain

	def __GetSiteID(self, site: str = None) -> int | None:
		"""
		Возвращает целочисленный идентификатор сайта.
			site – домен сайта (по умолчанию используемый парсером).
		"""

		if not site: site = self._Manifest.site
		SiteID = None

		for Domain in self.__Sites.keys():
			if Domain in site: SiteID = self.__Sites[Domain]
		
		return SiteID

	def __GetSlides(self, branch_id: int, chapter: Chapter) -> list[dict]:
		"""
		Получает данные о слайдах главы.
			branch_id – идентификатор ветви;\n
			chapter – данные главы.
		"""

		Slides = list()

		if "moderated" in chapter.to_dict().keys() and not chapter["moderated"]:
			self._Portals.chapter_skipped(self._Title, chapter, comment = "Not moderated.")
			return Slides
		
		Server = self.__GetImagesServers(self._Settings.custom["server"])[0]
		Branch = "" if branch_id == str(self._Title.id) + "0" else f"&branch_id={branch_id}"
		URL = f"https://{self.__API}/api/manga/{self.__TitleSlug}/chapter?number={chapter.number}&volume={chapter.volume}{Branch}"
		Response = self._Requestor.get(URL)
		
		if Response.status_code == 200:
			Data = Response.json["data"].setdefault("pages", tuple())
			sleep(self._Settings.common.delay)

			for SlideIndex in range(len(Data)):
				Buffer = {
					"index": SlideIndex + 1,
					"link": Server + Data[SlideIndex]["url"].replace(" ", "%20"),
					"width": Data[SlideIndex]["width"],
					"height": Data[SlideIndex]["height"]
				}
				Slides.append(Buffer)

		else: self._Portals.request_error(Response, "Unable to request chapter content.", exception = False)

		return Slides

	def __GetStatus(self, data: dict) -> str:
		"""
		Получает статус.
			data – словарь данных тайтла.
		"""

		Status = None
		StatusesDetermination = {
			1: Statuses.ongoing,
			2: Statuses.completed,
			3: Statuses.announced,
			4: Statuses.dropped,
			5: Statuses.dropped
		}
		SiteStatusIndex = data["status"]["id"]
		if SiteStatusIndex in StatusesDetermination.keys(): Status = StatusesDetermination[SiteStatusIndex]

		return Status

	def __GetTitleData(self) -> dict | None:
		"""
		Получает данные тайтла.
			slug – алиас.
		"""
		
		URL = f"https://{self.__API}/api/manga/{self.__TitleSlug}?fields[]=eng_name&fields[]=otherNames&fields[]=summary&fields[]=releaseDate&fields[]=type_id&fields[]=caution&fields[]=genres&fields[]=tags&fields[]=franchise&fields[]=authors&fields[]=manga_status_id&fields[]=status_id"
		Response = self._Requestor.get(URL)

		if Response.status_code == 200:
			Response = Response.json["data"]
			sleep(self._Settings.common.delay)

		elif Response.status_code == 451: self._Portals.request_error(Response, "Account banned.")
		elif Response.status_code == 404: self._Portals.title_not_found(self._Title)
		else: self._Portals.request_error(Response, "Unable to request title data.")

		return Response

	def __GetTags(self, data: dict) -> list[str]:
		"""
		Получает список тегов.
			data – словарь данных тайтла.
		"""

		Tags = list()
		for Tag in data["tags"]: Tags.append(Tag["name"])

		return Tags

	def __GetType(self, data: dict) -> str:
		"""
		Получает тип тайтла.
			data – словарь данных тайтла.
		"""

		Type = None
		TypesDeterminations = {
			"Манга": Types.manga,
			"Манхва": Types.manhwa,
			"Маньхуа": Types.manhua,
			"Руманга": Types.russian_comic,
			"Комикс западный": Types.western_comic,
			"OEL-манга": Types.oel
		}
		SiteType = data["type"]["label"]
		if SiteType in TypesDeterminations.keys(): Type = TypesDeterminations[SiteType]

		return Type

	def __StringToDate(self, date_str: str) -> datetime:
		"""
		Преобразует строковое время в объектную реализацию.
			date_str – строковая интерпретация.
		"""

		DatePattern = "%Y-%m-%dT%H:%M:%S.%fZ"

		return datetime.strptime(date_str, DatePattern)

	#==========================================================================================#
	# >>>>> ПУБЛИЧНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def amend(self, branch: Branch, chapter: Chapter):
		"""
		Дополняет главу дайными о слайдах.
			branch – данные ветви;\n
			chapter – данные главы.
		"""

		Slides = self.__GetSlides(branch.id, chapter)
		for Slide in Slides: chapter.add_slide(Slide["link"], Slide["width"], Slide["height"])

	def amend_postprocessor(self, chapter: Chapter):
		"""
		Вносит изменения в главу после дополнения её контентом. Запускается независимо от процесса дополнения.
		
		Переопределите данный метод для обработки.

		:param chapter: Данные главы.
		:type chapter: Chapter
		"""

		if not self._Settings.custom["add_moderation_status"]: chapter.remove_extra_data("moderated")

	def collect(self, period: int | None = None, filters: str | None = None, pages: int | None = None) -> list[str]:
		"""
		Собирает список тайтлов по заданным параметрам.
			period – количество часов до текущего момента, составляющее период получения данных;\n
			filters – строка, описывающая фильтрацию (подробнее в README.md);\n
			pages – количество запрашиваемых страниц каталога.
		"""

		Updates = list()
		IsUpdatePeriodOut = False
		Page = 1
		UpdatesCount = 0
		Headers = {
			"Site-Id": str(self.__GetSiteID())
		}
		CurrentDate = datetime.utcnow()

		while not IsUpdatePeriodOut:
			Response = self._Requestor.get(f"https://{self.__API}/api/latest-updates?page={Page}", headers = Headers)

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

	def image(self, url: str) -> str | None:
		"""
		Скачивает изображение с сайта во временный каталог парсера и возвращает имя файла.
			url – ссылка на изображение.
		"""

		Result = self._ImagesDownloader.temp_image(url)
		
		if not Result:
			Servers = self.__GetImagesServers(all_sites = True)

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

	def parse(self):
		"""Получает основные данные тайтла."""

		self._Requestor.config.add_header("Site-Id", str(self.__Sites[self._Manifest.site]))

		if self._Title.id and self._Title.slug: self.__TitleSlug = f"{self._Title.id}--{self._Title.slug}"
		else: self.__TitleSlug = self._Title.slug

		Data = self.__GetTitleData()
		self._SystemObjects.manager.get_parser_settings()

		if Data:
			self._Title.set_site(self.__CheckCorrectDomain(Data))
			self._Title.set_id(Data["id"])
			self._Title.set_slug(Data["slug"])
			self._Title.set_content_language("rus")
			self._Title.set_localized_name(Data["rus_name"])
			self._Title.set_eng_name(Data["eng_name"])
			self._Title.set_another_names(Data["otherNames"])
			if Data["name"] not in Data["otherNames"] and Data["name"] != Data["rus_name"] and Data["name"] != Data["eng_name"]: self._Title.add_another_name(Data["name"])
			self._Title.set_covers(self.__GetCovers(Data))
			self._Title.set_authors(self.__GetAuthors(Data))
			self._Title.set_publication_year(int(Data["releaseDate"]) if Data["releaseDate"] else None)
			self._Title.set_description(self.__GetDescription(Data))
			self._Title.set_age_limit(self.__GetAgeLimit(Data))
			self._Title.set_type(self.__GetType(Data))
			self._Title.set_status(self.__GetStatus(Data))
			self._Title.set_is_licensed(Data["is_licensed"])
			self._Title.set_genres(self.__GetGenres(Data))
			self._Title.set_tags(self.__GetTags(Data))
			self._Title.set_franchises(self.__GetFranchises(Data))

			self.__GetBranches()