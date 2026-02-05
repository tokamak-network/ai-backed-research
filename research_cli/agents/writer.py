"""Writer agent for generating and revising research manuscripts."""

from typing import Optional, List, Dict
from ..llm import ClaudeLLM
from ..config import get_config


class WriterAgent:
    """AI agent that writes and revises research manuscripts.

    Uses Claude Opus for high-quality research writing with iterative
    refinement based on specialist feedback.
    """

    def __init__(self, model: str = "claude-opus-4.5"):
        """Initialize writer agent.

        Args:
            model: Claude model to use (default: Opus 4.5)
        """
        config = get_config()
        llm_config = config.get_llm_config("anthropic", model)
        self.llm = ClaudeLLM(
            api_key=llm_config.api_key,
            model=llm_config.model,
            base_url=llm_config.base_url
        )
        self.model = model

    async def write_manuscript(self, topic: str, profile: str = "academic") -> str:
        """Write initial research manuscript.

        Args:
            topic: Research topic
            profile: Writing profile (academic, technical, etc.)

        Returns:
            Manuscript text in markdown format
        """
        system_prompt = """You are an expert research writer specializing in blockchain technology and distributed systems.

Your writing style:
- Clear, precise technical language
- Well-structured with logical flow
- Evidence-based with specific examples and data
- Balanced perspective considering multiple viewpoints
- Academic rigor with proper citations

Write comprehensive research reports that are:
- Factually accurate
- Technically rigorous
- Accessible to experts in the field
- Grounded in current literature and data"""

        prompt = f"""Write a comprehensive research report on the following topic:

TOPIC: {topic}

PROFILE: {profile}

Requirements:
- 3,000-5,000 words
- Include executive summary
- Structured sections with clear headings
- Technical depth appropriate for experts
- Cite specific examples, protocols, and data
- Include practical implications
- Forward-looking analysis of trends

Format: Markdown with proper headings, lists, code blocks where appropriate.

Write the complete manuscript now."""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=8000
        )

        return response.content

    async def revise_manuscript(
        self,
        manuscript: str,
        reviews: List[Dict],
        round_number: int
    ) -> str:
        """Revise manuscript based on specialist feedback.

        Args:
            manuscript: Current manuscript text
            reviews: List of review dictionaries from specialists
            round_number: Current revision round (1, 2, 3, etc.)

        Returns:
            Revised manuscript text
        """
        # Consolidate feedback from all reviewers
        feedback_summary = self._consolidate_feedback(reviews)

        system_prompt = """You are an expert research writer revising a manuscript based on peer review feedback.

Your revision approach:
- Address all substantive criticisms
- Maintain the manuscript's core structure and arguments where valid
- Add missing analysis and evidence as requested
- Improve clarity and precision
- Keep revisions focused and coherent

Do not:
- Ignore valid criticism
- Add fluff or filler content
- Change topics or scope dramatically
- Lose valuable existing content unnecessarily"""

        prompt = f"""REVISION ROUND {round_number}

You are revising a research manuscript based on specialist peer reviews.

CURRENT MANUSCRIPT:
{manuscript}

---

SPECIALIST REVIEWS:

{feedback_summary}

---

REVISION INSTRUCTIONS:

1. Read all reviews carefully and identify key criticisms
2. Prioritize issues by severity:
   - Factual errors (highest priority)
   - Missing critical analysis
   - Unclear explanations
   - Minor improvements

3. Revise the manuscript to address feedback:
   - Fix factual inaccuracies
   - Add missing technical depth and analysis
   - Include requested examples and data
   - Improve clarity and structure
   - Strengthen rigor and citations

4. Preserve what works:
   - Keep strengths identified by reviewers
   - Maintain clear structure
   - Retain good examples and data

Output the complete revised manuscript in markdown format.
Focus on substantive improvements that address reviewer concerns."""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=8000
        )

        return response.content

    def _consolidate_feedback(self, reviews: List[Dict]) -> str:
        """Consolidate reviews into structured feedback.

        Args:
            reviews: List of review dictionaries

        Returns:
            Formatted feedback summary
        """
        feedback_parts = []

        for review in reviews:
            specialist = review["specialist_name"]
            scores = review["scores"]
            avg = review["average"]

            part = f"""
## {specialist} (Average: {avg}/10)

**Scores:**
- Accuracy: {scores['accuracy']}/10
- Completeness: {scores['completeness']}/10
- Clarity: {scores['clarity']}/10
- Novelty: {scores['novelty']}/10
- Rigor: {scores['rigor']}/10

**Summary:**
{review['summary']}

**Strengths:**
{chr(10).join('- ' + s for s in review['strengths'])}

**Weaknesses:**
{chr(10).join('- ' + w for w in review['weaknesses'])}

**Suggestions:**
{chr(10).join('- ' + s for s in review['suggestions'])}

**Detailed Feedback:**
{review['detailed_feedback']}
"""
            feedback_parts.append(part)

        return "\n---\n".join(feedback_parts)
