from typing import TYPE_CHECKING, Literal, cast

from dublib.functions.data import Zerotify

from melon.core.base.formats.base_format import ImageData, Statuses
from melon.core.base.formats.manga import BaseBranch, Chapter, Types
from melon.core.base.parsers.base_manga_parser import BaseMangaParser

if TYPE_CHECKING:
	from melon.core.base.formats.manga import Manga

	from . import SourceOperator

class Parser(BaseMangaParser):
	"""Парсер."""
	#==========================================================================================#
	# >>>>> ПРИВАТНЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def __GetAgeLimit(self, data: dict) -> int | None:
		"""
		Получает возрастной рейтинг.

		:param data: Словарь данных тайтла.
		:type data: dict
		:return: Возрастной рейтинг.
		:rtype: int | None
		"""

		RatingString: str = data["ageRestriction"]["label"].split(" ")[0].replace("+", "").replace("Нет", "")

		if RatingString.isdigit():
			return int(RatingString)

		return None 

	def __GetAuthors(self, data: dict) -> list[str]:
		"""
		Получает список авторов.

		:param data: Словарь данных тайтла.
		:type data: dict
		:return: Список авторов.
		:rtype: list[str]
		"""

		Authors = []

		for Author in data["authors"]:
			Authors.append(Author["name"])

		return Authors

	def __GetBranches(self):
		"""Получает ветви контента тайтла и устанавливает их."""

		SourceOperatorObject = cast("SourceOperator", self.source_operator)
		Title = cast("Manga", self.title)

		Branches: dict[int, BaseBranch] = {}
		Response = self.requestor.get(f"https://{SourceOperatorObject.api_domain}/api/manga/{Title.slug}/chapters")
		
		if Response.ok and Response.json:
			Data = Response.json["data"]

			for CurrentChapterData in Data:

				for BranchData in CurrentChapterData["branches"]:
					OriginalBranchID: int | None = BranchData.get("branch_id")
					BranchID: int = OriginalBranchID or int(str(Title.id) + "0")

					if BranchID not in Branches.keys():
						Branches[BranchID] = BaseBranch(BranchID)

					ChapterObject = Chapter(self, CurrentChapterData["id"])
					ChapterObject.set_volume(CurrentChapterData["volume"])
					ChapterObject.set_number(CurrentChapterData["number"])
					ChapterObject.set_name(CurrentChapterData["name"])
					ChapterObject.set_is_paid("restricted_view" in BranchData and not BranchData["restricted_view"]["is_open"])
					ChapterObject.set_workers([sub["name"] for sub in BranchData["teams"]])
					ChapterObject.extra_data.set("moderated", False if "moderation" in BranchData else True)

					if self.settings.custom["add_free_publication_date"] and ChapterObject.is_paid:
						ChapterObject.extra_data.set("free-publication-date", BranchData["restricted_view"]["expired_at"])

					Branches[BranchID].add_chapter(ChapterObject)

		else: self.portals.request_error(Response, "Unable to request chapter.", exception = False)

		for CurrentBranch in Branches.values(): Title.add_branch(CurrentBranch)

	def __GetDescription(self, data: dict) -> str | None:
		"""
		Возвращает описание тайтла.

		:param data: Словарь данных тайтла.
		:type data: dict
		:return: Описание.
		:rtype: str | None
		"""

		Summary: dict | None = data.get("summary")

		if not Summary:
			return None

		DescriptionContent: dict = Summary["content"][0]
		Content: list[dict] | None = DescriptionContent.get("content")

		if not Content:
			return None

		Content = cast(list[dict], Content)
		DescriptionLines: list[str] = []

		for Element in Content:
			if Element.get("type") != "text": continue
			Paragraph: str | None = Element.get("text")
			if not Paragraph: continue
			DescriptionLines.append(Paragraph)

		Description = "\n".join(DescriptionLines)

		return Zerotify(Description)

	def __GetClassificators(self, data: dict, classificators_type: Literal["franchise", "genres", "tags"]) -> list[str]:
		"""
		Получает классификаторы тайтла.

		:param data: Словарь данных тайтла.
		:type data: dict
		:param classificators_type: Тип получаемых классификаторов.
		:type classificators_type: Literal["genres", "tags"]
		:return: Список классификаторов.
		:rtype: list[str]
		"""

		Classificators = []
		for ClassificatorData in data[classificators_type]:
			Classificators.append(ClassificatorData["name"])

		if classificators_type == "franchise" and "Оригинальные работы" in Classificators:
			Classificators.remove("Оригинальные работы")

		return Classificators

	def __GetSlides(self, branch_id: int, chapter: Chapter) -> list[ImageData]:
		"""
		Получает данные слайдов.

		:param branch_id: ID ветви.
		:type branch_id: int
		:param chapter: Глава.
		:type chapter: Chapter
		:return: Список данных слайдов.
		:rtype: list[ImageData]
		"""

		SourceOperatorObject = cast("SourceOperator", self.source_operator)
		Title = cast("Manga", self.title)

		Slides: list[ImageData] = []

		if chapter.extra_data.exists("moderated") and not chapter.extra_data.get("moderated"):
			self.portals.chapter_skipped(chapter, comment = "Not moderated.")
			return Slides
		
		Server = SourceOperatorObject.get_images_servers(self.settings.custom["server"])[0]
		Branch = "" if branch_id == str(Title.id) + "0" else f"&branch_id={branch_id}"
		URL = f"https://{SourceOperatorObject.api_domain}/api/manga/{Title.slug}/chapter?number={chapter.number}&volume={chapter.volume}{Branch}"
		Response = self.requestor.get(URL)
		
		if Response.ok and Response.json:
			Data = Response.json["data"].setdefault("pages", ())

			for SlideData in Data:
				ImageBuffer = ImageData(Server + SlideData["url"].replace(" ", "%20"))
				ImageBuffer.create_resolution(SlideData["width"], SlideData["height"])
				Slides.append(ImageBuffer)

		else: self.portals.request_error(Response, "Unable to request chapter content.", exception = False)

		return Slides

	def __GetStatus(self, data: dict) -> Statuses | None:
		"""
		Определяет статус тайтла.

		:param data: Словарь данных тайтла.
		:type data: dict
		:return: Статус тайтла
		:rtype: Statuses | None
		"""

		StatusesDetermination = {
			1: Statuses.ongoing,
			2: Statuses.completed,
			3: Statuses.announced,
			4: Statuses.dropped,
			5: Statuses.dropped
		}
		SiteStatusIndex = data["status"]["id"]
		if SiteStatusIndex in StatusesDetermination:
			return StatusesDetermination[SiteStatusIndex]

		return None

	def __GetTitleData(self) -> dict | None:
		"""
		Получает данные тайтла.

		:return: Словарь данных тайтла.
		:rtype: dict | None
		"""

		SourceOperatorObject = cast("SourceOperator", self.source_operator)
		Title = cast("Manga", self.title)
		
		Query = (
			"eng_name",
			"otherNames",
			"summary",
			"releaseDate",
			"caution",
			"genres",
			"tags",
			"franchise",
			"authors",
			"manga_status_id",
			"status_id"
		)
		URL = f"https://{SourceOperatorObject.api_domain}/api/manga/{Title.slug}?" + "".join(f"fields[]={Item}&" for Item in Query).rstrip("&")
		Response = self.requestor.get(URL)

		if Response.ok and Response.json:
			return Response.json["data"]

		elif Response.status_code == 451: self.portals.request_error(Response, "Account banned.")
		elif Response.status_code == 404: self.portals.title_not_found(Title)
		else: self.portals.request_error(Response, "Unable to request title data.")

		return None

	def __GetType(self, data: dict) -> Types | None:
		"""
		Определяет тип тайтла.

		:param data: Словарь данных тайтла.
		:type data: dict
		:return: Тип тайтла.
		:rtype: Types | None
		"""

		TypesDeterminations = {
			"Манга": Types.manga,
			"Манхва": Types.manhwa,
			"Маньхуа": Types.manhua,
			"Руманга": Types.russian_comic,
			"Комикс западный": Types.western_comic,
			"OEL-манга": Types.oel
		}
		SiteType = data["type"]["label"]

		if SiteType in TypesDeterminations:
			return TypesDeterminations[SiteType]

		return None

	#==========================================================================================#
	# >>>>> ПЕРЕОПРЕДЕЛЯЕМЫЕ МЕТОДЫ <<<<< #
	#==========================================================================================#

	def _Amend(self, branch: BaseBranch, chapter: Chapter) -> str | None:
		"""
		Дополняет главу дайными о контенте.

		:param branch: Ветвь.
		:type branch: BaseBranch
		:param chapter: Глава.
		:type chapter: BaseChapter
		:return: Дополнительное необязательное сообщение о дополнении.
		:rtype: str | None
		"""

		chapter.set_slides(self.__GetSlides(branch.id, chapter))

	def _Parse(self):
		"""Получает основные данные тайтла."""

		Title = cast("Manga", self.title)

		Data = self.__GetTitleData()

		if Data:
			Title.set_id(Data["id"])
			Title.set_content_language("rus")
			Title.set_localized_name(Data["rus_name"])
			Title.set_eng_name(Data["eng_name"])

			Title.set_another_names(Data["otherNames"])
			Title.add_another_name(Data["name"])

			Title.add_cover(ImageData(Data["cover"]["default"]))
			Title.add_cover(ImageData(Data["cover"]["thumbnail"]))

			Title.set_authors(self.__GetAuthors(Data))
			Title.set_publication_year(int(Data["releaseDate"]) if Data["releaseDate"] else None)
			Title.set_description(self.__GetDescription(Data))
			Title.set_age_limit(self.__GetAgeLimit(Data))
			Title.set_type(self.__GetType(Data))
			Title.set_status(self.__GetStatus(Data))
			Title.set_is_licensed(Data["is_licensed"])

			Title.set_genres(self.__GetClassificators(Data, "genres"))
			Title.set_tags(self.__GetClassificators(Data, "tags"))
			Title.set_franchises(self.__GetClassificators(Data, "franchise"))

			self.__GetBranches()
		
	def _PreSaver(self):
		"""Запускается непосредственно перед сохранением тайтла."""

		Title = cast("Manga", self.title)

		for CurrentBranch in Title.branches:
			for CurrentChapter in CurrentBranch.chapters:
				if not self.settings.custom["add_moderation_status"]:
					CurrentChapter.extra_data.remove("moderated")
