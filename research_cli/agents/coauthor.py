"""Co-author agent for collaborative research."""

from typing import List, Dict
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
4. Document your findings clearly

CRITICAL: Only cite references you are CERTAIN exist. If you are unsure whether a paper, author combination, or venue is real, do not include it. Fabricated references are worse than no references. Prefer citing from any verified sources provided in the project context."""

        # Build context from research notes
        context_text = ""
        if context.get("research_questions"):
            context_text += "\n\nPROJECT RESEARCH QUESTIONS:\n"
            context_text += "\n".join(f"- {q}" for q in context["research_questions"])

        if context.get("hypotheses"):
            context_text += "\n\nPROJECT HYPOTHESES:\n"
            context_text += "\n".join(f"- {h}" for h in context["hypotheses"])

        if context.get("available_references"):
            context_text += "\n\nAVAILABLE REAL REFERENCES (use these as citations — they are verified academic sources):\n"
            context_text += context["available_references"]
            context_text += "\n\nIMPORTANT: You may ONLY cite references from the list above. Do not add references from memory — they may be fabricated. If a claim cannot be supported by these sources, state the claim without citation rather than inventing one."

        prompt = f"""You have been assigned a research task:

TASK: {task.title}

DESCRIPTION:
{task.description}

PROJECT CONTEXT:
{context_text}

---

Conduct focused research on this task. Be concise — prioritize substance over length.

1. **Findings** (3-4 key findings, each 2-3 sentences)
   - Title: Brief descriptive title
   - Description: Core discovery (2-3 sentences max)
   - Evidence: One concrete example or data point
   - Confidence: "high", "medium", or "low"

2. **References** (3-6 authoritative sources)
   - Authors, Title, Venue, Year, DOI/URL

3. **Research Notes** (2-4 sentences)
   - Key limitations or open questions only

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
            max_tokens=3072
        )

        # Parse response
        data = repair_json(response.content)

        # Create Finding objects
        findings = []
        for i, f_data in enumerate(data.get("findings", [])):
            finding = Finding(
                id=f"{self.author_id}_finding_{i+1}",
                title=f_data.get("title", f"Finding {i+1}"),
                description=f_data.get("description", ""),
                evidence=f_data.get("evidence", []),
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
                authors=r_data.get("authors", []),
                title=r_data.get("title", "Untitled"),
                venue=r_data.get("venue", ""),
                year=r_data.get("year", 0),
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

    async def analyze_reviews(
        self,
        reviews: List[Dict],
        manuscript: str,
    ) -> str:
        """Analyze reviewer feedback and generate domain-specific revision notes.

        Produces actionable revision guidance from this co-author's expertise
        perspective, which the writer uses alongside reviewer feedback during
        manuscript revision.

        Args:
            reviews: List of review dictionaries from specialists
            manuscript: Current manuscript text

        Returns:
            Revision notes as plain text (for direct insertion into writer prompt)
        """
        system_prompt = f"""You are an expert researcher in {self.expertise}.

Your specializations: {', '.join(self.focus_areas)}

You are a co-author on this manuscript. External peer reviewers have provided feedback.
Your job is to analyze their feedback through the lens of your domain expertise and
produce specific, actionable revision notes for the lead writer."""

        # Extract key review elements
        review_summaries = []
        for i, review in enumerate(reviews):
            name = review.get('specialist_name', review.get('expert_name', f'Reviewer {i+1}'))
            avg = review.get('average', 'N/A')
            strengths = "\n".join(f"  - {s}" for s in review.get('strengths', []))
            weaknesses = "\n".join(f"  - {w}" for w in review.get('weaknesses', []))
            suggestions = "\n".join(f"  - {s}" for s in review.get('suggestions', []))
            review_summaries.append(
                f"### {name} (Score: {avg}/10)\n"
                f"Strengths:\n{strengths}\n"
                f"Weaknesses:\n{weaknesses}\n"
                f"Suggestions:\n{suggestions}"
            )

        reviews_text = "\n\n".join(review_summaries)

        prompt = f"""As a co-author with expertise in {self.expertise}, analyze the following peer reviews
and provide revision guidance for the lead writer.

CURRENT MANUSCRIPT (for context):
{manuscript[:3000]}
{"[...manuscript truncated for brevity...]" if len(manuscript) > 3000 else ""}

---

PEER REVIEWS:
{reviews_text}

---

Provide revision notes covering:

1. **Domain-Specific Interpretation**: Which reviewer concerns relate to your expertise?
   Explain what the reviewers are really asking for from a domain perspective.

2. **Specific Revision Suggestions**: For each relevant concern, provide concrete guidance:
   - What content should be added, removed, or rewritten
   - Specific technical details, examples, or frameworks to include
   - Domain-accurate terminology or concepts the writer should use

3. **Additional Domain Insights**: Anything the reviewers missed that your expertise
   suggests should also be addressed in the revision.

Be specific and actionable. The writer will use your notes directly during revision."""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=2048
        )

        return response.content
