"""Writer agent for generating and revising research manuscripts."""

from typing import Optional, List, Dict
from ..llm import ClaudeLLM
from ..config import get_config
from ..models.section import WritingContext, SectionOutput


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
            max_tokens=16384  # Claude Opus 4.5 maximum output
        )

        return response.content

    async def write_rebuttal(
        self,
        manuscript: str,
        reviews: List[Dict],
        round_number: int
    ) -> str:
        """Write author rebuttal responding to reviewer feedback.

        Args:
            manuscript: Current manuscript text
            reviews: List of review dictionaries from specialists
            round_number: Current review round

        Returns:
            Rebuttal text explaining responses to each reviewer
        """
        feedback_summary = self._consolidate_feedback(reviews)

        system_prompt = """You are the author of a research manuscript responding to peer review feedback.

Your role:
- Address each reviewer's concerns directly and professionally
- Explain what changes you will make (or have made)
- Clarify misunderstandings or provide additional context
- Respectfully disagree when reviewer criticism is not applicable
- Show engagement with feedback and willingness to improve

Write a professional rebuttal that demonstrates:
- Careful reading of all reviews
- Clear plan for addressing substantive concerns
- Rationale for decisions (what to change, what to keep)
- Respect for reviewers' time and expertise"""

        prompt = f"""You have received peer reviews for your manuscript. Write a detailed rebuttal responding to each reviewer.

ROUND: {round_number}

MANUSCRIPT SUMMARY:
[Word count: {len(manuscript.split())} words]

REVIEWER FEEDBACK:
{feedback_summary}

---

Write a professional author rebuttal with the following structure:

## Author Rebuttal - Round {round_number}

### Overview
[1-2 paragraphs: thank reviewers, summarize key themes in feedback, outline revision strategy]

### Response to Reviewer 1 ([Reviewer Name])
**Overall Assessment**: [Acknowledge their score and main concerns]

**Major Points**:
1. [Reviewer concern 1]
   - **Our response**: [What you will change/clarify/explain]
   - **Action taken**: [Specific changes made or planned]

2. [Reviewer concern 2]
   - **Our response**: ...
   - **Action taken**: ...

**Minor Points**: [Address smaller suggestions collectively]

### Response to Reviewer 2 ([Reviewer Name])
[Same structure]

### Response to Reviewer 3 ([Reviewer Name])
[Same structure]

### Summary of Changes
- [List major revisions planned/made]
- [Clarifications added]
- [New analysis/data included]

---

Guidelines:
- Be specific about what you will change
- Provide rationale for disagreements (respectfully)
- Show you understand the criticism even if you disagree
- Keep tone professional and collaborative
- Focus on substantive issues, not minor wording

Write the complete rebuttal now."""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=4096
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
            max_tokens=16384  # Claude Opus 4.5 maximum output
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

    async def write_section(
        self,
        context: WritingContext
    ) -> SectionOutput:
        """Write a single section with full context.

        Args:
            context: Writing context with plan, previous sections, and section spec

        Returns:
            Section output with content and metadata
        """
        section_spec = context.section_spec
        previous_summaries = context.get_all_previous_summaries()

        system_prompt = """You are an expert research writer specializing in blockchain technology and distributed systems.

Your writing style:
- Clear, precise technical language
- Well-structured with logical flow
- Evidence-based with specific examples and data
- Balanced perspective considering multiple viewpoints
- Academic rigor with proper analysis

You are writing ONE SECTION of a larger paper. Focus deeply on this section's topic."""

        prompt = f"""You are writing Section {section_spec.order} of a research paper.

OVERALL RESEARCH PLAN:
Topic: {context.research_plan.topic}

Research Questions:
{chr(10).join(f'- {q}' for q in context.research_plan.research_questions)}

PREVIOUSLY WRITTEN SECTIONS:
{previous_summaries}

---

CURRENT SECTION TO WRITE:
Title: {section_spec.title}
Section ID: {section_spec.id}
Depth Level: {section_spec.depth_level}

Key Points to Cover:
{chr(10).join(f'- {p}' for p in section_spec.key_points)}

---

YOUR TASK:

Write this section in complete detail. You have the FULL token budget dedicated to just this section.

Requirements:
- Write {section_spec.estimated_tokens//250}-{section_spec.estimated_tokens//150} words (aim for depth, not brevity)
- Reference previous sections naturally when relevant (e.g., "As discussed in the Introduction...")
- Maintain consistent terminology with previous sections
- Provide technical depth appropriate for the {section_spec.depth_level} level
- Include specific examples, data, protocols, and analysis
- Use proper markdown formatting with subheadings (###) where appropriate

Write the complete section now. Focus on quality and comprehensiveness - you have the full token budget for just this section."""

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
                "depth_level": section_spec.depth_level
            }
        )

    async def revise_section(
        self,
        section: SectionOutput,
        feedback: str,
        context: WritingContext
    ) -> SectionOutput:
        """Revise a specific section based on feedback.

        Args:
            section: Original section output
            feedback: Reviewer feedback specific to this section
            context: Writing context

        Returns:
            Revised section output
        """
        system_prompt = """You are an expert research writer revising a section based on peer review feedback.

Your revision approach:
- Address all substantive criticisms
- Add missing analysis and evidence as requested
- Improve clarity and precision
- Maintain coherence with rest of paper
- Keep what works"""

        prompt = f"""You are revising one section of a research paper based on reviewer feedback.

SECTION TITLE: {section.metadata.get('title', 'Unknown')}
CURRENT SECTION CONTENT:
{section.content}

---

REVIEWER FEEDBACK FOR THIS SECTION:
{feedback}

---

YOUR TASK:

Revise this section to address the feedback. You have the full token budget for this section.

Requirements:
- Address all substantive criticisms
- Add missing technical depth, examples, or data as requested
- Improve clarity where needed
- Maintain consistent terminology
- Keep strengths that reviewers identified

Write the complete revised section now."""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=16384
        )

        content = response.content
        word_count = len(content.split())

        return SectionOutput(
            section_id=section.section_id,
            content=content,
            word_count=word_count,
            tokens_used=response.total_tokens,
            metadata=section.metadata
        )
