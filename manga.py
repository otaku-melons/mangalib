from Source.Core.Base.Formats.Manga import Branch, Chapter, Types
from Source.Core.Base.Formats.BaseFormat import Cover, Statuses
from Source.Core.Base.Parsers.MangaParser import MangaParser
from Source.Core.Base.Formats.Manga.Elements import Slide

from dublib.Methods.Data import Zerotify

from typing import TYPE_CHECKING
from time import sleep

if TYPE_CHECKING:
	from .main import SourceOperator

class Parser(MangaParser):
	"""Парсер."""

	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#
	
	def _PostInitMethod(self):
		"""Метод, выполняющийся после инициализации объекта."""

		self.__TitleSlug = None
		self.__API = self._SourceOperator.api_domain
		self._SourceOperator: "SourceOperator"

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

			if data["site"] != self._SourceOperator.get_site_id(self._Title.site):
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

					ChapterObject = Chapter(self._SystemObjects, self._Title)
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

	def __GetDescription(self, data: dict) -> str | None:
		"""
		Возвращает описание тайтла.

		:param data: Словарь данных тайтла.
		:type data: dict
		:return: Описание.
		:rtype: str | None
		"""
		
		Description = None
		DescriptionContent = None

		if "summary" in data.keys(): DescriptionContent = data["summary"]["content"][0]
		DescriptionContent = tuple(Element["text"].strip() for Element in DescriptionContent["content"])
		Description = "\n".join(DescriptionContent)

		return Zerotify(Description)

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

	def __GetSiteDomain(self, id: str) -> int | None:
		"""
		Возвращает домен сайта.
			id – целочисленный идентификатор сайта.
		"""

		SiteDomain = None

		for Domain, ID in self.__Sites.items():
			if ID == id: SiteDomain = Domain
		
		return SiteDomain

	def __GetSlides(self, branch_id: int, chapter: Chapter) -> list[dict]:
		"""
		Получает данные о слайдах главы.
			branch_id – идентификатор ветви;\n
			chapter – данные главы.
		"""

		Slides = list()

		if "moderated" in chapter.to_dict().keys() and not chapter["moderated"]:
			self._Portals.chapter_skipped(chapter, comment = "Not moderated.")
			return Slides
		
		Server = self._SourceOperator.get_images_servers(self._Settings.custom["server"])[0]
		Branch = "" if branch_id == str(self._Title.id) + "0" else f"&branch_id={branch_id}"
		URL = f"https://{self.__API}/api/manga/{self.__TitleSlug}/chapter?number={chapter.number}&volume={chapter.volume}{Branch}"
		Response = self._Requestor.get(URL)
		
		if Response.status_code == 200:
			Data = Response.json["data"].setdefault("pages", tuple())
			sleep(self._Settings.common.delay)

			for SlideData in Data:
				SlideObject = Slide(self._SystemObjects, chapter)
				SlideObject.set_link(Server + SlideData["url"].replace(" ", "%20"))
				SlideObject.set_resolution(SlideData["width"], SlideData["height"])
				Slides.append(SlideObject)

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

	#==========================================================================================#
	# >>>>> ПУБЛИЧНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def amend(self, branch: Branch, chapter: Chapter):
		"""
		Дополняет главу дайными о слайдах.

		:param branch: Данные ветви.
		:type branch: Branch
		:param chapter: Данные главы.
		:type chapter: Chapter
		"""

		chapter.set_slides(self.__GetSlides(branch.id, chapter))

	def parse(self):
		"""Получает основные данные тайтла."""

		self._Requestor.config.add_header("Site-Id", str(self._SourceOperator.get_site_id()))

		if self._Title.id and self._Title.slug: self.__TitleSlug = f"{self._Title.id}--{self._Title.slug}"
		else: self.__TitleSlug = self._Title.slug

		Data = self.__GetTitleData()
		self._SystemObjects.controller.get_parser_settings()

		if Data:
			self._Title.set_site(self.__CheckCorrectDomain(Data))
			self._Title.set_id(Data["id"])
			self._Title.set_content_language("rus")
			self._Title.set_localized_name(Data["rus_name"])
			self._Title.set_eng_name(Data["eng_name"])
			self._Title.set_another_names(Data["otherNames"])
			if Data["name"] not in Data["otherNames"] and Data["name"] != Data["rus_name"] and Data["name"] != Data["eng_name"]: self._Title.add_another_name(Data["name"])
			self._Title.add_cover(Cover(self._SystemObjects, self).set_link(Data["cover"]["default"]))
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

	def postprocessor(self):
		"""Вносит изменения в тайтл непосредственно перед сохранением."""

		for CurrentBranch in self._Title.branches:
			for CurrentChapter in CurrentBranch.chapters:
				if not self._Settings.custom["add_moderation_status"]: CurrentChapter.remove_extra_data("moderated")