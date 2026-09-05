"""Inbound Telegram flow: job links -> ingestion, resumes -> profile, commands.

Extends the outbound-only Telegram integration (notifications + digest) with
an inbound message handler wired into the webhook:

- a message with a job-board URL is imported through the standard manual
  pipeline (normalize -> deduplicate -> persist) and immediately scored
  against the candidate profile;
- a long plain-text message is treated as a resume: it is parsed by
  ``ResumeParserService`` and upserted into the master candidate profile;
- ``/score``, ``/train``, ``/resume`` and ``/help`` commands give explicit
  control (scoring, feedback-based threshold suggestions, profile updates).

The service never changes runtime behaviour automatically — ``/train`` only
reports deterministic feedback statistics and threshold *suggestions*
(specs #17/#18/#32, no ML).
"""

import re
from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import UUID

import httpx

from app.core.config import settings
from app.core.exceptions import AIProviderError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.job import Job
from app.providers.jobs.jsonld import (
    extract_jobposting_blocks,
    jobposting_to_rawjob,
    stable_external_id,
    strip_html,
)
from app.repositories.application import ApplicationRepository
from app.repositories.candidate import CandidateRepository
from app.repositories.job import JobRepository, JobSourceRepository
from app.repositories.matching import MatchResultRepository
from app.schemas.candidate import CandidateProfileCreate, CandidateProfileUpdate
from app.schemas.job import RawJob
from app.services.candidate import CandidateService
from app.services.deduplication import DeduplicationService
from app.services.feedback_analytics import FeedbackAnalyticsService
from app.services.job import JobService, JobSourceService
from app.services.matching import MatchingService
from app.services.resume_parser import ResumeParserService
from app.services.threshold_advisor import ThresholdAdvisor

logger = get_logger(__name__)

# Single-user setup; mirrors scripts/init_candidate.py DEFAULT_USER_ID.
DEFAULT_USER_ID = UUID("00000000-0000-0000-0000-100000000001")

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)
_OG_RE = re.compile(
    r'<meta[^>]+property=["\']og:(?P<prop>[a-z_]+)["\'][^>]+content=["\'](?P<content>.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)

# A plain-text message at least this long (and without URLs) is treated as a
# resume. The parser itself enforces a 50-char minimum; 200 gives a reliable
# separation from short chat remarks like "спасибо".
RESUME_MIN_LENGTH = 200

HTTP_TIMEOUT_SECONDS = 20.0
HTTP_USER_AGENT = "AutoHH/1.0 (+https://github.com/103D/AutoHH)"

HELP_TEXT = (
    "🤖 AutoHH — ассистент по поиску работы\n\n"
    "Команды:\n"
    "• /score <ссылка или ID вакансии> — импортировать вакансию и оценить её\n"
    "• /train — отчёт по обратной связи и предложения по порогам\n"
    "• /resume <текст резюме> — обновить профиль кандидата\n\n"
    "Или просто:\n"
    "• киньте ссылку на вакансию — импортирую и сразу оценю;\n"
    "• вставьте текст резюме длинным сообщением — обновлю профиль."
)

UNKNOWN_COMMAND_TEXT = "Неизвестная команда. Доступно: /score, /train, /resume, /help."

_NO_PROFILE_HINT = (
    "⚠️ Профиль кандидата не найден — сначала отправьте резюме "
    "(длинным сообщением или через /resume <текст>)."
)

# Labels by MatchCategory *string value* (the model stores plain strings;
# MatchCategory is a plain class of str constants, not an Enum).
_CATEGORY_LABELS: dict[str, str] = {
    "DREAM_JOB": "🔥 Работа мечты",
    "STRETCH": "🚀 Растущая роль",
    "SOLID_MATCH": "✅ Уверенное совпадение",
    "MARKET_RESEARCH": "📊 Для изучения рынка",
    "LEARNING_OPPORTUNITY": "🎓 Чему учиться",
    "IGNORE": "💤 Пропустить",
    "NOT_ELIGIBLE": "⛔ Не проходит обязательные требования",
}


def extract_url(text: str | None) -> str | None:
    """Return the first http(s) URL in the text, or None."""
    if not text:
        return None
    match = _URL_RE.search(text)
    return match.group(0).rstrip(".,;:!?") if match else None


def _og_metadata(html: str) -> dict[str, str]:
    """Extract OpenGraph properties (title/description/site_name)."""
    meta: dict[str, str] = {}
    for match in _OG_RE.finditer(html or ""):
        value = strip_html(match.group("content")).strip()
        if value:
            meta.setdefault(match.group("prop"), value)
    return meta


def _clean_currency(value) -> str | None:
    """Keep only well-formed 3-letter uppercase currency codes."""
    text = str(value or "").strip().upper()
    return text if re.fullmatch(r"[A-Z]{3}", text) else None


def extract_job_payload(html: str | None, url: str) -> RawJob | None:
    """Build a RawJob from a vacancy page: JSON-LD first, OpenGraph fallback.

    Pure function (no network/DB) so the parsing strategy is unit-testable.
    Returns None when nothing usable could be extracted.
    """
    postings = extract_jobposting_blocks(html or "")
    if postings:
        data = jobposting_to_rawjob(postings[0], base_url=url)
        try:
            return RawJob(
                external_id=str(data["external_id"] or stable_external_id(url)),
                title=str(data["title"] or "Untitled"),
                company=str(data["company"] or "Unknown"),
                description=str(data["description"] or " "),
                url=str(data["url"] or url),
                location=data.get("location"),
                salary_min=data.get("salary_min"),
                salary_max=data.get("salary_max"),
                currency=_clean_currency(data.get("currency")),
                employment_type=data.get("employment_type"),
                work_format=data.get("work_format"),
                experience_required=data.get("experience_required"),
                published_at=data.get("published_at"),
                raw_data={"import": "telegram_link", "posting": data.get("raw_data") or {}},
            )
        except Exception as e:  # malformed structured data — fall back to OG
            logger.warning(f"Failed to build RawJob from JSON-LD for {url}: {e}")

    meta = _og_metadata(html or "")
    title = meta.get("title")
    if not title:
        raw_title = _TITLE_RE.search(html or "")
        if raw_title:
            title = strip_html(raw_title.group(1))
    if not title:
        return None

    host = urlparse(url).netloc or "unknown"
    return RawJob(
        external_id=f"url-{stable_external_id(url)}",
        title=title[:500],
        company=meta.get("site_name") or host,
        description=meta.get("description") or " ",
        url=url,
        raw_data={"import": "telegram_link", "strategy": "opengraph"},
    )


class TelegramInboundService:
    """Handles inbound Telegram messages: links, resumes and commands."""

    def __init__(self, session, ai_provider=None):
        self.session = session
        self._ai_provider = ai_provider

    # ------------------------------------------------------------------
    # Message dispatch
    # ------------------------------------------------------------------
    async def handle_message(self, text: str | None) -> str | None:
        """Dispatch one inbound message text to a flow; returns the reply."""
        stripped = (text or "").strip()
        if not stripped:
            return None

        if stripped.startswith("/"):
            parts = stripped.split(None, 1)
            command = parts[0].split("@", 1)[0].lower()  # /score@my_bot -> /score
            argument = parts[1].strip() if len(parts) > 1 else ""

            if command in ("/start", "/help"):
                return HELP_TEXT
            if command == "/score":
                return await self.handle_score_argument(argument)
            if command == "/train":
                return await self.training_digest()
            if command == "/resume":
                if not argument:
                    return "Пришлите текст резюме: /resume <текст> (или длинным сообщением)."
                return await self.ingest_resume(argument)
            return UNKNOWN_COMMAND_TEXT

        url = extract_url(stripped)
        if url:
            return await self.handle_score_argument(url)

        if len(stripped) >= RESUME_MIN_LENGTH:
            return await self.ingest_resume(stripped)

        return HELP_TEXT

    # ------------------------------------------------------------------
    # Scoring flow
    # ------------------------------------------------------------------
    async def handle_score_argument(self, argument: str) -> str:
        """/score flow: import a URL (if given) then analyze the job."""
        argument = (argument or "").strip()
        if not argument:
            return "Укажите ссылку на вакансию или её ID: /score https://..."

        try:
            job_id = UUID(argument)
        except ValueError:
            url = extract_url(argument)
            if not url:
                return "Не похоже на ссылку или ID вакансии."

            try:
                job, import_status = await self.import_job_from_url(url)
            except ValidationError as e:
                return f"⚠️ {e}"
            except httpx.HTTPError:
                logger.warning(f"Failed to download vacancy page {url}")
                return "⚠️ Не удалось загрузить страницу вакансии. Попробуйте позже."
            except NotFoundError as e:
                return f"⚠️ {e}"

            prefix = (
                "♻️ Вакансия уже была в базе"
                if import_status == "duplicate"
                else "📥 Вакансия импортирована"
            )
            return prefix + "\n\n" + await self._score_with_hints(job.id)

        return await self._score_with_hints(job_id)

    async def _score_with_hints(self, job_id: UUID) -> str:
        try:
            return await self.score_job(job_id)
        except NotFoundError:
            return _NO_PROFILE_HINT

    async def score_job(self, job_id: UUID) -> str:
        """Analyze one job against the default profile; returns formatted RU text."""
        job = await JobRepository(self.session).get(job_id)
        if job is None:
            raise NotFoundError(f"Вакансия {job_id} не найдена")

        result = await self._matching_service().analyze_job(job_id)
        return self.format_score(result, job)

    @staticmethod
    def format_score(result, job) -> str:
        """Format a MatchResultResponse-like object as a RU Telegram reply."""
        category = str(getattr(result, "recommendation", "") or "")
        label = _CATEGORY_LABELS.get(category, category or "—")
        emoji, _, title = label.partition(" ")

        lines = [f"{emoji} {job.title} — {getattr(result, 'score', '?')}/100 · {title}"]

        strong = [str(s) for s in (getattr(result, "strong_matches", None) or [])]
        if strong:
            lines.append(f"Сильные стороны: {', '.join(strong[:5])}")

        missing = [str(s) for s in (getattr(result, "missing_skills", None) or [])]
        if missing:
            lines.append(f"Чему подтянуться: {', '.join(missing[:5])}")

        failures = [str(f) for f in (getattr(result, "hard_failures", None) or [])]
        if failures:
            lines.append("Не пройдено: " + "; ".join(failures[:3]))

        reasoning = getattr(result, "reasoning_summary", None)
        if reasoning:
            lines.append("")
            lines.append(str(reasoning)[:600])

        if job.url:
            lines.append("")
            lines.append(str(job.url))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Link import
    # ------------------------------------------------------------------
    async def import_job_from_url(self, url: str) -> tuple[Job, str]:
        """Fetch a vacancy page and import it through the standard pipeline.

        Returns (job, status); status is 'created' or 'duplicate'.
        """
        html = await self._fetch_html(url)
        raw_job = extract_job_payload(html, url)
        if raw_job is None:
            raise ValidationError(
                f"Не удалось извлечь вакансию из страницы {url} — "
                "нет ни JSON-LD JobPosting, ни OpenGraph-разметки."
            )

        source = await JobSourceService(
            JobSourceRepository(self.session)
        ).get_or_create_manual_source()
        job_service = JobService(JobRepository(self.session))
        dedup_service = DeduplicationService(JobRepository(self.session))

        job, status = await job_service.ingest_raw_job(
            source.id, raw_job, dedup_service, source_type="manual"
        )
        if status == "duplicate":
            job = await JobRepository(self.session).get_by_external_id(
                source.id, raw_job.external_id
            )
        if job is None:
            raise NotFoundError(f"Вакансия {url} не найдена после импорта")
        return job, status

    async def _fetch_html(self, url: str) -> str:
        """Download a vacancy page (follow redirects; raise httpx errors)."""
        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": HTTP_USER_AGENT},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    # ------------------------------------------------------------------
    # Resume flow
    # ------------------------------------------------------------------
    async def ingest_resume(self, text: str) -> str:
        """Parse resume text and upsert the master candidate profile."""
        if len((text or "").strip()) < 50:
            return "Текст слишком короткий для разбора — пришлите полное резюме."

        parser = (
            ResumeParserService(ai_provider=self._ai_provider)
            if self._ai_provider is not None
            else ResumeParserService()
        )
        try:
            parsed = await parser.parse(text)
            profile_data = parser.to_profile_data(parsed)
        except ValidationError as e:
            return f"⚠️ Не удалось разобрать резюме: {e}"
        except AIProviderError:
            logger.error("Resume parsing failed: AI provider unavailable")
            return "⚠️ AI-провайдер недоступен, попробуйте позже."

        version_key = f"telegram_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        profile_id, created = await self._upsert_profile(
            profile_data, text, version_key, parsed
        )

        salary = "—"
        if profile_data.get("desired_salary_min") or profile_data.get("desired_salary_max"):
            salary = (
                f"{profile_data.get('desired_salary_min') or '?'}–"
                f"{profile_data.get('desired_salary_max') or '?'} "
                f"{profile_data.get('salary_currency') or ''}".strip()
            )
        skills = profile_data.get("skills") or []
        header = "✅ Профиль создан из резюме" if created else "✅ Профиль обновлён из резюме"
        lines = [
            header,
            f"Позиции: {', '.join(profile_data.get('desired_positions') or [])}",
        ]
        if profile_data.get("experience_years") is not None:
            lines.append(
                f"Опыт: {profile_data['experience_years']} лет "
                f"({profile_data.get('experience_level') or 'n/a'})"
            )
        lines.append(f"Навыки ({len(skills)}): {', '.join(str(s) for s in skills[:10])}")
        lines.append(f"Зарплата: {salary}")
        if parsed.full_name:
            lines.append(f"Имя: {parsed.full_name}")
        lines.append(f"ID профиля: {profile_id}")
        lines.append("Теперь киньте ссылку на вакансию — оценю её по этому профилю.")
        return "\n".join(lines)

    async def _upsert_profile(
        self, profile_data: dict, resume_text: str, version_key: str, parsed
    ) -> tuple[UUID, bool]:
        """Create or update the single-user master profile from parsed facts."""
        service = CandidateService(CandidateRepository(self.session))
        try:
            existing = await service.get_profile_by_user(DEFAULT_USER_ID)
        except NotFoundError:
            existing = None

        versions = dict(existing.resume_versions or {}) if existing else {}
        versions.setdefault("original", resume_text)
        versions[version_key] = resume_text
        preferences = dict(existing.additional_preferences or {}) if existing else {}
        preferences.update(
            {
                "parsed_at": datetime.now(UTC).isoformat(),
                "parsed_from": "telegram",
                "full_name": parsed.full_name,
                "summary": parsed.summary,
            }
        )
        profile_data["resume_versions"] = versions
        profile_data["additional_preferences"] = preferences

        if existing:
            await service.update_profile(existing.id, CandidateProfileUpdate(**profile_data))
            return existing.id, False

        created = await service.create_profile(
            CandidateProfileCreate(user_id=DEFAULT_USER_ID, **profile_data)
        )
        return created.id, True

    # ------------------------------------------------------------------
    # Training digest (feedback loop; read-only, no ML)
    # ------------------------------------------------------------------
    async def training_digest(self) -> str:
        """Aggregate feedback statistics and threshold suggestions."""
        report = await FeedbackAnalyticsService(
            ApplicationRepository(self.session)
        ).feedback_report()
        advisor = ThresholdAdvisor(settings.threshold_advisor_min_bucket)
        suggestion = advisor.suggest_from_response(report)
        return self.format_training_digest(report, suggestion)

    @staticmethod
    def format_training_digest(report: dict, suggestion) -> str:
        """Format a feedback report + threshold suggestion as a RU reply."""
        lines = ["🎓 Обучение: отчёт по обратной связи", ""]
        lines.append(
            f"Заявок: {report.get('total_applications', 0)} · "
            f"Ответов: {report.get('responded', 0)} ({report.get('response_rate', 0)}%) · "
            f"Интервью: {report.get('interviews', 0)} ({report.get('interview_rate', 0)}%)"
        )

        best_bucket = getattr(suggestion, "best_bucket", None)
        if best_bucket:
            lines.append(f"Лучший диапазон оценок: {best_bucket}")

        skip_below = getattr(suggestion, "suggested_skip_below", None)
        if skip_below:
            lines.append(
                f"Ниже score {skip_below} интервью не было — можно пропускать "
                "LLM-анализ (предложение, не автоприменение)."
            )

        insights = list(getattr(suggestion, "insights", None) or [])
        if insights:
            lines.append("")
            lines.extend(f"💡 {insight}" for insight in insights[:5])

        top_missing = report.get("missing_skills_on_rejection") or []
        if top_missing:
            skills = ", ".join(f"{row['name']} ({row['count']})" for row in top_missing[:5])
            lines.append("")
            lines.append(f"Чаще всего не хватает: {skills}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------
    def _matching_service(self) -> MatchingService:
        return MatchingService(
            JobRepository(self.session),
            CandidateService(CandidateRepository(self.session)),
            MatchResultRepository(self.session),
        )
