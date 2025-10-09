"""Specialized repository classes for HTBase domain models.

Each repository extends BaseRepository and adds domain-specific query methods.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Any

from sqlalchemy import desc, delete, select, update

from .base_repository import BaseRepository
from .models import (
    ArchiveArtifact,
    ArchivedUrl,
    ArticleEntity,
    ArticleSummary,
    ArticleTag,
    CommandExecution,
    CommandOutputLine,
    UrlMetadata,
)
from .schemas import ArtifactSchema, ArtifactStatus


class ArchivedUrlRepository(BaseRepository[ArchivedUrl]):
    """Repository for archived URL records."""

    model_class = ArchivedUrl

    def get_by_url(self, url: str) -> Optional[ArchivedUrl]:
        """Get archived URL by its URL string.

        Args:
            url: URL to look up

        Returns:
            ArchivedUrl or None if not found
        """
        with self._get_session() as session:
            return (
                session.execute(
                    select(ArchivedUrl).where(ArchivedUrl.url == url)
                )
                .scalars()
                .first()
            )

    def get_by_url_session(self, session, url: str) -> Optional[ArchivedUrl]:
        """Get archived URL by URL within an existing session.

        For use within transactions.
        """
        return (
            session.execute(select(ArchivedUrl).where(ArchivedUrl.url == url))
            .scalars()
            .first()
        )

    def get_or_create(
        self, url: str, item_id: Optional[str] = None, name: Optional[str] = None
    ) -> ArchivedUrl:
        """Get existing or create new archived URL record.

        Also backfills item_id/name if provided and missing.

        Args:
            url: URL to get or create
            item_id: Optional item ID to set
            name: Optional name to set

        Returns:
            ArchivedUrl instance
        """
        with self._get_session() as session:
            return self._get_or_create_session(
                session, url=url, item_id=item_id, name=name
            )

    def _get_or_create_session(
        self,
        session,
        url: str,
        item_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> ArchivedUrl:
        """Get or create within an existing session."""
        row = self.get_by_url_session(session, url)
        if row is None:
            row = ArchivedUrl(url=url, item_id=item_id, name=name)
            session.add(row)
            session.flush()
        else:
            # Backfill item_id/name if missing
            changed = False
            if item_id and not row.item_id:
                row.item_id = item_id
                changed = True
            if name and not row.name:
                row.name = name
                changed = True
            if changed:
                session.flush()
        return row

    def update_total_size(self, archived_url_id: int) -> None:
        """Calculate and update total size from all artifacts.

        Args:
            archived_url_id: ID of archived URL to update
        """
        with self._get_session() as session:
            # Get all artifacts for this URL
            stmt = select(ArchiveArtifact).where(
                ArchiveArtifact.archived_url_id == archived_url_id
            )
            artifacts = session.execute(stmt).scalars().all()

            # Sum up all sizes
            total = sum(
                art.size_bytes for art in artifacts if art.size_bytes is not None
            )

            # Update the archived_urls row
            au = session.get(ArchivedUrl, archived_url_id)
            if au:
                au.total_size_bytes = total if total > 0 else None


class ArchiveArtifactRepository(BaseRepository[ArchiveArtifact]):
    """Repository for archive artifact records."""

    model_class = ArchiveArtifact

    def get_or_create(
        self,
        archived_url_id: int,
        archiver: str,
        task_id: Optional[str] = None,
    ) -> ArchiveArtifact:
        """Get existing or create new artifact record.

        Args:
            archived_url_id: Parent archived URL ID
            archiver: Archiver name
            task_id: Optional task ID

        Returns:
            ArchiveArtifact instance
        """
        with self._get_session() as session:
            return self._get_or_create_session(
                session,
                archived_url_id=archived_url_id,
                archiver=archiver,
                task_id=task_id,
            )

    def _get_or_create_session(
        self,
        session,
        archived_url_id: int,
        archiver: str,
        task_id: Optional[str] = None,
    ) -> ArchiveArtifact:
        """Get or create within an existing session."""
        art = (
            session.execute(
                select(ArchiveArtifact).where(
                    ArchiveArtifact.archived_url_id == archived_url_id,
                    ArchiveArtifact.archiver == archiver,
                )
            )
            .scalars()
            .first()
        )
        if art is None:
            art = ArchiveArtifact(
                archived_url_id=archived_url_id,
                archiver=archiver,
                task_id=task_id,
                status=ArtifactStatus.PENDING if task_id else None,
            )
            session.add(art)
            session.flush()
        else:
            if task_id:
                art.task_id = task_id
                art.status = ArtifactStatus.PENDING
                session.flush()
        return art

    def list_by_status(
        self, statuses: Sequence[str], limit: Optional[int] = None
    ) -> List[ArtifactSchema]:
        """List artifacts by status.

        Args:
            statuses: Status values to filter by
            limit: Maximum number to return

        Returns:
            List of artifact schemas with URL info
        """
        if not statuses:
            return []
        with self._get_session() as session:
            stmt = (
                select(ArchiveArtifact, ArchivedUrl)
                .join(ArchivedUrl, ArchivedUrl.id == ArchiveArtifact.archived_url_id)
                .where(ArchiveArtifact.status.in_(list(statuses)))
                .order_by(
                    ArchiveArtifact.updated_at.desc().nullslast(),
                    ArchiveArtifact.created_at.desc(),
                )
            )
            if limit:
                stmt = stmt.limit(limit)
            rows = session.execute(stmt).all()
            return [
                ArtifactSchema(
                    artifact_id=artifact.id,
                    archiver=artifact.archiver,
                    status=artifact.status,
                    task_id=artifact.task_id,
                    item_id=archived_url.item_id,
                    url=archived_url.url,
                    archived_url_id=archived_url.id,
                    success=artifact.success,
                    exit_code=artifact.exit_code,
                    saved_path=artifact.saved_path,
                    size_bytes=artifact.size_bytes,
                    created_at=artifact.created_at,
                    updated_at=artifact.updated_at,
                )
                for artifact, archived_url in rows
            ]

    def finalize_result(
        self,
        artifact_id: Optional[int] = None,
        *,
        rowid: Optional[int] = None,
        success: bool,
        exit_code: Optional[int],
        saved_path: Optional[str],
        size_bytes: Optional[int] = None,
    ) -> None:
        """Update artifact with final archiving result.

        Args:
            artifact_id: Artifact ID to update.
            rowid: Legacy alias for artifact ID (deprecated).
            success: Whether archiving succeeded.
            exit_code: Process exit code.
            saved_path: Path to saved file.
            size_bytes: Optional file size in bytes.

        Raises:
            ValueError: If neither artifact_id nor rowid is provided.
        """
        resolved_id = artifact_id if artifact_id is not None else rowid
        if resolved_id is None:
            raise ValueError("artifact_id or rowid must be provided")

        with self._get_session() as session:
            art = session.get(ArchiveArtifact, resolved_id)
            if art is None:
                return
            art.success = bool(success)
            art.exit_code = exit_code
            art.saved_path = saved_path
            art.status = ArtifactStatus.SUCCESS if success else ArtifactStatus.FAILED
            if size_bytes is not None:
                art.size_bytes = size_bytes

    def find_successful(
        self, item_id: str, url: str, archiver: str
    ) -> Optional[ArchiveArtifact]:
        """Find successful artifact for URL and archiver.

        Looks up by URL first (canonical match), then falls back to item_id.

        Args:
            item_id: Item ID
            url: URL
            archiver: Archiver name

        Returns:
            ArchiveArtifact or None if not found
        """
        with self._get_session() as session:
            # First try to find by URL (most specific match)
            au = (
                session.execute(select(ArchivedUrl).where(ArchivedUrl.url == url))
                .scalars()
                .first()
            )

            # If no URL match and item_id provided, try item_id as fallback
            if not au and item_id:
                au = (
                    session.execute(
                        select(ArchivedUrl).where(ArchivedUrl.item_id == item_id)
                    )
                    .scalars()
                    .first()
                )
                # But if we matched by item_id, verify the URL also matches
                if au and au.url != url:
                    return None

            if not au:
                return None

            art = (
                session.execute(
                    select(ArchiveArtifact).where(
                        ArchiveArtifact.archived_url_id == au.id,
                        ArchiveArtifact.archiver == archiver,
                        ArchiveArtifact.success == True,  # noqa: E712
                    )
                    .limit(1)
                )
                .scalars()
                .first()
            )
            return art

    def list_by_item_id(self, item_id: str) -> List[ArchiveArtifact]:
        """Get all artifacts for an item ID.

        Args:
            item_id: Item ID to search for

        Returns:
            List of artifacts
        """
        with self._get_session() as session:
            stmt = (
                select(ArchiveArtifact)
                .join(ArchivedUrl, ArchiveArtifact.archived_url_id == ArchivedUrl.id)
                .where(ArchivedUrl.item_id == item_id)
            )
            return list(session.execute(stmt).scalars().all())

    def list_by_url(self, url: str) -> List[ArchiveArtifact]:
        """Get all artifacts for a URL.

        Args:
            url: URL to search for

        Returns:
            List of artifacts
        """
        with self._get_session() as session:
            stmt = (
                select(ArchiveArtifact)
                .join(ArchivedUrl, ArchiveArtifact.archived_url_id == ArchivedUrl.id)
                .where(ArchivedUrl.url == url)
            )
            return list(session.execute(stmt).scalars().all())

    def list_by_task_id(self, task_id: str) -> List[Dict[str, Any]]:
        """Get all artifacts for a task.

        Args:
            task_id: Task ID to search for

        Returns:
            List of artifact dicts with URL info
        """
        with self._get_session() as session:
            stmt = (
                select(ArchiveArtifact, ArchivedUrl)
                .join(ArchivedUrl, ArchiveArtifact.archived_url_id == ArchivedUrl.id)
                .where(ArchiveArtifact.task_id == task_id)
                .order_by(ArchiveArtifact.id.asc())
            )
            rows = session.execute(stmt).all()
            out: List[Dict[str, Any]] = []
            for art, au in rows:
                created_val = getattr(art, "created_at", None)
                created_at = (
                    created_val.isoformat()
                    if hasattr(created_val, "isoformat")
                    else created_val
                )
                out.append(
                    {
                        "rowid": art.id,
                        "item_id": au.item_id,
                        "user_id": None,
                        "url": au.url,
                        "success": 1 if art.success else 0,
                        "exit_code": art.exit_code,
                        "saved_path": art.saved_path,
                        "created_at": created_at,
                        "status": art.status,
                        "task_id": art.task_id,
                        "name": au.name,
                    }
                )
            return out

    def list_with_pagination(
        self, limit: int = 200, offset: int = 0
    ) -> List[tuple[ArchiveArtifact, ArchivedUrl]]:
        """List artifacts with URL info and pagination.

        Args:
            limit: Maximum number to return
            offset: Number to skip

        Returns:
            List of (artifact, archived_url) tuples
        """
        with self._get_session() as session:
            stmt = (
                select(ArchiveArtifact, ArchivedUrl)
                .join(ArchivedUrl, ArchiveArtifact.archived_url_id == ArchivedUrl.id)
                .order_by(desc(ArchiveArtifact.created_at), desc(ArchiveArtifact.id))
                .limit(int(max(1, limit)))
                .offset(int(max(0, offset)))
            )
            return list(session.execute(stmt).all())

    def get_size_stats(self, archived_url_id: int) -> Dict[str, Any]:
        """Get size statistics for an archived URL.

        Args:
            archived_url_id: Archived URL ID

        Returns:
            Dict with total_size_bytes and artifact details
        """
        with self._get_session() as session:
            au = session.get(ArchivedUrl, archived_url_id)
            if not au:
                return {"total_size_bytes": None, "artifacts": []}

            stmt = select(ArchiveArtifact).where(
                ArchiveArtifact.archived_url_id == archived_url_id
            )
            artifacts = session.execute(stmt).scalars().all()

            artifact_sizes = [
                {
                    "archiver": art.archiver,
                    "size_bytes": art.size_bytes,
                    "saved_path": art.saved_path,
                }
                for art in artifacts
            ]

            return {
                "total_size_bytes": au.total_size_bytes,
                "artifacts": artifact_sizes,
            }


class UrlMetadataRepository(BaseRepository[UrlMetadata]):
    """Repository for URL metadata records."""

    model_class = UrlMetadata

    def get_by_archived_url(self, archived_url_id: int) -> Optional[UrlMetadata]:
        """Get metadata for an archived URL.

        Args:
            archived_url_id: Archived URL ID

        Returns:
            UrlMetadata or None
        """
        with self._get_session() as session:
            stmt = select(UrlMetadata).where(
                UrlMetadata.archived_url_id == archived_url_id
            )
            return session.execute(stmt).scalars().first()

    def upsert(self, artifact_id: int, data: Dict[str, Any]) -> int:
        """Upsert metadata for an artifact's URL.

        Args:
            artifact_id: Artifact ID (to resolve archived_url_id)
            data: Metadata dictionary

        Returns:
            Metadata ID
        """
        with self._get_session() as session:
            art = session.get(ArchiveArtifact, artifact_id)
            if art is None:
                raise ValueError("artifact not found")
            au_id = art.archived_url_id

            row = (
                session.execute(
                    select(UrlMetadata).where(UrlMetadata.archived_url_id == au_id)
                )
                .scalars()
                .first()
            )
            payload = dict(
                archived_url_id=au_id,
                source_url=data.get("source_url"),
                title=data.get("title"),
                byline=data.get("byline"),
                site_name=data.get("site_name"),
                description=data.get("description"),
                published=data.get("published"),
                language=data.get("language"),
                canonical_url=data.get("canonical_url"),
                top_image=data.get("top_image"),
                favicon=data.get("favicon"),
                keywords=json.dumps(data.get("keywords") or [], ensure_ascii=False),
                text=data.get("text"),
                word_count=int(data.get("word_count"))
                if data.get("word_count") is not None
                else None,
                reading_time_minutes=float(data.get("reading_time_minutes"))
                if data.get("reading_time_minutes") is not None
                else None,
            )
            if row is None:
                row = UrlMetadata(**payload)  # type: ignore[arg-type]
                session.add(row)
                session.flush()
            else:
                for k, v in payload.items():
                    setattr(row, k, v)
                session.flush()
            return int(row.id)


class ArticleSummaryRepository(BaseRepository[ArticleSummary]):
    """Repository for article summary records."""

    model_class = ArticleSummary

    def upsert(
        self,
        archived_url_id: int,
        summary_type: str,
        summary_text: str,
        bullet_points: Optional[List[Any]] = None,
        model_name: Optional[str] = None,
    ) -> int:
        """Create or update a summary.

        Args:
            archived_url_id: Archived URL ID
            summary_type: Type of summary
            summary_text: Summary text
            bullet_points: Optional bullet points
            model_name: Optional model name

        Returns:
            Summary ID
        """
        normalized_type = (summary_type or "default").strip() or "default"
        with self._get_session() as session:
            summary = (
                session.execute(
                    select(ArticleSummary).where(
                        ArticleSummary.archived_url_id == archived_url_id,
                        ArticleSummary.summary_type == normalized_type,
                    )
                )
                .scalars()
                .first()
            )
            if summary is None:
                summary = ArticleSummary(
                    archived_url_id=archived_url_id,
                    summary_type=normalized_type,
                    summary_text=summary_text,
                    bullet_points=bullet_points,
                    model_name=model_name,
                )
                session.add(summary)
            else:
                summary.summary_text = summary_text
                summary.bullet_points = bullet_points
                summary.model_name = model_name
            session.flush()
            return int(summary.id)

    def get_by_type(
        self, archived_url_id: int, summary_type: str = "default"
    ) -> Optional[ArticleSummary]:
        """Get summary by type.

        Args:
            archived_url_id: Archived URL ID
            summary_type: Type of summary

        Returns:
            ArticleSummary or None
        """
        normalized_type = (summary_type or "default").strip() or "default"
        with self._get_session() as session:
            return (
                session.execute(
                    select(ArticleSummary).where(
                        ArticleSummary.archived_url_id == archived_url_id,
                        ArticleSummary.summary_type == normalized_type,
                    )
                )
                .scalars()
                .first()
            )

    def list_for_url(self, archived_url_id: int) -> List[ArticleSummary]:
        """List all summaries for a URL.

        Args:
            archived_url_id: Archived URL ID

        Returns:
            List of summaries
        """
        with self._get_session() as session:
            stmt = (
                select(ArticleSummary)
                .where(ArticleSummary.archived_url_id == archived_url_id)
                .order_by(ArticleSummary.summary_type.asc())
            )
            return list(session.execute(stmt).scalars().all())


class ArticleTagRepository(BaseRepository[ArticleTag]):
    """Repository for article tag records."""

    model_class = ArticleTag

    def replace_tags(
        self, archived_url_id: int, tags: Sequence[Dict[str, Any]]
    ) -> int:
        """Replace all tags for a URL.

        Args:
            archived_url_id: Archived URL ID
            tags: List of tag dicts

        Returns:
            Number of tags inserted
        """
        normalized: list[ArticleTag] = []
        seen: set[tuple[str, str]] = set()
        for payload in tags:
            if not payload:
                continue
            raw_tag = str(payload.get("tag", "")).strip()
            if not raw_tag:
                continue
            raw_source = str(payload.get("source", "llm")).strip() or "llm"
            key = (raw_tag.lower(), raw_source.lower())
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                ArticleTag(
                    archived_url_id=archived_url_id,
                    tag=raw_tag,
                    source=raw_source,
                    confidence=self._coerce_float(payload.get("confidence")),
                    reason=payload.get("reason"),
                )
            )
        with self._get_session() as session:
            session.execute(
                delete(ArticleTag).where(
                    ArticleTag.archived_url_id == archived_url_id
                )
            )
            for obj in normalized:
                session.add(obj)
            session.flush()
            return len(normalized)

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        """Coerce value to float or None."""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def list_for_url(self, archived_url_id: int) -> List[ArticleTag]:
        """List all tags for a URL.

        Args:
            archived_url_id: Archived URL ID

        Returns:
            List of tags
        """
        with self._get_session() as session:
            stmt = (
                select(ArticleTag)
                .where(ArticleTag.archived_url_id == archived_url_id)
                .order_by(ArticleTag.source.asc(), ArticleTag.tag.asc())
            )
            return list(session.execute(stmt).scalars().all())


class ArticleEntityRepository(BaseRepository[ArticleEntity]):
    """Repository for article entity records."""

    model_class = ArticleEntity

    def replace_entities(
        self, archived_url_id: int, entities: Sequence[Dict[str, Any]]
    ) -> int:
        """Replace all entities for a URL.

        Args:
            archived_url_id: Archived URL ID
            entities: List of entity dicts

        Returns:
            Number of entities inserted
        """
        normalized: list[ArticleEntity] = []
        seen: set[tuple[str, Optional[str]]] = set()
        for payload in entities:
            if not payload:
                continue
            raw_entity = str(payload.get("entity", "")).strip()
            if not raw_entity:
                continue
            raw_type_value = payload.get("entity_type")
            raw_type = str(raw_type_value).strip() if raw_type_value else None
            key = (raw_entity.lower(), raw_type.lower() if raw_type else None)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                ArticleEntity(
                    archived_url_id=archived_url_id,
                    entity=raw_entity,
                    entity_type=raw_type,
                    alias=(str(payload.get("alias", "")).strip() or None),
                    reason=payload.get("reason"),
                    confidence=self._coerce_float(payload.get("confidence")),
                    validated=bool(payload.get("validated", True)),
                )
            )
        with self._get_session() as session:
            session.execute(
                delete(ArticleEntity).where(
                    ArticleEntity.archived_url_id == archived_url_id
                )
            )
            for obj in normalized:
                session.add(obj)
            session.flush()
            return len(normalized)

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        """Coerce value to float or None."""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def list_for_url(self, archived_url_id: int) -> List[ArticleEntity]:
        """List all entities for a URL.

        Args:
            archived_url_id: Archived URL ID

        Returns:
            List of entities
        """
        with self._get_session() as session:
            stmt = (
                select(ArticleEntity)
                .where(ArticleEntity.archived_url_id == archived_url_id)
                .order_by(
                    ArticleEntity.entity_type.asc().nullsfirst(),
                    ArticleEntity.entity.asc(),
                )
            )
            return list(session.execute(stmt).scalars().all())


class CommandExecutionRepository(BaseRepository[CommandExecution]):
    """Repository for command execution logging."""

    model_class = CommandExecution

    def create_execution(
        self,
        command: str,
        start_time: datetime,
        timeout: float,
        archived_url_id: Optional[int] = None,
        archiver: Optional[str] = None,
    ) -> int:
        """Create a new command execution record.

        Args:
            command: Command string
            start_time: Start timestamp
            timeout: Timeout in seconds
            archived_url_id: Optional archived URL ID
            archiver: Optional archiver name

        Returns:
            Execution ID
        """
        with self._get_session() as session:
            execution = CommandExecution(
                command=command,
                start_time=start_time,
                timeout=timeout,
                archived_url_id=archived_url_id,
                archiver=archiver,
            )
            session.add(execution)
            session.flush()
            return execution.id

    def finalize_execution(
        self,
        execution_id: int,
        end_time: datetime,
        exit_code: Optional[int],
        timed_out: bool,
    ) -> None:
        """Update execution with final results.

        Args:
            execution_id: Execution ID
            end_time: End timestamp
            exit_code: Exit code
            timed_out: Whether command timed out
        """
        with self._get_session() as session:
            stmt = (
                update(CommandExecution)
                .where(CommandExecution.id == execution_id)
                .values(
                    end_time=end_time,
                    exit_code=exit_code,
                    timed_out=timed_out,
                )
            )
            session.execute(stmt)
            session.flush()

    def append_output_line(
        self,
        execution_id: int,
        stream: str,
        line: str,
        timestamp: datetime,
        line_number: Optional[int] = None,
    ) -> None:
        """Append an output line to execution log.

        Args:
            execution_id: Execution ID
            stream: Stream name (stdout/stderr)
            line: Line text
            timestamp: Line timestamp
            line_number: Optional line number
        """
        with self._get_session() as session:
            output_line = CommandOutputLine(
                execution_id=execution_id,
                timestamp=timestamp,
                stream=stream,
                line=line,
                line_number=line_number,
            )
            session.add(output_line)
            session.flush()

    def get_output_lines(self, execution_id: int) -> List[CommandOutputLine]:
        """Get all output lines for an execution.

        Args:
            execution_id: Execution ID

        Returns:
            List of output lines in chronological order
        """
        with self._get_session() as session:
            stmt = (
                select(CommandOutputLine)
                .where(CommandOutputLine.execution_id == execution_id)
                .order_by(
                    CommandOutputLine.timestamp.asc(), CommandOutputLine.id.asc()
                )
            )
            return list(session.execute(stmt).scalars().all())

    def list_executions(
        self,
        archived_url_id: Optional[int] = None,
        archiver: Optional[str] = None,
        limit: int = 100,
    ) -> List[CommandExecution]:
        """List command executions with optional filtering.

        Args:
            archived_url_id: Optional archived URL ID filter
            archiver: Optional archiver name filter
            limit: Maximum number to return

        Returns:
            List of command executions
        """
        with self._get_session() as session:
            stmt = select(CommandExecution).order_by(
                CommandExecution.start_time.desc()
            )

            if archived_url_id is not None:
                stmt = stmt.where(
                    CommandExecution.archived_url_id == archived_url_id
                )

            if archiver is not None:
                stmt = stmt.where(CommandExecution.archiver == archiver)

            stmt = stmt.limit(limit)

            return list(session.execute(stmt).scalars().all())
