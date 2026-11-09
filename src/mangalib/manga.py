from typing import TYPE_CHECKING, Literal, override

from melon.core import exceptions
from melon.core.base.formats.base_format.branch import Branch
from melon.core.base.formats.base_format.enums import Status
from melon.core.base.formats.manga.chapter import Chapter
from melon.core.base.formats.manga.enums import Type
from melon.core.base.parser.presets import BaseMangaParser
from melon.core.base.structs.image import ImageData, ImageType
from melon.sdk.html_parser import HyperTextParser

if TYPE_CHECKING:
	from collections.abc import Callable

	from melon.core.html.elements import Paragraph

	from . import SourceOperator as SourceOperator
	from .settings.custom import CustomSettingsModel as CustomSettingsModel

class Parser(BaseMangaParser["SourceOperator", "CustomSettingsModel"]):
	"""Parser."""

	@override
	def _amend(self, branch: Branch, chapter: Chapter) -> str | None:
		"""
		Amend chapter content.

		Args:
			branch (Branch): Branch.
			chapter (Any): Chapter

		Returns:
			str | None: Optional additional message about amending result.
		"""

		chapter.set_slides(self.__get_slides(branch.id, chapter))

	@override
	def _parse(self):
		"""Parse title data witchout chapters content."""

		data: dict = self.__get_title_data()

		self.title.data.set_id(data["id"])
		self.title.data.set_slug(data["slug_url"]) # Fix for using short slugs.
		self.title.data.set_content_language("rus")
		self.title.data.set_localized_name(data["rus_name"])
		self.title.data.set_eng_name(data["eng_name"])
		self.title.data.set_another_names(data["otherNames"])
		self.title.data.add_another_name(data["name"])
		self.title.data.add_cover(ImageData(data["cover"]["default"], ImageType.Cover))
		self.title.data.add_cover(ImageData(data["cover"]["thumbnail"], ImageType.Cover))
		self.title.data.set_publication_year(int(data["releaseDate"]) if data["releaseDate"] else None)
		self.title.data.set_is_licensed(data["is_licensed"])

		self.__get_authors(data)
		self.__get_description(data)
		self.__get_age_limit(data)
		self.__get_type(data)
		self.__get_status(data)
		self.__get_classificators(data, "genres")
		self.__get_classificators(data, "tags")
		self.__get_classificators(data, "franchise")

		self.__get_branches()

	@override
	def _pre_saver(self):
		"""Run before title saving in descriptive JSON file."""

		for branch in self.title.data.branches:
			for chapter in branch.chapters:
				if not self.settings.custom.add_moderation_status:
					chapter.extra_data.remove("moderated")

	def __get_age_limit(self, data: dict):
		"""
		Get age limit.

		Args:
			data (dict): Title data.
		"""

		value: str = data["ageRestriction"]["label"]
		rating_string: str = value.split(" ")[0].replace("+", "").replace("Нет", "")

		if rating_string.isdigit():
			self.title.data.set_age_limit(int(rating_string))

	def __get_authors(self, data: dict):
		"""
		Get authors.

		Args:
			data (dict): Title data.
		"""

		authors: list[str] = [author["name"] for author in data["authors"]]
		self.title.data.set_authors(authors)

	def __get_branches(self):
		"""Получает ветви контента тайтла и устанавливает их."""

		branches: dict[int, Branch] = {}
		response = self.requestor.get(f"https://{self.source_operator.api_domain}/api/manga/{self.title.data.slug}/chapters")

		if not response.ok or not response.json:
			self.portals.request_error(response, "Unable to request chapter.")

		data: list[dict] = response.json["data"]

		for chapter_data in data:

			for branch_data in chapter_data["branches"]:
				original_branch_id: int | None = branch_data.get("branch_id")
				branch_id: int = original_branch_id or int(str(self.title.data.id) + "0")

				if branch_id not in branches.keys():
					branches[branch_id] = Branch(branch_id)

				buffer = Chapter(self, chapter_data["id"])
				buffer.set_volume(chapter_data["volume"])
				buffer.set_number(chapter_data["number"])
				buffer.set_name(chapter_data["name"])
				buffer.set_is_paid("restricted_view" in branch_data and not branch_data["restricted_view"]["is_open"])
				buffer.set_workers([sub["name"] for sub in branch_data["teams"]])
				buffer.extra_data.set("moderated", False if "moderation" in branch_data else True)

				if self.settings.custom.add_free_publication_date and buffer.is_paid:
					buffer.extra_data.set("free-publication-date", branch_data["restricted_view"]["expired_at"])

				branches[branch_id].add_chapter(buffer)

		self.title.data.set_branches(tuple(branches.values()))

	def __get_description(self, data: dict):
		"""
		Get description.

		Args:
			data (dict): Title data.
		"""

		summary: dict | None = data.get("summary")

		if not summary:
			return

		description_content: list[dict] | None = summary.get("content")

		if not description_content:
			return

		html_parser = HyperTextParser(self.settings.common.pretty)
		paragraphs: list[Paragraph] = []

		for content in description_content:
			elements: list[dict] | None = content.get("content")

			if not elements:
				continue

			for element in elements:
				text: str | None = element.get("text")

				if not text or not text.strip():
					continue

				tag = html_parser.make_tag("p", text)
				paragraphs.extend(html_parser.parse_paragraphs(tag, allow_footnotes = False))

		self.title.data.set_description(paragraphs)

	def __get_classificators(self, data: dict, classificators_type: Literal["franchise", "genres", "tags"]):
		"""
		Get classificators.

		Args:
			data (dict): Title data.
			classificators_type (Literal["franchise", "genres", "tags"]): Classificator type.
		"""

		classificators: list[str] = []

		for classificator_data in data[classificators_type]:
			classificators.append(classificator_data["name"])

		if classificators_type == "franchise" and "Оригинальные работы" in classificators:
			classificators.remove("Оригинальные работы")

		setters: dict[Literal["franchise", "genres", "tags"], Callable] = {
			"franchise": self.title.data.set_franchises,
			"genres": self.title.data.set_genres,
			"tags": self.title.data.set_tags,
		}

		setters[classificators_type](classificators)

	def __get_slides(self, branch_id: int, chapter: Chapter) -> list[ImageData]:
		"""
		Get slides.

		Args:
			branch_id (int): Branch ID.
			chapter (Chapter): Chapter.

		Returns:
			list[ImageData]: Slides.

		Raises:
			exceptions.parsing.ParsingError: Missing chapter data.
		"""

		if chapter.extra_data.exists("moderated") and not chapter.extra_data.get("moderated"):
			self.portals.chapter_skipped(chapter, comment = "Not moderated.")
			return []

		params: dict[str, int | str] = {}

		if chapter.number:
			params["number"] = chapter.number
		else:
			raise exceptions.parsing.ParsingError("Missing chapter number. Unable create request params.")

		if chapter.volume:
			params["volume"] = chapter.volume
		else:
			raise exceptions.parsing.ParsingError("Missing volume. Unable create request params.")

		if branch_id != int(f"{self.title.data.id}0"):
			params["branch_id"] = branch_id

		response = self.requestor.get(f"https://{self.source_operator.api_domain}/api/manga/{self.title.data.slug}/chapter", params = params)

		if not response.ok or not response.json:
			self.portals.request_error(response, "Unable to request chapter content.")

		data: dict = response.json["data"]
		pages: list[dict] = data.get("pages", ())

		servers = self.source_operator.get_images_servers()
		images_server: str = tuple(server.domain for server in servers)[0]

		slides: list[ImageData] = []

		for slide_data in pages:
			url: str = slide_data["url"]
			url = url.replace(" ", "%20")
			url = f"https://{images_server}{url}"

			image = ImageData(url, ImageType.Slide)
			image.create_resolution(slide_data.get("width"), slide_data.get("height"))

			slides.append(image)

		return slides

	def __get_status(self, data: dict):
		"""
		Get status.

		Args:
			data (dict): Title data.
		"""

		determinations: dict[int, Status] = {
			1: Status.ongoing,
			2: Status.completed,
			3: Status.announced,
			4: Status.dropped,
			5: Status.dropped,
		}
		index: int = data["status"]["id"]

		if index in determinations:
			self.title.data.set_status(determinations[index])
		else:
			self.portals.printer.warning(f"Unknown status index: {index}.")

	def __get_title_data(self) -> dict:
		"""
		Get title data.

		Returns:
			dict: Title data.
		"""

		query: tuple[str, ...] = (
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
			"status_id",
		)

		url: str = f"https://{self.source_operator.api_domain}/api/manga/{self.title.data.slug}?" + "".join(f"fields[]={item}&" for item in query).rstrip("&")
		response = self.requestor.get(url)

		if response.ok and response.json:
			return response.json["data"]

		elif response.status_code == 451:
			self.portals.request_error(response, "Account banned.")

		self.portals.request_error(response, "Unable to request title data.")

	def __get_type(self, data: dict):
		"""
		Get title type.

		Args:
			data (dict): Title data.
		"""

		determinations: dict[str, Type] = {
			"Манга": Type.manga,
			"Манхва": Type.manhwa,
			"Маньхуа": Type.manhua,
			"Руманга": Type.russian_comic,
			"Комикс западный": Type.western_comic,
			"OEL-манга": Type.oel,
		}
		value: str = data["type"]["label"]

		if value in determinations:
			self.title.data.set_title_type(determinations[value])
		else:
			self.portals.printer.warning(f"Inknown type literal: \"{value}\".")
