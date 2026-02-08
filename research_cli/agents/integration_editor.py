"""Integration editor for combining sections into coherent manuscript."""

from typing import List
from ..model_config import create_llm_for_role
from ..models.section import ResearchPlan, SectionOutput, IntegrationResult


class IntegrationEditorAgent:
    """AI agent that integrates individual sections into coherent manuscript.

    Adds transitions, ensures consistency, and polishes final manuscript.
    """

    def __init__(self, role: str = "integration_editor"):
        """Initialize integration editor.

        Args:
            role: Role name for model config lookup
        """
        self.llm = create_llm_for_role(role)
        self.model = self.llm.model

    async def integrate_sections(
        self,
        sections: List[SectionOutput],
        plan: ResearchPlan
    ) -> IntegrationResult:
        """Integrate individual sections into coherent manuscript.

        Args:
            sections: List of section outputs in order
            plan: Original research plan

        Returns:
            Integration result with polished manuscript
        """
        # Build concatenated sections
        section_texts = []
        for section in sections:
            title = section.metadata.get('title', section.section_id)
            section_texts.append(f"# {title}\n\n{section.content}")

        concatenated = "\n\n---\n\n".join(section_texts)

        system_prompt = """You are an expert technical editor specializing in academic research papers.

Your role:
- Integrate individual sections into a coherent whole
- Add smooth transitions between sections
- Ensure consistent terminology throughout
- Add cross-references where appropriate
- Polish for readability and flow
- Maintain technical accuracy"""

        prompt = f"""You are integrating a research paper that was written section-by-section.

RESEARCH TOPIC: {plan.topic}

CURRENT MANUSCRIPT (section-by-section):
{concatenated}

---

YOUR TASK:

Integrate these sections into a polished, coherent research paper.

Integration tasks:
1. Add smooth transitions between sections
   - Bridge paragraphs that connect ideas
   - Forward references (e.g., "We will explore this in Section 4...")
   - Backward references (e.g., "Building on the mechanism described earlier...")

2. Ensure consistency
   - Standardize terminology (e.g., always "blob transaction" not switching terms)
   - Consistent notation and symbols
   - Consistent citation style

3. Add cross-references
   - Link related concepts across sections
   - Reference figures/tables consistently

4. Polish flow
   - Remove redundancy between sections
   - Ensure logical progression
   - Smooth any abrupt transitions

5. Final touches
   - Ensure introduction properly sets up all sections
   - Ensure conclusion synthesizes all sections
   - Add "roadmap" sentences in introduction

Output the complete integrated manuscript in markdown format.

IMPORTANT: Maintain all technical content and depth. Your job is integration and polish, not rewriting."""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.5,  # Lower temperature for consistency
            max_tokens=8192
        )

        manuscript = response.content
        word_count = len(manuscript.split())

        changes = [
            "Added transitions between sections",
            "Standardized terminology",
            "Added cross-references",
            "Polished for coherence"
        ]

        return IntegrationResult(
            manuscript=manuscript,
            word_count=word_count,
            sections_integrated=len(sections),
            changes_made=changes,
            metadata={
                "integration_tokens": response.total_tokens,
                "original_word_count": sum(s.word_count for s in sections)
            }
        )

    async def quick_integrate(
        self,
        sections: List[SectionOutput]
    ) -> str:
        """Quick integration - just concatenate with minimal processing.

        Args:
            sections: List of section outputs

        Returns:
            Concatenated manuscript string
        """
        parts = []
        for section in sections:
            title = section.metadata.get('title', section.section_id)
            parts.append(f"# {title}\n\n{section.content}")

        return "\n\n".join(parts)
