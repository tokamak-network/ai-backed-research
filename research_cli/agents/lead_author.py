"""Lead Author agent for collaborative research and writing."""

from typing import List, Dict, Optional
from ..model_config import create_llm_for_role
from ..utils.json_repair import repair_json
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
            max_tokens=2048,
            json_mode=True
        )

        # Parse response
        data = repair_json(response.content)

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
            max_tokens=2048,
            json_mode=True
        )

        # Parse response
        data = repair_json(response.content)

        # Create task objects
        tasks = []
        fallback_assignee = coauthor_expertises[0]["id"] if coauthor_expertises else "unknown"
        for i, task_data in enumerate(data.get("tasks", [])):
            task = ResearchTask(
                id=f"task_{i+1}",
                title=task_data.get("title", f"Research task {i+1}"),
                description=task_data.get("description", ""),
                assigned_to=task_data.get("assigned_to", fallback_assignee)
            )
            tasks.append(task)

        return tasks

    async def plan_manuscript_structure(
        self,
        research_notes: CollaborativeResearchNotes,
        topic: str,
        target_journal: str,
        target_length: int = 4000,
        research_type: str = "survey",
        audience_level: str = "professional",
    ) -> ManuscriptPlan:
        """Plan manuscript structure with sections."""

        system_prompt = f"""You are an experienced academic writer in {self.expertise}.

You are planning the structure of a research manuscript for submission to: {target_journal}

Your role: Create a detailed section-by-section plan that will guide the writing process."""

        # Summarize research notes
        findings_summary = f"{len(research_notes.findings)} findings collected"
        refs_summary = f"{len(research_notes.references)} references"

        # Build reference list for the planner
        from ..utils.source_retriever import SourceRetriever
        ref_ids = {r.id for r in research_notes.references}
        refs_for_plan = SourceRetriever.format_for_prompt(research_notes.references) if research_notes.references else "No references available."

        # Research type-specific structure guidance (audience-aware)
        structure_guidance = ""
        if research_type == "survey":
            if audience_level == "beginner":
                structure_guidance = """Recommended structure for BEGINNER-FRIENDLY SURVEY:
- TL;DR (bullet points in plain language)
- Why This Matters (real-world relevance)
- What Is [Topic]? (background for non-specialists, define all terms)
- How Does It Work? (core concepts, use analogies)
- Current State of the Field (key developments, organized by theme)
- What's Next? (future directions in accessible language)
- Conclusion (key takeaways)"""
            elif audience_level == "intermediate":
                structure_guidance = """Recommended structure for INTERMEDIATE SURVEY:
- Executive Summary (1 concise paragraph, no bullets)
- Introduction (motivation, scope, why this matters now)
- Background & Key Concepts (assume basics, unpack only specialist terms in context)
- Analysis by Theme (organize surveyed works by theme, with concrete examples)
- Comparative Discussion (trade-offs, strengths, weaknesses — use prose, not lists)
- Future Directions
- Conclusion"""
            else:
                structure_guidance = """Recommended structure for SURVEY papers:
- Abstract (150-250 words)
- Introduction (motivation, scope, contributions)
- Background / Taxonomy
- Thematic Analysis sections (organize surveyed works by theme)
- Comparative Analysis / Discussion
- Future Directions
- Conclusion"""
        elif research_type == "explainer":
            if audience_level == "beginner":
                structure_guidance = """Recommended structure for BEGINNER-FRIENDLY EXPLAINER:
- TL;DR (bullet points in plain language)
- Why This Matters (real-world relevance, zero jargon)
- The Building Blocks (prerequisite concepts explained with everyday analogies BEFORE anything technical)
- How [Topic] Works (step-by-step, each step grounded in the building blocks above)
- Real-World Examples (concrete applications the reader can relate to)
- What's Next / Where This Is Heading
- Conclusion

CRITICAL: The "Building Blocks" section must come BEFORE any technical explanation.
Every difficult concept gets: (1) analogy/everyday comparison → (2) simple definition → (3) why it matters for this topic."""
            elif audience_level == "intermediate":
                structure_guidance = """Recommended structure for INTERMEDIATE EXPLAINER:
- Executive Summary (1 concise paragraph, no bullets — state the core argument)
- Introduction (what is this topic, why it matters now, what's at stake)
- Key Concepts in Context (weave specialist terms into the narrative — explain them where they naturally arise, not in a glossary)
- How It Works (technical explanation grounded in concrete examples)
- Trade-offs and Considerations (analytical prose, not pro/con lists)
- Applications / Real-World Impact
- Conclusion

CRITICAL: Do NOT create a separate definitions/glossary section. Instead, unpack specialist terms naturally within the prose where they first appear.
Use the pattern: concrete example or context first → then introduce the term as a label for what was just described."""
            else:
                structure_guidance = """Recommended structure for PROFESSIONAL EXPLAINER:
- Abstract (concise overview)
- Introduction (motivation, scope)
- Foundational Concepts (formal definitions with intuitive motivation — explain the 'why' before the 'what')
- Technical Deep-Dive (detailed mechanism/architecture, building on foundations)
- Analysis and Discussion (trade-offs, comparisons, limitations)
- Applications and Implications
- Conclusion

CRITICAL: Even for expert audiences, lead each concept section with a brief intuitive framing before formal treatment.
Never assume a concept is obvious — provide the reasoning chain that connects fundamentals to the topic."""
        elif research_type == "original":
            structure_guidance = """Recommended structure for ORIGINAL RESEARCH:
- Abstract (150-250 words)
- Introduction (problem, questions, contributions)
- Related Work
- Methodology
- Results / Analysis
- Discussion
- Conclusion"""
        else:
            structure_guidance = """Common academic structure:
- Abstract (150-250 words)
- Introduction (600-800 words)
- Background/Related Work (800-1000 words)
- Core Analysis sections
- Discussion (600-800 words)
- Conclusion (300-400 words)"""

        # Audience guidance
        audience_note = ""
        tldr_format = """
SUMMARY FORMAT: The abstract_outline MUST be a TL;DR with exactly 3-4 bullet points.
Each bullet is one concise sentence (max 20 words). No jargon. Plain language.
Write abstract_outline in EXACTLY this format:
"- Bullet one: a single clear sentence\\n- Bullet two: a single clear sentence\\n- Bullet three: a single clear sentence"

EXAMPLE (do NOT copy — write your own based on the topic):
"- Quantum computers may one day break the encryption that protects Bitcoin and other cryptocurrencies\\n- Current quantum hardware is far too weak to pose a real threat today\\n- The crypto industry is already developing quantum-resistant security measures\\n- Understanding this timeline helps investors and developers prepare for the transition"
"""
        if audience_level == "beginner":
            audience_note = (
                "\nAUDIENCE: Complete non-specialists (zero prior knowledge). Write as if explaining to a curious friend."
                "\nUse everyday language. NO math, NO formulas, NO acronyms without explanation."
                "\nEvery section must start with a plain-language hook that answers 'why should I care?'"
                f"\n{tldr_format}"
            )
        elif audience_level == "intermediate":
            audience_note = (
                "\nAUDIENCE: Educated readers with basic domain knowledge — think The Economist's science/technology coverage."
                "\nAssume familiarity with common terms in the field. Unpack specialist jargon naturally within the prose, not as separate definitions."
                "\nWrite in clear, analytical prose. No bullet-point analysis. Favor concrete examples over abstract statements."
                "\nSUMMARY FORMAT: The abstract_outline MUST be a single concise paragraph (3-5 sentences). NO bullets. State the core argument and key findings in flowing prose."
            )

        # Section count guidance based on target length
        if target_length <= 2500:
            section_count_guide = "3-5 sections"
        else:
            section_count_guide = "5-7 sections"

        prompt = f"""Plan the structure for a research manuscript on: "{topic}"

RESEARCH NOTES SUMMARY:
- Research Questions: {len(research_notes.research_questions)}
- Findings: {findings_summary}
- References: {refs_summary}

TARGET:
- Journal: {target_journal}
- Length: {target_length} words
- Paper type: {research_type}{audience_note}

CRITICAL LENGTH CONSTRAINT:
- Total word count across ALL sections MUST NOT exceed {target_length} words.
- Use {section_count_guide} (NOT more).
- Each section's target_length must be planned so the SUM equals {target_length}.
- Example budget for {target_length} words with 4 sections: {target_length // 4} words each.
- Double-check: add up all section target_lengths before responding. The total MUST equal {target_length}.

AVAILABLE REFERENCES (assign these to sections via relevant_references):
{refs_for_plan}

Create a detailed manuscript plan with {section_count_guide}. For each section specify:
1. Title and order
2. Purpose (what this section accomplishes)
3. Key points to cover (3-5 points)
4. Target length in words
5. Subsection titles (2-4 subsections)
6. relevant_references: list of reference IDs (integers) that this section should cite

{structure_guidance}

Adapt this structure to your specific research.

Return JSON:
{{
  "title": "Manuscript title",
  "abstract_outline": "Write the actual abstract (150-250 words). NOT a description of what it should cover — write the abstract itself as it would appear in the published paper.",
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
      "subsections": ["Background", "Motivation", "Contributions"],
      "relevant_references": [1, 3, 5]
    }}
  ]
}}"""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=4096,
            json_mode=True
        )

        # Parse response
        data = repair_json(response.content)

        # Create plan object
        sections = []
        for idx, sec_data in enumerate(data.get("sections", []), 1):
            # Parse relevant_references, filtering to valid IDs
            raw_refs = sec_data.get("relevant_references", [])
            valid_refs = [int(r) for r in raw_refs if isinstance(r, (int, float)) and int(r) in ref_ids] if raw_refs else []

            section = SectionSpec(
                id=sec_data.get("id", f"section_{idx}"),
                title=sec_data.get("title", f"Section {idx}"),
                order=sec_data.get("order", idx),
                purpose=sec_data.get("purpose", ""),
                key_points=sec_data.get("key_points", []),
                target_length=sec_data.get("target_length", 500),
                subsections=sec_data.get("subsections", []),
                relevant_references=valid_refs,
            )
            sections.append(section)

        # Fallback: if LLM omitted relevant_references for all sections,
        # distribute available refs round-robin so every section has some
        if sections and not any(s.relevant_references for s in sections) and ref_ids:
            sorted_refs = sorted(ref_ids)
            for i, ref_id in enumerate(sorted_refs):
                sections[i % len(sections)].relevant_references.append(ref_id)

        plan = ManuscriptPlan(
            title=data.get("title", "Untitled"),
            abstract_outline=data.get("abstract_outline", ""),
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

        total_planned = sum(s.target_length for s in original_plan.sections)
        prompt = f"""You proposed the following manuscript plan for: "{topic}"

ORIGINAL PLAN:

Title: {original_plan.title}

Overall Narrative: {original_plan.overall_narrative}

Target Length: {original_plan.target_length} words (current plan total: {total_planned} words)

Sections:
{chr(10).join(f"  {s.order}. {s.title} ({s.target_length} words) - {s.purpose}  [refs: {s.relevant_references}]" for s in original_plan.sections)}

CO-AUTHOR FEEDBACK:
{feedback_text}

---

CRITICAL LENGTH CONSTRAINT:
- The TOTAL word count across ALL sections MUST NOT exceed {original_plan.target_length} words.
- If a co-author suggests adding a section, you MUST shrink or merge other sections to stay within budget.
- Do NOT increase the total. The sum of all section target_lengths must equal {original_plan.target_length}.
- REJECT any suggestion that would inflate the manuscript beyond the target length.

As lead author, review all feedback and make your final decisions:

1. For each suggestion, decide: ACCEPT, MODIFY, or REJECT
2. Provide reasoning for your decisions
3. Output the FINAL plan (which may be unchanged or updated)
4. VERIFY: add up all section target_lengths — the total MUST equal {original_plan.target_length}

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
        "subsections": ["Subsection1", "Subsection2"],
        "relevant_references": [1, 3, 5]
      }}
    ]
  }}
}}"""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=4096,
            json_mode=True
        )

        # Parse response
        try:
            data = repair_json(response.content)
        except ValueError:
            # If parsing fails even after repair, return original plan
            return original_plan

        # Extract final plan
        final_plan_data = data.get("final_plan", {})

        # Collect valid ref IDs from original plan
        original_ref_ids = set()
        for s in original_plan.sections:
            original_ref_ids.update(s.relevant_references)

        # Create section specs
        sections = []
        for idx, sec_data in enumerate(final_plan_data.get("sections", []), 1):
            # Parse relevant_references, filtering to valid IDs
            raw_refs = sec_data.get("relevant_references", [])
            # If original plan had refs, validate against them; otherwise accept any int
            if original_ref_ids:
                valid_refs = [int(r) for r in raw_refs if isinstance(r, (int, float)) and int(r) in original_ref_ids] if raw_refs else []
            else:
                valid_refs = [int(r) for r in raw_refs if isinstance(r, (int, float))] if raw_refs else []

            # Fallback: try to inherit from matching original section (by id or position)
            if not valid_refs:
                sec_id = sec_data.get("id", f"section_{idx}")
                orig = next((s for s in original_plan.sections if s.id == sec_id), None)
                if not orig and idx <= len(original_plan.sections):
                    orig = original_plan.sections[idx - 1]  # positional fallback
                if orig:
                    valid_refs = orig.relevant_references

            section = SectionSpec(
                id=sec_data.get("id", f"section_{idx}"),
                title=sec_data.get("title", f"Section {idx}"),
                order=sec_data.get("order", idx),
                purpose=sec_data.get("purpose", ""),
                key_points=sec_data.get("key_points", []),
                target_length=sec_data.get("target_length", 500),
                subsections=sec_data.get("subsections", []),
                relevant_references=valid_refs,
            )
            sections.append(section)

        # If no sections parsed, keep original
        if not sections:
            sections = original_plan.sections

        # Hard clamp: if LLM inflated the total, proportionally scale down
        total_planned = sum(s.target_length for s in sections)
        target = original_plan.target_length
        if total_planned > target * 1.1:  # Allow 10% tolerance
            scale = target / total_planned
            for s in sections:
                s.target_length = max(100, int(s.target_length * scale))

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
        manuscript_plan: ManuscriptPlan,
        audience_level: str = "professional",
    ) -> SectionDraft:
        """Write a single manuscript section."""

        # Audience-specific system prompts
        if audience_level == "beginner":
            system_prompt = f"""You are a world-class science communicator (think Kurzgesagt or Vox explainers) in {self.expertise}.

Your specializations: {', '.join(self.focus_areas)}

You are writing for someone with ZERO background knowledge. Imagine explaining to a curious friend over coffee.

RULES:
- NO math formulas, NO equations, NO Greek letters
- NO unexplained acronyms — always spell out first, then abbreviate: "Proof of Stake (PoS)"
- Use everyday analogies: "think of it like a digital lock", "imagine a library where..."
- Short paragraphs (3-4 sentences max)
- Use "Key Takeaway" boxes (blockquote format) at the end of each major point
- Bullet-point summaries are encouraged for comparisons
- Start each section with a hook: why should the reader care?
- Numbered citations [1], [2] are fine but keep them minimal and unobtrusive
- Never use "..." or ellipsis to abbreviate content
- Write at a reading level that a high-school student could follow"""
        elif audience_level == "intermediate":
            system_prompt = f"""You are an expert analyst writing in the style of The Economist's science and technology coverage, specializing in {self.expertise}.

Your specializations: {', '.join(self.focus_areas)}

You are writing for educated readers who have basic domain knowledge but are not specialists in this particular area.

RULES:
- Assume the reader knows common terms in the field — do NOT define basics like "machine learning" or "peer review"
- When introducing specialist terms, unpack them naturally in context (e.g., "the process of X — known as Y — works by...")
- Write in clear, analytical prose with well-developed paragraphs (4-6 sentences)
- Do NOT use bullet-point lists for analysis or discussion — use flowing prose
- Ground abstract claims in concrete examples: name specific studies, tools, institutions, or events
- Numbered citations [1], [2] for key claims — aim for moderate density (more than beginner, less than academic)
- Use precise but accessible language — avoid both oversimplification and unnecessary jargon
- Never use "..." or ellipsis to abbreviate content"""
        else:
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

        # Get relevant findings (fallback: all findings if none assigned)
        if section_spec.relevant_findings:
            relevant_findings = [
                f for f in research_notes.findings
                if f.id in section_spec.relevant_findings
            ]
        else:
            relevant_findings = research_notes.findings
        findings_text = ""
        if relevant_findings:
            findings_text = "\n\nRELEVANT RESEARCH FINDINGS:\n"
            for finding in relevant_findings:
                findings_text += f"\n- **{finding.title}**\n"
                findings_text += f"  {finding.description}\n"
                findings_text += f"  Evidence: {finding.evidence}\n"
                findings_text += f"  Citations: [{','.join(map(str, finding.citations))}]\n"

        # Get relevant references (fallback: all references if none assigned)
        if section_spec.relevant_references:
            relevant_refs = [
                r for r in research_notes.references
                if r.id in section_spec.relevant_references
            ]
        else:
            relevant_refs = research_notes.references
        refs_text = ""
        if relevant_refs:
            refs_text = "\n\nAVAILABLE REFERENCES — ONLY cite from this list using [ID] format:\n"
            for ref in relevant_refs:
                authors = ", ".join(ref.authors[:3])
                if len(ref.authors) > 3:
                    authors += " et al."
                refs_text += f"\n[{ref.id}] {authors} ({ref.year}). {ref.title}. {ref.venue}.\n"
                if ref.summary:
                    refs_text += f"    Summary: {ref.summary}\n"
            refs_text += "\nCRITICAL: Use ONLY the reference IDs above (e.g. [1], [5]). Do NOT invent new references or citation numbers."

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
{self._get_writing_instructions(audience_level, section_spec.target_length)}

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
        research_notes: CollaborativeResearchNotes,
        audience_level: str = "professional",
    ) -> Manuscript:
        """Integrate all sections into complete manuscript."""

        # Combine sections in original order (already ordered by spec.order)
        sections_content = []
        for section in sections:
            sections_content.append(section.content)

        main_content = "\n\n---\n\n".join(sections_content)

        # Collect all citation IDs actually used in section text
        all_citations = set()
        for s in sections:
            all_citations.update(s.citations)

        # Filter references to only those cited in the body (eliminates ghost refs)
        cited_refs = [r for r in research_notes.references if r.id in all_citations]

        # Format references section with cited refs only
        refs_section = self._format_references(cited_refs)

        # Calculate totals
        total_words = sum(s.word_count for s in sections)

        # Extract abstract: from dedicated section, or fall back to plan outline
        abstract = ""
        if sections and sections[0].id == "abstract":
            abstract = sections[0].content
        elif plan.abstract_outline:
            abstract = plan.abstract_outline

        # For beginner audience, ensure TL;DR is bullet-point format
        if audience_level == "beginner" and abstract:
            abstract = await self._ensure_bullet_format(abstract)

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

    async def _ensure_bullet_format(self, text: str) -> str:
        """Ensure text is in bullet-point format (3-5 bullets).

        If the text already contains bullet points, return as-is.
        Otherwise, use LLM to convert it to concise bullet points.
        """
        import re
        # Count lines starting with "- " or "* " (bullet markers)
        lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
        bullet_lines = [l for l in lines if re.match(r'^[-*•]\s', l)]
        if len(bullet_lines) >= 3:
            return text  # Already in bullet format

        # Convert via LLM
        response = await self.llm.generate(
            prompt=(
                "Convert the following text into EXACTLY 3-5 bullet points. "
                "Each bullet should be one concise sentence (max 20 words). "
                "Use plain language, no jargon. Start each bullet with '- '.\n\n"
                f"Text:\n{text}\n\n"
                "Output ONLY the bullet points, nothing else."
            ),
            system="You convert text into concise bullet points. Output only bullet lines starting with '- '.",
            temperature=0.3,
            max_tokens=512,
        )

        result = response.content.strip()
        # Validate the LLM actually returned bullets
        result_lines = [l.strip() for l in result.split('\n') if l.strip()]
        result_bullets = [l for l in result_lines if re.match(r'^[-*•]\s', l)]
        if len(result_bullets) >= 3:
            return '\n'.join(result_bullets)

        # Fallback: return original if conversion failed
        return text

    def _get_writing_instructions(self, audience_level: str, target_length: int) -> str:
        """Return audience-appropriate writing instructions for write_section."""
        if audience_level == "beginner":
            return f"""1. Write as if explaining to a smart friend with NO background — zero jargon
2. NO math, NO formulas, NO equations — use plain-language descriptions instead
3. Every technical term must be explained with an everyday analogy on first use
4. Short paragraphs (3-4 sentences). Use "Key Takeaway" blockquote boxes after key points
5. Target exactly {target_length} words (±10%)
6. Bullet-point summaries encouraged for lists and comparisons
7. Start each subsection with a hook: why should the reader care about this?
8. Citations [1], [2] are fine but keep them minimal — don't interrupt the flow
9. Never use "..." to abbreviate content
10. Do NOT repeat information already covered in previous sections"""
        elif audience_level == "intermediate":
            return f"""1. Write in the analytical style of The Economist — authoritative, precise, and readable
2. Assume the reader has basic domain knowledge — skip elementary definitions
3. Unpack specialist terms naturally in context, not as glossary entries
4. Well-developed paragraphs (4-6 sentences), analytical tone, active voice
5. Target exactly {target_length} words (±10%)
6. Do NOT use bullet-point lists for analysis — use flowing prose throughout
7. Ground every major claim in a concrete example: name the study, tool, or institution
8. Citations [1], [2] at moderate density — more than beginner, less than academic
9. Never use "..." to abbreviate content
10. Do NOT repeat information already covered in previous sections"""
        else:
            return f"""1. Write in flowing academic prose — full paragraphs, not bullet lists
2. Use numbered citations [1], [2] inline where appropriate
3. Ensure smooth flow from previous sections
4. Include all specified subsections
5. Target exactly {target_length} words (±10%)
6. Provide strong evidence and specific examples
7. Maintain technical rigor
8. NEVER use bullet-point lists for analysis or discussion
9. Never use "..." to abbreviate content
10. Do NOT repeat information already covered in previous sections. Reference them instead."""

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
