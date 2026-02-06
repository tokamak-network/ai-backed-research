"""Research notes data models."""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path


@dataclass
class LiteratureNote:
    """Note from reading a paper/document."""

    source: str  # Paper title, URL, etc.
    source_type: str  # "paper", "documentation", "blog", "github"
    key_findings: List[str]
    quotes: List[str] = field(default_factory=list)
    questions_raised: List[str] = field(default_factory=list)
    relevance: str = ""  # How this relates to research question
    metadata: Dict = field(default_factory=dict)


@dataclass
class DataAnalysisNote:
    """Note from data analysis."""

    analysis_type: str  # "statistical", "comparative", "trend"
    data_source: str  # Where data came from
    raw_data: Dict  # Raw data collected
    findings: List[str]
    visualizations: List[str] = field(default_factory=list)  # Paths to generated charts
    methodology: str = ""
    limitations: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)


@dataclass
class ObservationNote:
    """General observation or insight."""

    observation: str
    supporting_evidence: List[str] = field(default_factory=list)
    implications: List[str] = field(default_factory=list)
    confidence: str = "medium"  # "low", "medium", "high"


@dataclass
class QuestionNote:
    """Research question or gap identified."""

    question: str
    why_important: str
    potential_approaches: List[str] = field(default_factory=list)
    answered: bool = False
    answer: str = ""


@dataclass
class ResearchNotebook:
    """Complete research notebook for a topic."""

    topic: str
    research_questions: List[str]

    # Notes collected
    literature_notes: List[LiteratureNote] = field(default_factory=list)
    data_analysis_notes: List[DataAnalysisNote] = field(default_factory=list)
    observations: List[ObservationNote] = field(default_factory=list)
    questions: List[QuestionNote] = field(default_factory=list)

    # Research artifacts
    artifacts_dir: Optional[Path] = None  # Directory for charts, data files, etc.

    # Metadata
    start_date: str = ""
    last_updated: str = ""
    status: str = "active"  # "active", "ready_for_paper", "completed"

    def to_markdown(self) -> str:
        """Export notebook to markdown format (raw, unpolished)."""
        lines = [f"# Research Notes: {self.topic}\n"]

        lines.append(f"**Status:** {self.status}\n")
        lines.append(f"**Last Updated:** {self.last_updated}\n\n")

        # Research Questions
        lines.append("## Research Questions\n")
        for i, q in enumerate(self.research_questions, 1):
            lines.append(f"{i}. {q}\n")
        lines.append("\n")

        # Literature Review
        if self.literature_notes:
            lines.append("## Literature Review\n\n")
            for note in self.literature_notes:
                lines.append(f"### {note.source}\n")
                lines.append(f"**Type:** {note.source_type}\n\n")

                if note.relevance:
                    lines.append(f"**Relevance:** {note.relevance}\n\n")

                lines.append("**Key Findings:**\n")
                for finding in note.key_findings:
                    lines.append(f"- {finding}\n")
                lines.append("\n")

                if note.quotes:
                    lines.append("**Quotes:**\n")
                    for quote in note.quotes:
                        lines.append(f"> {quote}\n")
                    lines.append("\n")

                if note.questions_raised:
                    lines.append("**Questions Raised:**\n")
                    for q in note.questions_raised:
                        lines.append(f"- {q}\n")
                    lines.append("\n")

        # Data Analysis
        if self.data_analysis_notes:
            lines.append("## Data Analysis\n\n")
            for note in self.data_analysis_notes:
                lines.append(f"### {note.analysis_type.title()} Analysis\n")
                lines.append(f"**Source:** {note.data_source}\n\n")

                if note.methodology:
                    lines.append(f"**Methodology:** {note.methodology}\n\n")

                lines.append("**Raw Data:**\n")
                lines.append("```json\n")
                import json
                lines.append(json.dumps(note.raw_data, indent=2))
                lines.append("\n```\n\n")

                lines.append("**Findings:**\n")
                for finding in note.findings:
                    lines.append(f"- {finding}\n")
                lines.append("\n")

                if note.visualizations:
                    lines.append("**Visualizations:**\n")
                    for viz in note.visualizations:
                        lines.append(f"![Chart]({viz})\n")
                    lines.append("\n")

                if note.limitations:
                    lines.append("**Limitations:**\n")
                    for lim in note.limitations:
                        lines.append(f"- {lim}\n")
                    lines.append("\n")

        # Observations
        if self.observations:
            lines.append("## Key Observations\n\n")
            for obs in self.observations:
                lines.append(f"**Observation** (confidence: {obs.confidence}):\n")
                lines.append(f"{obs.observation}\n\n")

                if obs.supporting_evidence:
                    lines.append("Evidence:\n")
                    for ev in obs.supporting_evidence:
                        lines.append(f"- {ev}\n")
                    lines.append("\n")

                if obs.implications:
                    lines.append("Implications:\n")
                    for imp in obs.implications:
                        lines.append(f"- {imp}\n")
                    lines.append("\n")

        # Open Questions
        if self.questions:
            lines.append("## Open Questions & Gaps\n\n")
            for q in self.questions:
                status = "✓ ANSWERED" if q.answered else "❓ OPEN"
                lines.append(f"**{status}:** {q.question}\n")
                lines.append(f"*Why important:* {q.why_important}\n\n")

                if q.answered:
                    lines.append(f"*Answer:* {q.answer}\n\n")
                elif q.potential_approaches:
                    lines.append("*Potential approaches:*\n")
                    for approach in q.potential_approaches:
                        lines.append(f"- {approach}\n")
                    lines.append("\n")

        return "".join(lines)

    def get_statistics(self) -> Dict:
        """Get notebook statistics."""
        return {
            "literature_sources": len(self.literature_notes),
            "data_analyses": len(self.data_analysis_notes),
            "observations": len(self.observations),
            "open_questions": sum(1 for q in self.questions if not q.answered),
            "answered_questions": sum(1 for q in self.questions if q.answered),
            "visualizations": sum(len(note.visualizations) for note in self.data_analysis_notes)
        }
