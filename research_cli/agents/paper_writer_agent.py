"""Paper writer agent for writing polished papers from research notes."""

from typing import List, Optional
from ..llm import ClaudeLLM
from ..config import get_config
from ..models.research_notes import ResearchNotebook
from ..models.section import ResearchPlan, SectionOutput, WritingContext


class PaperWriterAgent:
    """AI agent that writes polished papers from research notes.

    This agent:
    - Reads raw research notes
    - Reorganizes for reader comprehension
    - Writes structured, polished sections
    - Maintains academic rigor
    """

    def __init__(self, model: str = "claude-opus-4.5"):
        """Initialize paper writer agent.

        Args:
            model: Claude model to use (Opus for quality)
        """
        config = get_config()
        llm_config = config.get_llm_config("anthropic", model)
        self.llm = ClaudeLLM(
            api_key=llm_config.api_key,
            model=llm_config.model,
            base_url=llm_config.base_url
        )
        self.model = model

    async def plan_paper_structure(
        self,
        notebook: ResearchNotebook
    ) -> ResearchPlan:
        """Plan paper structure based on research notes.

        Args:
            notebook: Research notebook with findings

        Returns:
            Research plan with section structure
        """
        from ..models.section import SectionSpec

        system_prompt = """You are a research paper author planning structure.

Your role:
- Analyze research findings
- Design logical flow for readers
- Create section outline
- Ensure narrative coherence"""

        # Get notebook stats
        stats = notebook.get_statistics()

        prompt = f"""You have completed research and taken notes. Now plan the paper structure.

RESEARCH NOTES SUMMARY:
Topic: {notebook.topic}

Research Questions:
{chr(10).join(f'- {q}' for q in notebook.research_questions)}

Research Conducted:
- {stats['literature_sources']} literature sources
- {stats['data_analyses']} data analyses
- {stats['observations']} observations
- {stats['visualizations']} visualizations created
- {stats['open_questions']} open questions remain

Key Findings (sample):
{chr(10).join(f'- {note.findings[0]}' for note in notebook.data_analysis_notes[:3] if note.findings)}

YOUR TASK:

Plan paper structure that:
1. Introduces topic clearly for readers
2. Provides necessary background
3. Presents findings logically
4. Discusses implications
5. Acknowledges limitations

Output in JSON:

{{
  "sections": [
    {{
      "id": "intro",
      "title": "Introduction",
      "key_points": ["point 1", "point 2"],
      "dependencies": [],
      "estimated_tokens": 2000,
      "depth_level": "overview",
      "order": 1,
      "research_notes_to_use": ["literature_note_1", "observation_1"]
    }}
  ]
}}

Plan 5-8 sections."""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=3072
        )

        # Parse response
        import json
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse paper plan: {e}\n{content[:200]}")

        sections = []
        for s in data["sections"]:
            spec = SectionSpec(
                id=s["id"],
                title=s["title"],
                key_points=s["key_points"],
                dependencies=s.get("dependencies", []),
                estimated_tokens=s.get("estimated_tokens", 3000),
                depth_level=s.get("depth_level", "detailed"),
                order=s.get("order", len(sections) + 1)
            )
            sections.append(spec)

        plan = ResearchPlan(
            topic=notebook.topic,
            research_questions=notebook.research_questions,
            sections=sections,
            total_estimated_tokens=sum(s.estimated_tokens for s in sections)
        )

        return plan

    async def write_section_from_notes(
        self,
        section_spec,
        notebook: ResearchNotebook,
        previous_sections: List[SectionOutput] = None
    ) -> SectionOutput:
        """Write a paper section based on research notes.

        Args:
            section_spec: Section specification
            notebook: Research notebook with findings
            previous_sections: Previously written sections

        Returns:
            Section output
        """
        system_prompt = """You are writing a research paper section.

Your role:
- Transform raw research notes into polished prose
- Organize for reader comprehension
- Maintain academic rigor
- Include evidence and citations
- Write clearly and precisely

You are writing for an educated technical audience."""

        # Extract relevant notes
        notebook_md = notebook.to_markdown()

        # Summarize previous sections
        previous_summaries = ""
        if previous_sections:
            previous_summaries = "\n\n".join([
                f"## {s.metadata.get('title', s.section_id)}\n{s.content[:500]}..."
                for s in previous_sections
            ])

        prompt = f"""Write a paper section based on your research notes.

RESEARCH NOTES:
{notebook_md}

---

PREVIOUSLY WRITTEN SECTIONS:
{previous_summaries if previous_summaries else "None (this is the first section)"}

---

SECTION TO WRITE:
Title: {section_spec.title}
Section ID: {section_spec.id}
Order: {section_spec.order}

Key Points to Cover:
{chr(10).join(f'- {p}' for p in section_spec.key_points)}

---

YOUR TASK:

Write this section by:
1. Reviewing relevant research notes above
2. Organizing information for reader comprehension
3. Writing clearly and precisely
4. Including specific evidence/data from notes
5. Referencing findings naturally
6. Maintaining logical flow

Write {section_spec.estimated_tokens//250}-{section_spec.estimated_tokens//150} words.

This is a POLISHED section for readers, not raw notes.
Use proper academic style, clear explanations, and evidence-based arguments.

Write the complete section now in markdown format."""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=16384
        )

        content = response.content
        word_count = len(content.split())

        return SectionOutput(
            section_id=section_spec.id,
            content=content,
            word_count=word_count,
            tokens_used=response.total_tokens,
            metadata={
                "title": section_spec.title,
                "order": section_spec.order,
                "depth_level": section_spec.depth_level,
                "based_on_research_notes": True
            }
        )

    async def write_paper_from_notes(
        self,
        notebook: ResearchNotebook
    ) -> List[SectionOutput]:
        """Write complete paper from research notes.

        Args:
            notebook: Research notebook

        Returns:
            List of section outputs
        """
        # 1. Plan paper structure
        plan = await self.plan_paper_structure(notebook)

        # 2. Write sections sequentially
        sections = []
        for section_spec in plan.get_ordered_sections():
            section_output = await self.write_section_from_notes(
                section_spec,
                notebook,
                previous_sections=sections
            )
            sections.append(section_output)

        return sections
