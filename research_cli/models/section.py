"""Section-level writing data models."""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class SectionSpec:
    """Specification for a section to be written."""

    id: str  # e.g., "intro", "background", "mechanism"
    title: str  # e.g., "Introduction and Motivation"
    key_points: List[str]  # Main points to cover
    dependencies: List[str] = field(default_factory=list)  # Section IDs that must be written first
    estimated_tokens: int = 3000  # Estimated output tokens
    depth_level: str = "detailed"  # "overview", "detailed", "comprehensive"
    order: int = 0  # Order in manuscript


@dataclass
class ResearchPlan:
    """Complete research plan with section breakdown."""

    topic: str
    research_questions: List[str]
    sections: List[SectionSpec]
    total_estimated_tokens: int
    recommended_experts: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def get_section(self, section_id: str) -> Optional[SectionSpec]:
        """Get section by ID."""
        for section in self.sections:
            if section.id == section_id:
                return section
        return None

    def get_ordered_sections(self) -> List[SectionSpec]:
        """Get sections in writing order."""
        return sorted(self.sections, key=lambda s: s.order)


@dataclass
class SectionOutput:
    """Output from writing a section."""

    section_id: str
    content: str  # Markdown content
    word_count: int
    tokens_used: int
    metadata: Dict = field(default_factory=dict)


@dataclass
class WritingContext:
    """Context provided to section writer."""

    research_plan: ResearchPlan
    previous_sections: List[SectionOutput]
    section_spec: SectionSpec

    def get_section_summary(self, section_id: str) -> Optional[str]:
        """Get brief summary of previous section for context."""
        for section in self.previous_sections:
            if section.section_id == section_id:
                # Return first paragraph as summary
                lines = section.content.split('\n')
                summary_lines = []
                for line in lines:
                    if line.strip():
                        summary_lines.append(line)
                        if len(' '.join(summary_lines).split()) > 200:  # ~200 word summary
                            break
                return ' '.join(summary_lines)
        return None

    def get_all_previous_summaries(self) -> str:
        """Get summaries of all previous sections."""
        summaries = []
        for section in self.previous_sections:
            summary = self.get_section_summary(section.section_id)
            if summary:
                spec = self.research_plan.get_section(section.section_id)
                title = spec.title if spec else section.section_id
                summaries.append(f"## {title}\n{summary}")

        return "\n\n".join(summaries) if summaries else "No previous sections."


@dataclass
class IntegrationResult:
    """Result of integrating sections."""

    manuscript: str  # Complete integrated manuscript
    word_count: int
    sections_integrated: int
    changes_made: List[str] = field(default_factory=list)  # Description of integration changes
    metadata: Dict = field(default_factory=dict)
