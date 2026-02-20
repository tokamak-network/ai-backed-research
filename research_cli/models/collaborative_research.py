"""Models for collaborative research phase with multiple authors."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime

from ..utils.normalize_ref import normalize_title, clean_doi


@dataclass
class Reference:
    """Single reference/citation."""

    id: int
    authors: List[str]
    title: str
    venue: str
    year: int
    url: Optional[str] = None
    doi: Optional[str] = None
    summary: str = ""  # Why this is cited

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "authors": self.authors,
            "title": self.title,
            "venue": self.venue,
            "year": self.year,
            "url": self.url,
            "doi": self.doi,
            "summary": self.summary
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Reference":
        return cls(
            id=data["id"],
            authors=data["authors"],
            title=data["title"],
            venue=data["venue"],
            year=data["year"],
            url=data.get("url"),
            doi=data.get("doi"),
            summary=data.get("summary", "")
        )


@dataclass
class Finding:
    """Single research finding."""

    id: str
    title: str
    description: str
    evidence: str
    citations: List[int]  # Reference IDs
    author: str  # Who contributed this
    confidence: str  # "high", "medium", "low"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "evidence": self.evidence,
            "citations": self.citations,
            "author": self.author,
            "confidence": self.confidence,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Finding":
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            evidence=data["evidence"],
            citations=data["citations"],
            author=data["author"],
            confidence=data["confidence"],
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


@dataclass
class ResearchTask:
    """Research task assigned to co-author."""

    id: str
    title: str
    description: str
    assigned_to: str  # Author ID
    status: str = "pending"  # "pending", "in_progress", "completed"
    result: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "assigned_to": self.assigned_to,
            "status": self.status,
            "result": self.result
        }


@dataclass
class ResearchContribution:
    """Co-author's research contribution."""

    author: str
    task_id: str
    findings: List[Finding]
    references: List[Reference]
    notes: str

    def to_dict(self) -> dict:
        return {
            "author": self.author,
            "task_id": self.task_id,
            "findings": [f.to_dict() for f in self.findings],
            "references": [r.to_dict() for r in self.references],
            "notes": self.notes
        }


@dataclass
class CollaborativeResearchNotes:
    """
    Research notes - core content before manuscript writing.
    Collaborative version with multiple authors.
    """

    # Core research content
    research_questions: List[str] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)

    # Methodology
    methodology: Dict[str, Any] = field(default_factory=dict)

    # Findings (with inline citations)
    findings: List[Finding] = field(default_factory=list)

    # Open questions for further research
    open_questions: List[str] = field(default_factory=list)

    # References collected during research
    references: List[Reference] = field(default_factory=list)

    # Collaboration metadata
    contributions: List[ResearchContribution] = field(default_factory=list)

    # Research tasks
    tasks: List[ResearchTask] = field(default_factory=list)

    # Version tracking
    version: int = 1
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_finding(self, finding: Finding):
        """Add a finding to notes."""
        self.findings.append(finding)
        self.last_updated = datetime.now().isoformat()

    def add_reference(self, reference: Reference) -> Reference:
        """Add a reference to notes, deduplicating by DOI or title.

        Returns:
            The existing Reference if duplicate, otherwise the newly added one.
        """
        # Clean bogus DOIs before comparison
        reference.doi = clean_doi(reference.doi)

        # DOI-based dedup
        if reference.doi:
            doi_key = reference.doi.lower().strip()
            for existing in self.references:
                if existing.doi and existing.doi.lower().strip() == doi_key:
                    return existing

        # Title-based dedup
        norm = normalize_title(reference.title)
        if norm and norm != "untitled":
            for existing in self.references:
                if normalize_title(existing.title) == norm:
                    return existing

        self.references.append(reference)
        self.last_updated = datetime.now().isoformat()
        return reference

    def get_next_reference_id(self) -> int:
        """Get next available reference ID."""
        if not self.references:
            return 1
        return max(r.id for r in self.references) + 1

    def to_dict(self) -> dict:
        return {
            "research_questions": self.research_questions,
            "hypotheses": self.hypotheses,
            "methodology": self.methodology,
            "findings": [f.to_dict() for f in self.findings],
            "open_questions": self.open_questions,
            "references": [r.to_dict() for r in self.references],
            "contributions": [c.to_dict() for c in self.contributions],
            "tasks": [t.to_dict() for t in self.tasks],
            "version": self.version,
            "last_updated": self.last_updated
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CollaborativeResearchNotes":
        return cls(
            research_questions=data.get("research_questions", []),
            hypotheses=data.get("hypotheses", []),
            methodology=data.get("methodology", {}),
            findings=[Finding.from_dict(f) for f in data.get("findings", [])],
            open_questions=data.get("open_questions", []),
            references=[Reference.from_dict(r) for r in data.get("references", [])],
            contributions=[],  # Simplified for now
            tasks=[],  # Simplified for now
            version=data.get("version", 1),
            last_updated=data.get("last_updated", datetime.now().isoformat())
        )
