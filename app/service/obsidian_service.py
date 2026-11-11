import os
import re
import frontmatter
from pathlib import Path
from datetime import datetime, timedelta

from app.logging_config import setup_logging
from app.model.postgresdb_schema import Note, NoteSection, MasteryStage
from app.client.embedding.ollama_embedder import OllamaEmbeddingClient
from app.repository.note_repository import NoteRepository
from app.clock import today

logger = setup_logging()

class ObsidianService:
    def __init__(
        self,
        note_repo: NoteRepository | None = None,
        ollama_embedder: OllamaEmbeddingClient | None = None
    ):
        self.note_repo = note_repo or NoteRepository()
        self.ollama_embedder = ollama_embedder or OllamaEmbeddingClient()

    def _parse_sections(self, content: str) -> dict[str, str]:
        """
        Splits markdown note content into subtopic sections keyed by heading title.
        Defaults unheaded intro text to 'Overview'.
        """
        heading_pattern = re.compile(r'^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$', re.MULTILINE)
        matches = []
        fenced: str | None = None
        offset = 0
        for line in content.splitlines(keepends=True):
            fence_match = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
            if fence_match:
                fence_token = fence_match.group(1)[0]
                if fenced is None:
                    fenced = fence_token
                elif fenced == fence_token:
                    fenced = None
            if fenced is None:
                match = heading_pattern.match(line.rstrip("\r\n"))
                if match:
                    matches.append((offset, offset + match.end(), len(match.group(1)), match.group(2).strip()))
            offset += len(line)

        if not matches:
            return {"Overview": content.strip()}

        sections = {}
        intro_content = content[:matches[0][0]].strip()
        if intro_content:
            sections["Overview"] = intro_content
        hierarchy: list[tuple[int, str]] = []
        for i, (heading_start, heading_end, level, title) in enumerate(matches):
            hierarchy = [(depth, name) for depth, name in hierarchy if depth < level]
            hierarchy.append((level, title))
            heading_title = " › ".join(name for _, name in hierarchy)
            start_pos = heading_end
            end_pos = matches[i + 1][0] if i + 1 < len(matches) else len(content)
            body = content[start_pos:end_pos].strip()
            if heading_title in sections:
                suffix = 2
                while f"{heading_title} ({suffix})" in sections:
                    suffix += 1
                heading_title = f"{heading_title} ({suffix})"
            sections[heading_title] = body

        return sections

    def handle_note_created(self, note_path: Path | str):
        """Handle creation of a new Obsidian note, parsing subtopics and generating section embeddings."""
        note_path = Path(note_path)
        logger.info(f"Handling note creation for {note_path}")

        existing_note = self.note_repo.fetch_note_by_file_path(str(note_path))
        if existing_note:
            logger.info(f"Note {note_path} already exists in DB. Delegating to modification handler.")
            self.handle_note_modified(note_path)
            return

        note_metadata = self._extract_metadata_from_notes(str(note_path))
        note_content = self._extract_content_from_notes(str(note_path))

        title, topic, tags = self._clean_metadata(note_metadata, note_path.stem)

        note_model = Note(
            title=title,
            topic=topic,
            tags=tags,
            file_path=str(note_path),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            status="active",
        )

        note_id = self.note_repo.add_note(note_model)
        if not note_id:
            logger.error(f"Failed to create note record for {note_path}")
            return

        # Parse sections and save each as NoteSection
        sections = self._parse_sections(note_content)
        for heading, body in sections.items():
            embedding = self.ollama_embedder.get_document_embedding(f"{heading}\n{body}")
            section_model = NoteSection(
                note_id=note_id,
                heading=heading,
                content=body,
                review_stage=MasteryStage.NOVICE,
                mastery_score=MasteryStage.NOVICE.stage_weight,
                next_review_date=today() + timedelta(days=MasteryStage.NOVICE.interval_days),
                embedding=embedding,
                embedding_model=self.ollama_embedder.model,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            self.note_repo.add_section(section_model)
        logger.info(f"Successfully processed new note '{title}' with {len(sections)} section(s).")

    def sync_vault(self) -> int:
        """Index existing Markdown files before the watcher begins receiving events."""
        from app.config import watchdog_config
        root = Path(watchdog_config().vault_path)
        if not root.is_dir():
            raise ValueError(f"Vault folder path does not exist: {root}")
        indexed = 0
        failed = 0
        for path in root.rglob("*.md"):
            if any(part.startswith(".") for part in path.relative_to(root).parts):
                continue
            try:
                self.handle_note_created(path)
                indexed += 1
            except Exception:
                failed += 1
                logger.exception("Could not index vault file %s", path)
        logger.info("Vault reconciliation completed: %s processed, %s failed", indexed, failed)
        return indexed

    def handle_note_modified(self, note_path: Path | str):
        """Handle modification of an Obsidian note by detecting subtopic changes/additions."""
        note_path = Path(note_path)
        logger.info(f"Handling note modification for {note_path}")
        note = self.note_repo.fetch_note_by_file_path(str(note_path))
        if not note or note.id is None:
            logger.warning(f"Note at {note_path} not found in DB. Treating as new note creation.")
            self.handle_note_created(note_path)
            return

        updated_note_content = self._extract_content_from_notes(str(note_path))
        existing_sections = self.note_repo.fetch_sections_by_note_id(note.id)
        existing_by_heading = {sec.heading: sec for sec in existing_sections}

        new_sections = self._parse_sections(updated_note_content)

        for heading, old_section in existing_by_heading.items():
            if heading not in new_sections and old_section.section_id is not None:
                self.note_repo.db.delete("note_sections", "section_id = %s", (old_section.section_id,))

        for heading, body in new_sections.items():
            if heading in existing_by_heading:
                # Subtopic already exists: evaluate similarity & demotion steps
                old_sec = existing_by_heading[heading]
                if (old_sec.content or "") == body:
                    continue
                new_embedding = self.ollama_embedder.get_document_embedding(f"{heading}\n{body}")
                eval_res = self.ollama_embedder.evaluate_subtopic_similarity(old_sec.embedding, new_embedding)
                similarity = eval_res["similarity"]
                demotion_steps = eval_res["demotion_steps"]

                logger.info(f"Subtopic '{heading}' similarity: {similarity:.4f}, Action: {eval_res['action']}")

                # Update section content and embedding
                old_sec.content = body
                old_sec.embedding = new_embedding
                old_sec.embedding_model = self.ollama_embedder.model
                old_sec.updated_at = datetime.now()

                if demotion_steps > 0:
                    new_stage = self._demote_stage_by(old_sec.review_stage, demotion_steps)
                    old_sec.review_stage = new_stage
                    old_sec.mastery_score = new_stage.stage_weight
                    old_sec.next_review_date = today() + timedelta(days=new_stage.interval_days)
                    logger.info(f"Subtopic '{heading}' modified. Demoted {demotion_steps} step(s) -> {new_stage.value}.")

                self.note_repo.update_section(old_sec)
            else:
                # NEW subtopic added!
                new_embedding = self.ollama_embedder.get_document_embedding(f"{heading}\n{body}")
                logger.info(f"New subtopic '{heading}' detected. Adding at NOVICE stage.")
                new_sec = NoteSection(
                    note_id=note.id,
                    heading=heading,
                    content=body,
                    review_stage=MasteryStage.NOVICE,
                    mastery_score=MasteryStage.NOVICE.stage_weight,
                    next_review_date=today() + timedelta(days=MasteryStage.NOVICE.interval_days),
                    embedding=new_embedding,
                    embedding_model=self.ollama_embedder.model,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                self.note_repo.add_section(new_sec)

        metadata = self._extract_metadata_from_notes(str(note_path))
        title, topic, tags = self._clean_metadata(metadata, note_path.stem)
        self.note_repo.update_note_metadata(
            note.id, title=title, topic=topic, tags=tags,
        )

    def _clean_metadata(self, metadata: dict | None, fallback_title: str) -> tuple[str, str, list[str]]:
        """Extract and sanitize title, topic, and tags from raw frontmatter metadata."""
        meta = metadata if isinstance(metadata, dict) else {}
        raw_title = meta.get("title")
        title = (str(raw_title).strip() if raw_title is not None else "") or fallback_title

        raw_topic = meta.get("topic")
        topic = (str(raw_topic).strip() if raw_topic is not None else "") or "General"

        raw_tags = meta.get("tags")
        if isinstance(raw_tags, list):
            tags = [str(t).strip() for t in raw_tags if t is not None and str(t).strip()]
        elif isinstance(raw_tags, str) and raw_tags.strip():
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        else:
            tags = []

        return title, topic, tags

    def _demote_stage_by(self, current_stage: MasteryStage, steps: int) -> MasteryStage:
        """Demotes a stage by a given number of steps, clamping at NOVICE."""
        stage_order = [
            MasteryStage.NOVICE,
            MasteryStage.APPRENTICE,
            MasteryStage.PRACTITIONER,
            MasteryStage.ADEPT,
            MasteryStage.SCHOLAR,
            MasteryStage.EXPERT,
            MasteryStage.MASTER,
        ]
        if steps >= 999:
            return MasteryStage.NOVICE
        current_idx = stage_order.index(current_stage)
        new_idx = max(0, current_idx - steps)
        return stage_order[new_idx]

    def _extract_metadata_from_notes(self, file_path: str) -> dict:
        """Extract metadata from an Obsidian note frontmatter."""
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path}")
            return {}

        try:
            post = frontmatter.load(file_path)
            return post.metadata if isinstance(post.metadata, dict) else {}
        except Exception as e:
            logger.warning(f"Error extracting metadata from {file_path}: {e}")
            return {}

    def _extract_content_from_notes(self, file_path: str) -> str:
        """Extract content from an Obsidian Note."""
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path}")
            return ""

        try:
            post = frontmatter.load(file_path)
            return post.content or ""
        except Exception as e:
            logger.warning(f"Error extracting content from {file_path}: {e}. Falling back to raw file read.")
            try:
                return Path(file_path).read_text(encoding="utf-8", errors="replace")
            except Exception as read_err:
                logger.error(f"Error reading raw content from {file_path}: {read_err}")
                return ""

    def handle_note_deleted(self, note_path: Path | str):
        """Handle deletion of a note."""
        note_path = Path(note_path)
        logger.info(f"Handling note deletion for {note_path}")
        note = self.note_repo.fetch_note_by_file_path(str(note_path))
        if note and note.id is not None:
            # Foreign key ON DELETE CASCADE automatically removes note_sections and review_history rows
            self.note_repo.db.delete("notes", "note_id = %s", (note.id,))
            logger.info(f"Successfully deleted note record ID {note.id} for {note_path}")

