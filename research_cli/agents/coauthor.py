"""Co-author agent for collaborative research."""

from typing import List
from ..model_config import create_llm_for_role
from ..utils.json_repair import repair_json
from ..models.collaborative_research import (
    ResearchTask,
    ResearchContribution,
    Finding,
    Reference
)


class CoauthorAgent:
    """
    Co-author who contributes specialized research.

    Responsibilities:
    - Conduct research on assigned tasks
    - Contribute findings with evidence
    - Provide references
    - Review sections from their expertise
    """

    def __init__(
        self,
        author_id: str,
        name: str,
        expertise: str,
        focus_areas: List[str],
        role: str = "coauthor"
    ):
        """Initialize co-author agent.

        Args:
            author_id: Unique ID
            name: Display name
            expertise: Area of expertise
            focus_areas: Specific focus areas
            role: Role name for model configuration lookup
        """
        self.llm = create_llm_for_role(role)
        self.model = self.llm.model
        self.author_id = author_id
        self.name = name
        self.expertise = expertise
        self.focus_areas = focus_areas

    async def conduct_research(
        self,
        task: ResearchTask,
        context: dict
    ) -> ResearchContribution:
        """Conduct research on assigned task."""

        system_prompt = f"""You are an expert researcher in {self.expertise}.

Your specializations: {', '.join(self.focus_areas)}

You are contributing to a collaborative research project. Your role is to:
1. Investigate the assigned research task thoroughly
2. Find specific evidence and examples
3. Provide authoritative references
4. Document your findings clearly"""

        # Build context from research notes
        context_text = ""
        if context.get("research_questions"):
            context_text += "\n\nPROJECT RESEARCH QUESTIONS:\n"
            context_text += "\n".join(f"- {q}" for q in context["research_questions"])

        if context.get("hypotheses"):
            context_text += "\n\nPROJECT HYPOTHESES:\n"
            context_text += "\n".join(f"- {h}" for h in context["hypotheses"])

        prompt = f"""You have been assigned a research task:

TASK: {task.title}

DESCRIPTION:
{task.description}

PROJECT CONTEXT:
{context_text}

---

Conduct thorough research on this task. Provide:

1. **Findings** (3-5 key findings)
   For each finding:
   - Title: Brief descriptive title
   - Description: What you discovered
   - Evidence: Specific examples, data, or observations
   - Confidence: "high", "medium", or "low"

2. **References** (4-8 authoritative sources)
   For each reference:
   - Authors (list of names)
   - Title
   - Venue (journal/conference/book)
   - Year
   - URL or DOI (if available)
   - Brief summary of why this source is relevant

3. **Research Notes**
   - Additional observations
   - Methodological considerations
   - Limitations or caveats
   - Suggestions for further investigation

Return your research in JSON format:
{{
  "findings": [
    {{
      "title": "Finding title",
      "description": "What was discovered",
      "evidence": "Specific evidence and examples",
      "confidence": "high|medium|low"
    }}
  ],
  "references": [
    {{
      "authors": ["Author1", "Author2"],
      "title": "Paper title",
      "venue": "Journal/Conference name",
      "year": 2023,
      "url": "https://...",
      "doi": "10.1234/...",
      "summary": "Why this is relevant"
    }}
  ],
  "notes": "Additional observations and considerations..."
}}"""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=8192
        )

        # Parse response
        data = repair_json(response.content)

        # Create Finding objects
        findings = []
        for i, f_data in enumerate(data.get("findings", [])):
            finding = Finding(
                id=f"{self.author_id}_finding_{i+1}",
                title=f_data["title"],
                description=f_data["description"],
                evidence=f_data["evidence"],
                citations=[],  # Will be filled when references are assigned IDs
                author=self.name,
                confidence=f_data.get("confidence", "medium")
            )
            findings.append(finding)

        # Create Reference objects (IDs will be assigned by research notes)
        references = []
        for r_data in data.get("references", []):
            reference = Reference(
                id=0,  # Will be assigned later
                authors=r_data["authors"],
                title=r_data["title"],
                venue=r_data["venue"],
                year=r_data["year"],
                url=r_data.get("url"),
                doi=r_data.get("doi"),
                summary=r_data.get("summary", "")
            )
            references.append(reference)

        contribution = ResearchContribution(
            author=self.name,
            task_id=task.id,
            findings=findings,
            references=references,
            notes=data.get("notes", "")
        )

        return contribution

    async def provide_plan_feedback(
        self,
        plan: dict,
        topic: str
    ) -> dict:
        """Provide feedback on the manuscript plan from co-author's expertise perspective."""

        system_prompt = f"""You are an expert researcher in {self.expertise}.

Your specializations: {', '.join(self.focus_areas)}

You are reviewing a research plan proposed by the lead author. Provide constructive feedback
from your area of expertise to help improve the plan."""

        prompt = f"""Review the following research plan for: "{topic}"

PROPOSED PLAN:

Title: {plan.get('title', 'Untitled')}

Overall Narrative: {plan.get('overall_narrative', 'Not specified')}

Sections:
{chr(10).join(f"  {i+1}. {s.get('title', 'Untitled')} ({s.get('target_length', 0)} words) - {s.get('purpose', 'No purpose specified')}" for i, s in enumerate(plan.get('sections', [])))}

---

From your expertise in {self.expertise}, provide feedback on:

1. **Strengths** (1-2 points)
   - What aspects of this plan are good?

2. **Suggestions** (2-3 points)
   - What could be improved?
   - What topics from your expertise should be covered?
   - What sections might need more/less attention?

3. **Missing Elements** (if any)
   - What important aspects are missing from your perspective?

Return JSON:
{{
  "strengths": ["strength1", "strength2"],
  "suggestions": ["suggestion1", "suggestion2"],
  "missing_elements": ["element1"] or [],
  "overall_assessment": "brief assessment"
}}"""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=2048
        )

        # Parse response
        feedback = repair_json(response.content)

        feedback["reviewer"] = self.name
        feedback["expertise"] = self.expertise
        return feedback

    async def review_section(
        self,
        section_content: str,
        section_title: str
    ) -> dict:
        """Review a section from co-author's expertise perspective."""

        system_prompt = f"""You are an expert reviewer in {self.expertise}.

Your specializations: {', '.join(self.focus_areas)}

You are reviewing a section of a collaborative manuscript from your area of expertise.
Provide constructive feedback focusing on technical accuracy, completeness, and clarity."""

        prompt = f"""Review the following manuscript section from your expertise in {self.expertise}:

SECTION: {section_title}

CONTENT:
{section_content}

---

Provide feedback on:

1. **Strengths** (2-3 points)
   - What is done well?
   - What are the strong aspects?

2. **Weaknesses** (2-3 points)
   - What needs improvement?
   - What is missing or unclear?

3. **Specific Suggestions** (2-4 suggestions)
   - Concrete recommendations for improvement
   - Additional points to cover
   - Corrections needed

4. **Scores** (1-5 scale)
   - Clarity: How clear and understandable is the writing?
   - Technical Accuracy: How accurate is the technical content?
   - Completeness: How complete is the coverage?

Return JSON:
{{
  "strengths": ["strength1", "strength2"],
  "weaknesses": ["weakness1", "weakness2"],
  "suggestions": ["suggestion1", "suggestion2"],
  "clarity_score": 4,
  "technical_accuracy": 4,
  "completeness": 3
}}"""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=2048
        )

        # Parse response
        feedback = repair_json(response.content)

        return feedback
