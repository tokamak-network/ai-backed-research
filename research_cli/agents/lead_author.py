"""Lead Author agent for collaborative research and writing."""

import json
from typing import List, Dict, Optional
from ..model_config import create_llm_for_role
from ..models.collaborative_research import (
    CollaborativeResearchNotes,
    Finding,
    Reference,
    ResearchTask
)
from ..models.manuscript import (
    ManuscriptPlan,
    SectionSpec,
    SectionDraft,
    Manuscript
)


class LeadAuthorAgent:
    """
    Lead author who coordinates research and writing.

    Responsibilities:
    - Create initial research notes
    - Identify research gaps and assign tasks
    - Plan manuscript structure
    - Write sections
    - Integrate contributions
    """

    def __init__(
        self,
        expertise: str,
        focus_areas: List[str],
        role: str = "lead_author"
    ):
        """Initialize lead author agent.

        Args:
            expertise: Lead's area of expertise
            focus_areas: Specific focus areas
            role: Role name for model configuration lookup
        """
        self.llm = create_llm_for_role(role)
        self.model = self.llm.model
        self.expertise = expertise
        self.focus_areas = focus_areas

    async def create_initial_research_notes(
        self,
        topic: str,
        category: str
    ) -> CollaborativeResearchNotes:
        """Create initial research notes with questions, hypotheses, methodology."""

        system_prompt = f"""You are a leading researcher in {self.expertise}.

Your specializations: {', '.join(self.focus_areas)}

You are beginning a research project. Your role is to:
1. Formulate clear research questions
2. Propose testable hypotheses
3. Outline research methodology
4. Identify what needs to be investigated

Be rigorous and specific. This will guide the entire research project."""

        prompt = f"""You are starting a research project on: "{topic}"

Target journal category: {category}

Create comprehensive initial research notes with:

1. **Research Questions** (3-5 questions)
   - What are the key questions this research should answer?
   - Make them specific, answerable, and impactful

2. **Hypotheses** (2-4 hypotheses)
   - What do you expect to find?
   - What relationships or patterns do you hypothesize?

3. **Methodology**
   - How will you investigate these questions?
   - What approaches, analyses, or frameworks will you use?
   - What data or evidence do you need?

4. **Open Questions**
   - What gaps exist in current understanding?
   - What needs further investigation?

Return your response in JSON format:
{{
  "research_questions": ["question 1", "question 2", ...],
  "hypotheses": ["hypothesis 1", "hypothesis 2", ...],
  "methodology": {{
    "approach": "...",
    "analysis_methods": ["method1", "method2"],
    "data_requirements": ["requirement1", "requirement2"]
  }},
  "open_questions": ["question 1", "question 2", ...]
}}"""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=4096
        )

        # Parse response
        try:
            data = json.loads(response.content)
        except json.JSONDecodeError:
            # Extract JSON from markdown code blocks if needed
            content = response.content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
                data = json.loads(json_str)
            else:
                raise

        # Create research notes object
        notes = CollaborativeResearchNotes(
            research_questions=data.get("research_questions", []),
            hypotheses=data.get("hypotheses", []),
            methodology=data.get("methodology", {}),
            open_questions=data.get("open_questions", [])
        )

        return notes

    async def identify_research_gaps(
        self,
        notes: CollaborativeResearchNotes,
        coauthor_expertises: List[Dict[str, str]]
    ) -> List[ResearchTask]:
        """Identify research tasks and assign to co-authors."""

        system_prompt = f"""You are the lead researcher on this project.

Your expertise: {self.expertise}

You have co-authors with the following expertise:
{chr(10).join(f"- {ca['name']}: {ca['expertise']}" for ca in coauthor_expertises)}

Your role: Identify specific research tasks that need to be done and assign them to the most suitable co-author based on their expertise."""

        prompt = f"""Based on the current research notes, identify specific research tasks that need to be completed.

CURRENT RESEARCH NOTES:

Research Questions:
{chr(10).join(f'- {q}' for q in notes.research_questions)}

Hypotheses:
{chr(10).join(f'- {h}' for h in notes.hypotheses)}

Open Questions:
{chr(10).join(f'- {q}' for q in notes.open_questions)}

---

Identify 2-4 specific research tasks that need to be completed. For each task:
1. Give it a clear title
2. Describe exactly what needs to be investigated
3. Assign it to the most suitable co-author based on their expertise

Available co-authors:
{chr(10).join(f"- {ca['id']}: {ca['name']} ({ca['expertise']})" for ca in coauthor_expertises)}

Return JSON:
{{
  "tasks": [
    {{
      "title": "Task title",
      "description": "Detailed description of what to investigate",
      "assigned_to": "coauthor_id",
      "rationale": "Why this coauthor is best suited"
    }}
  ]
}}"""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=2048
        )

        # Parse response
        try:
            data = json.loads(response.content)
        except json.JSONDecodeError:
            content = response.content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
                data = json.loads(json_str)
            else:
                raise

        # Create task objects
        tasks = []
        for i, task_data in enumerate(data.get("tasks", [])):
            task = ResearchTask(
                id=f"task_{i+1}",
                title=task_data["title"],
                description=task_data["description"],
                assigned_to=task_data["assigned_to"]
            )
            tasks.append(task)

        return tasks

    async def plan_manuscript_structure(
        self,
        research_notes: CollaborativeResearchNotes,
        topic: str,
        target_journal: str,
        target_length: int = 4000
    ) -> ManuscriptPlan:
        """Plan manuscript structure with sections."""

        system_prompt = f"""You are an experienced academic writer in {self.expertise}.

You are planning the structure of a research manuscript for submission to: {target_journal}

Your role: Create a detailed section-by-section plan that will guide the writing process."""

        # Summarize research notes
        findings_summary = f"{len(research_notes.findings)} findings collected"
        refs_summary = f"{len(research_notes.references)} references"

        prompt = f"""Plan the structure for a research manuscript on: "{topic}"

RESEARCH NOTES SUMMARY:
- Research Questions: {len(research_notes.research_questions)}
- Findings: {findings_summary}
- References: {refs_summary}

TARGET:
- Journal: {target_journal}
- Length: {target_length} words

Create a detailed manuscript plan with 5-7 sections. For each section specify:
1. Title and order
2. Purpose (what this section accomplishes)
3. Key points to cover (3-5 points)
4. Target length in words
5. Subsection titles (2-4 subsections)

Common academic structure:
- Abstract (150-250 words)
- Introduction (600-800 words)
- Background/Related Work (800-1000 words)
- Methodology (600-800 words)
- Results/Analysis (1000-1500 words)
- Discussion (600-800 words)
- Conclusion (300-400 words)

Adapt this structure to your specific research.

Return JSON:
{{
  "title": "Manuscript title",
  "abstract_outline": "Brief outline of what abstract should cover",
  "overall_narrative": "The story arc / flow of the paper",
  "target_length": {target_length},
  "sections": [
    {{
      "id": "intro",
      "title": "Introduction",
      "order": 1,
      "purpose": "Introduce the problem and motivate the research",
      "key_points": ["point1", "point2", "point3"],
      "target_length": 700,
      "subsections": ["Background", "Motivation", "Contributions"]
    }}
  ]
}}"""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=4096
        )

        # Parse response
        try:
            data = json.loads(response.content)
        except json.JSONDecodeError:
            content = response.content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
                data = json.loads(json_str)
            else:
                raise

        # Create plan object
        sections = []
        for sec_data in data.get("sections", []):
            section = SectionSpec(
                id=sec_data["id"],
                title=sec_data["title"],
                order=sec_data["order"],
                purpose=sec_data["purpose"],
                key_points=sec_data["key_points"],
                target_length=sec_data["target_length"],
                subsections=sec_data.get("subsections", [])
            )
            sections.append(section)

        plan = ManuscriptPlan(
            title=data["title"],
            abstract_outline=data["abstract_outline"],
            sections=sections,
            target_length=data.get("target_length", target_length),
            overall_narrative=data.get("overall_narrative", "")
        )

        return plan

    async def finalize_plan_with_feedback(
        self,
        original_plan: ManuscriptPlan,
        coauthor_feedbacks: List[dict],
        topic: str
    ) -> ManuscriptPlan:
        """Finalize manuscript plan by integrating co-author feedback."""

        system_prompt = f"""You are the lead researcher on this project in {self.expertise}.

You have proposed a manuscript plan and received feedback from your co-authors.
Your role is to carefully consider their feedback and make a final decision on the plan.

You have the authority to accept, modify, or reject suggestions. Make decisions that will
result in the best possible research output."""

        # Format co-author feedback
        feedback_text = ""
        for fb in coauthor_feedbacks:
            feedback_text += f"\n\n### Feedback from {fb.get('reviewer', 'Co-author')} ({fb.get('expertise', 'unknown')}):\n"
            feedback_text += f"**Strengths:** {', '.join(fb.get('strengths', []))}\n"
            feedback_text += f"**Suggestions:** {', '.join(fb.get('suggestions', []))}\n"
            if fb.get('missing_elements'):
                feedback_text += f"**Missing Elements:** {', '.join(fb.get('missing_elements', []))}\n"
            feedback_text += f"**Assessment:** {fb.get('overall_assessment', 'No assessment')}\n"

        prompt = f"""You proposed the following manuscript plan for: "{topic}"

ORIGINAL PLAN:

Title: {original_plan.title}

Overall Narrative: {original_plan.overall_narrative}

Sections:
{chr(10).join(f"  {s.order}. {s.title} ({s.target_length} words) - {s.purpose}" for s in original_plan.sections)}

CO-AUTHOR FEEDBACK:
{feedback_text}

---

As lead author, review all feedback and make your final decisions:

1. For each suggestion, decide: ACCEPT, MODIFY, or REJECT
2. Provide reasoning for your decisions
3. Output the FINAL plan (which may be unchanged or updated)

Return JSON:
{{
  "decisions": [
    {{
      "suggestion": "The suggestion text",
      "decision": "ACCEPT|MODIFY|REJECT",
      "reasoning": "Why you made this decision"
    }}
  ],
  "final_plan": {{
    "title": "Final title",
    "abstract_outline": "Final abstract outline",
    "overall_narrative": "Final narrative",
    "sections": [
      {{
        "id": "section_id",
        "title": "Section title",
        "order": 1,
        "purpose": "Section purpose",
        "key_points": ["point1", "point2"],
        "target_length": 700,
        "subsections": ["Subsection1", "Subsection2"]
      }}
    ]
  }}
}}"""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=6144
        )

        # Parse response
        try:
            data = json.loads(response.content)
        except json.JSONDecodeError:
            content = response.content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
                data = json.loads(json_str)
            else:
                # If parsing fails, return original plan
                return original_plan

        # Extract final plan
        final_plan_data = data.get("final_plan", {})

        # Create section specs
        sections = []
        for sec_data in final_plan_data.get("sections", []):
            section = SectionSpec(
                id=sec_data["id"],
                title=sec_data["title"],
                order=sec_data["order"],
                purpose=sec_data["purpose"],
                key_points=sec_data.get("key_points", []),
                target_length=sec_data.get("target_length", 500),
                subsections=sec_data.get("subsections", [])
            )
            sections.append(section)

        # If no sections parsed, keep original
        if not sections:
            sections = original_plan.sections

        final_plan = ManuscriptPlan(
            title=final_plan_data.get("title", original_plan.title),
            abstract_outline=final_plan_data.get("abstract_outline", original_plan.abstract_outline),
            sections=sections,
            target_length=original_plan.target_length,
            overall_narrative=final_plan_data.get("overall_narrative", original_plan.overall_narrative)
        )

        return final_plan

    async def write_section(
        self,
        section_spec: SectionSpec,
        research_notes: CollaborativeResearchNotes,
        previous_sections: List[SectionDraft],
        manuscript_plan: ManuscriptPlan
    ) -> SectionDraft:
        """Write a single manuscript section."""

        system_prompt = f"""You are an expert academic writer in {self.expertise}.

Your specializations: {', '.join(self.focus_areas)}

You are writing a section of a research manuscript. Write with:
- Flowing academic prose with well-developed paragraphs
- Clear topic sentences followed by evidence and analysis
- Strong evidence and specific examples
- Proper flow and logical structure
- Numbered citations [1], [2], etc. where appropriate
- NEVER bullet-point lists for analysis or discussion (lists only for technical specs/requirements)
- Never use "..." or ellipsis to abbreviate content"""

        # Summarize previous sections for context
        previous_context = ""
        if previous_sections:
            previous_context = "\n\nPREVIOUS SECTIONS (for context):\n"
            for sec in previous_sections:
                previous_context += f"\n### {sec.title} ({sec.word_count} words)\n"
                # Include first paragraph for context
                first_para = sec.content.split('\n\n')[0] if '\n\n' in sec.content else sec.content[:200]
                previous_context += f"{first_para}...\n"

        # Get relevant findings
        relevant_findings = [
            f for f in research_notes.findings
            if f.id in section_spec.relevant_findings
        ]
        findings_text = ""
        if relevant_findings:
            findings_text = "\n\nRELEVANT RESEARCH FINDINGS:\n"
            for finding in relevant_findings:
                findings_text += f"\n- **{finding.title}**\n"
                findings_text += f"  {finding.description}\n"
                findings_text += f"  Evidence: {finding.evidence}\n"
                findings_text += f"  Citations: [{','.join(map(str, finding.citations))}]\n"

        # Get relevant references
        relevant_refs = [
            r for r in research_notes.references
            if r.id in section_spec.relevant_references
        ]
        refs_text = ""
        if relevant_refs:
            refs_text = "\n\nAVAILABLE REFERENCES (use inline [1], [2] citations):\n"
            for ref in relevant_refs:
                authors = ", ".join(ref.authors[:3])
                if len(ref.authors) > 3:
                    authors += " et al."
                refs_text += f"\n[{ref.id}] {authors} ({ref.year}). {ref.title}. {ref.venue}.\n"
                if ref.summary:
                    refs_text += f"    Summary: {ref.summary}\n"

        prompt = f"""Write the "{section_spec.title}" section of the manuscript.

SECTION SPECIFICATION:
- Purpose: {section_spec.purpose}
- Target Length: {section_spec.target_length} words (±10%)
- Subsections: {', '.join(section_spec.subsections)}

Key Points to Cover:
{chr(10).join(f'  {i+1}. {p}' for i, p in enumerate(section_spec.key_points))}

OVERALL MANUSCRIPT NARRATIVE:
{manuscript_plan.overall_narrative}
{previous_context}
{findings_text}
{refs_text}

INSTRUCTIONS:
1. Write in flowing academic prose — full paragraphs, not bullet lists
2. Use numbered citations [1], [2] inline where appropriate
3. Ensure smooth flow from previous sections
4. Include all specified subsections
5. Target exactly {section_spec.target_length} words (±10%)
6. Provide strong evidence and specific examples
7. Maintain technical rigor
8. NEVER use bullet-point lists for analysis or discussion
9. Never use "..." to abbreviate content

Write the complete section in Markdown format. Start with the section title as ## heading."""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=8192
        )

        # Parse section
        content = response.content.strip()
        word_count = self._count_words(content)
        citations = self._extract_citations(content)

        section_draft = SectionDraft(
            id=section_spec.id,
            title=section_spec.title,
            content=content,
            word_count=word_count,
            citations=citations,
            author="lead",
            status="draft"
        )

        return section_draft

    async def integrate_sections(
        self,
        sections: List[SectionDraft],
        plan: ManuscriptPlan,
        research_notes: CollaborativeResearchNotes
    ) -> Manuscript:
        """Integrate all sections into complete manuscript."""

        # Combine sections in original order (already ordered by spec.order)
        sections_content = []
        for section in sections:
            sections_content.append(section.content)

        main_content = "\n\n---\n\n".join(sections_content)

        # Format references section
        refs_section = self._format_references(research_notes.references)

        # Calculate totals
        total_words = sum(s.word_count for s in sections)
        all_citations = set()
        for s in sections:
            all_citations.update(s.citations)

        # Extract abstract (first section should be abstract)
        abstract = ""
        if sections and sections[0].id == "abstract":
            abstract = sections[0].content

        manuscript = Manuscript(
            title=plan.title,
            abstract=abstract,
            content=main_content,
            references=refs_section,
            word_count=total_words,
            citation_count=len(all_citations),
            sections=sections
        )

        return manuscript

    def _format_references(self, references: List[Reference]) -> str:
        """Format references section in IEEE style."""
        from ..utils.citation_manager import CitationManager
        return CitationManager.format_references_markdown(references)

    def _count_words(self, text: str) -> int:
        """Count words in text."""
        return len(text.split())

    def _extract_citations(self, text: str) -> List[int]:
        """Extract citation numbers from text like [1], [2,3], etc."""
        import re
        citations = set()
        pattern = r'\[(\d+(?:,\d+)*)\]'
        matches = re.findall(pattern, text)
        for match in matches:
            nums = match.split(',')
            for num in nums:
                citations.add(int(num.strip()))
        return sorted(list(citations))
