"""Writer agent for generating and revising research manuscripts."""

import asyncio
import logging
from typing import Optional, List, Dict
from ..llm import ClaudeLLM
from ..llm.base import LLMResponse
from ..config import get_config
from ..models.section import WritingContext, SectionOutput
from ..models.collaborative_research import Reference
from ..utils.source_retriever import SourceRetriever

logger = logging.getLogger(__name__)

# Timeout (seconds) before falling back from Opus to Sonnet
LLM_TIMEOUT_SECONDS = 180  # 3 minutes


class WriterAgent:
    """AI agent that writes and revises research manuscripts.

    Uses Claude Opus for high-quality research writing with iterative
    refinement based on specialist feedback. Falls back to Sonnet on
    timeout or connection error.
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

        # Fallback LLM (Sonnet) for timeout/connection errors
        fallback_config = config.get_llm_config("anthropic", "claude-sonnet-4")
        self._fallback_llm = ClaudeLLM(
            api_key=fallback_config.api_key,
            model=fallback_config.model,
            base_url=fallback_config.base_url
        )

        # Token tracking for last LLM call
        self._last_input_tokens: int = 0
        self._last_output_tokens: int = 0
        self._last_total_tokens: int = 0
        self._last_model_used: str = model

    def get_last_token_usage(self) -> dict:
        """Return token usage from the most recent LLM call.

        Returns:
            Dict with tokens, input_tokens, output_tokens, model keys
        """
        return {
            "tokens": self._last_total_tokens,
            "input_tokens": self._last_input_tokens,
            "output_tokens": self._last_output_tokens,
            "model": self._last_model_used,
        }

    async def _generate_with_fallback(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 16384,
        timeout: int = LLM_TIMEOUT_SECONDS,
    ) -> LLMResponse:
        """Call primary LLM with timeout, fall back to Sonnet on failure.

        Uses streaming internally to prevent proxy idle-connection timeouts.
        """
        try:
            response = await asyncio.wait_for(
                self.llm.generate_streaming(
                    prompt=prompt,
                    system=system,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=timeout,
            )
            self._last_input_tokens = response.input_tokens or 0
            self._last_output_tokens = response.output_tokens or 0
            self._last_total_tokens = response.total_tokens or 0
            self._last_model_used = response.model
            return response
        except (asyncio.TimeoutError, Exception) as e:
            is_timeout = isinstance(e, asyncio.TimeoutError)
            reason = f"timeout ({timeout}s)" if is_timeout else f"{type(e).__name__}: {e}"
            logger.warning(f"Primary LLM ({self.model}) failed: {reason} — falling back to Sonnet")

            # Force-close the primary client to release proxy connections
            try:
                await self.llm.client.close()
            except Exception:
                pass
            # Recreate primary client for future calls
            config = get_config()
            llm_config = config.get_llm_config("anthropic", self.model)
            self.llm = ClaudeLLM(
                api_key=llm_config.api_key,
                model=llm_config.model,
                base_url=llm_config.base_url,
            )

            # Small delay to let proxy release the connection slot
            await asyncio.sleep(2)

            # Fallback to Sonnet (also streaming to avoid proxy timeouts)
            response = await self._fallback_llm.generate_streaming(
                prompt=prompt,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            self._last_input_tokens = response.input_tokens or 0
            self._last_output_tokens = response.output_tokens or 0
            self._last_total_tokens = response.total_tokens or 0
            self._last_model_used = response.model
            return response

    async def write_manuscript(
        self,
        topic: str,
        profile: str = "academic",
        references: Optional[List[Reference]] = None,
        domain: str = "interdisciplinary research",
        article_length: str = "full",
        audience_level: str = "professional",
    ) -> str:
        """Write initial research manuscript.

        Args:
            topic: Research topic
            profile: Writing profile (academic, technical, etc.)
            references: Optional list of real references to cite
            domain: Domain description for specialization context
            article_length: "full" (3,000-5,000 words) or "short" (1,500-2,500 words)
            audience_level: "beginner", "intermediate", or "professional"

        Returns:
            Manuscript text in markdown format
        """
        # Audience-level writing guidance
        audience_guidance = ""
        if audience_level == "beginner":
            audience_guidance = """
TARGET AUDIENCE: Beginners / Non-specialists
- Explain all technical terms on first use
- Use analogies and real-world examples to illustrate complex concepts
- Progress from simple concepts to more complex ones
- Minimize jargon; when technical terms are necessary, define them clearly
- Assume no prior domain knowledge"""
        elif audience_level == "intermediate":
            audience_guidance = """
TARGET AUDIENCE: Intermediate readers (basic domain knowledge assumed)
- Assume familiarity with fundamental concepts in the field
- Explain only advanced or specialized terminology
- Balance theoretical depth with practical applicability
- Include both conceptual explanations and technical details"""

        system_prompt = f"""You are an expert research writer specializing in {domain}.
{audience_guidance}
Your writing style:
- Write in flowing academic prose with well-developed paragraphs
- Each paragraph should have a topic sentence, supporting evidence, and analysis
- Clear, precise technical language with logical flow between ideas
- Evidence-based with specific examples and data
- Balanced perspective considering multiple viewpoints
- Academic rigor with proper citations
- NEVER use bullet-point lists for analysis or discussion
- Reserve lists ONLY for enumerating specific technical specifications, steps, or requirements
- Never use "..." or ellipsis to abbreviate content

Write comprehensive research reports that are:
- Factually accurate
- Technically rigorous
- {"Accessible to non-specialist readers while maintaining accuracy" if audience_level == "beginner" else "Accessible to readers with basic domain knowledge" if audience_level == "intermediate" else "Accessible to experts in the field"}
- Grounded in current literature and data"""

        # Build references block for injection
        refs_block = ""
        if references:
            refs_text = SourceRetriever.format_for_prompt(references)
            refs_block = f"""
VERIFIED SOURCES (use these as primary citations):
{refs_text}

CITATION RULES:
- You MUST cite these sources using [1], [2], etc. inline where relevant
- Integrate citations naturally into the text (e.g., "Recent work [1] shows...")
- Every major claim should be backed by at least one citation
- You may combine citations like [1,3] when multiple sources support a claim
- At the end of the manuscript, include a "## References" section listing all cited sources
- You may also add well-known references beyond this list, but prioritize these verified sources
"""

        # Length-dependent prompt segments
        if article_length == "short":
            length_requirement = "- 1,500-2,500 words"
            length_guidance = "\n- Be concise and focused. Prioritize depth over breadth."
        else:
            length_requirement = "- 3,000-5,000 words"
            length_guidance = ""

        prompt = f"""Write a comprehensive research report on the following topic:

TOPIC: {topic}

PROFILE: {profile}
{refs_block}
Requirements:
{length_requirement}
- Include executive summary
- Structured sections with clear headings
- Technical depth appropriate for experts
- Cite specific examples, protocols, and data
- Include practical implications
- Forward-looking analysis of trends{length_guidance}
{"- Include inline citations [1], [2] and a References section at the end" if references else ""}

Format: Markdown with proper headings (##, ###). Write in flowing academic prose paragraphs.
Do NOT use bullet-point lists for analysis or discussion. Reserve lists only for
enumerating specific technical items (e.g., protocol requirements, system specifications).
Never truncate content with "..." or leave sentences incomplete.

Write the complete manuscript now."""

        response = await self._generate_with_fallback(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=16384,
        )

        return response.content

    async def write_author_response(
        self,
        manuscript: str,
        reviews: List[Dict],
        round_number: int
    ) -> str:
        """Write author response to reviewer feedback.

        Args:
            manuscript: Current manuscript text
            reviews: List of review dictionaries from specialists
            round_number: Current review round

        Returns:
            Author response text addressing each reviewer
        """
        feedback_summary = self._consolidate_feedback(reviews)

        system_prompt = """You are the author of a research manuscript responding to peer review feedback.

Your role:
- Address each reviewer's concerns directly and professionally
- Explain what changes you will make (or have made)
- Clarify misunderstandings or provide additional context
- Respectfully disagree when reviewer criticism is not applicable
- Show engagement with feedback and willingness to improve

Write a professional author response that demonstrates:
- Careful reading of all reviews
- Clear plan for addressing substantive concerns
- Rationale for decisions (what to change, what to keep)
- Respect for reviewers' time and expertise"""

        prompt = f"""You have received peer reviews for your manuscript. Write a detailed response addressing each reviewer.

ROUND: {round_number}

MANUSCRIPT SUMMARY:
[Word count: {len(manuscript.split())} words]

REVIEWER FEEDBACK:
{feedback_summary}

---

Write a professional author response with the following structure:

## Author Response - Round {round_number}

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

Write the complete author response now."""

        response = await self._generate_with_fallback(
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
        round_number: int,
        references: Optional[List[Reference]] = None,
        domain: str = "interdisciplinary research",
        article_length: str = "full",
        author_response: Optional[str] = None,
        audience_level: str = "professional",
    ) -> str:
        """Revise manuscript based on specialist feedback.

        Args:
            manuscript: Current manuscript text
            reviews: List of review dictionaries from specialists
            round_number: Current revision round (1, 2, 3, etc.)
            references: Optional list of real references available for citation
            domain: Domain description for specialization context
            article_length: "full" or "short" — controls revision length constraints
            author_response: Author's response/rebuttal from this round (for revision accountability)
            audience_level: "beginner", "intermediate", or "professional"

        Returns:
            Revised manuscript text
        """
        # Consolidate feedback from all reviewers
        feedback_summary = self._consolidate_feedback(reviews)

        # Build structured revision checklist from reviewer weaknesses/suggestions
        checklist = self._build_revision_checklist(reviews)

        # Audience-level revision guidance
        audience_revision_note = ""
        if audience_level == "beginner":
            audience_revision_note = """
AUDIENCE: Beginner / Non-specialist
- Ensure all technical terms are explained on first use
- Add analogies and examples where reviewers note complexity
- Maintain simple-to-complex progression
- Minimize unnecessary jargon
"""
        elif audience_level == "intermediate":
            audience_revision_note = """
AUDIENCE: Intermediate (basic domain knowledge assumed)
- Fundamental concepts can be assumed
- Explain only advanced/specialized terminology
- Balance theoretical depth with practical applicability
"""

        system_prompt = f"""You are an expert research writer revising a manuscript based on peer review feedback.
{audience_revision_note}
Your revision approach:
- Address all substantive criticisms — EVERY item in the revision checklist must be handled
- Maintain the manuscript's core structure and arguments where valid
- Add missing analysis and evidence as requested
- Improve clarity and precision
- Keep revisions focused and coherent

CRITICAL RULE: You must implement every change you commit to. Reviewers will check whether promised changes were actually made. Failing to follow through on stated revisions is worse than not making them at all.

Do not:
- Ignore valid criticism
- Add fluff or filler content
- Change topics or scope dramatically
- Lose valuable existing content unnecessarily
- Convert flowing prose into bullet-point lists
- Use "..." or ellipsis to truncate content
- Promise changes in response but fail to implement them in the manuscript

Maintain flowing academic prose style throughout the revision."""

        # Build references block for revision
        refs_block = ""
        if references:
            refs_text = SourceRetriever.format_for_prompt(references)
            refs_block = f"""
VERIFIED SOURCES (available for citation):
{refs_text}

CITATION RULES FOR REVISION:
- Use [1], [2], etc. to cite these sources inline
- If reviewers noted weak/missing citations, add more from this list
- Ensure the References section at the end is complete and accurate
"""

        # Build accountability block from author response
        accountability_block = ""
        if author_response:
            accountability_block = f"""
AUTHOR RESPONSE (your commitments from rebuttal):
{author_response}

ACCOUNTABILITY: The above is YOUR response to reviewers. You MUST implement every change you committed to.
Reviewers will verify each promise. Any unimplemented commitment will be flagged as a serious issue.
"""

        prompt = f"""REVISION ROUND {round_number}

You are revising a research manuscript based on specialist peer reviews.

CURRENT MANUSCRIPT:
{manuscript}

---

SPECIALIST REVIEWS:

{feedback_summary}
{refs_block}
---

REVISION CHECKLIST (you must address every item):
{checklist}

---
{accountability_block}
REVISION INSTRUCTIONS:

1. Read all reviews carefully and the revision checklist above
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
   - Maintain flowing academic prose throughout — do NOT convert paragraphs into bullet lists
   - Never truncate content with "..."

4. Preserve what works:
   - Keep strengths identified by reviewers
   - Maintain clear structure
   - Retain good examples and data
{"" if article_length != "short" else """
5. Length constraint:
   - Keep the manuscript concise, under 3,000 words
   - Do not expand sections unnecessarily
   - Prioritize quality and depth over breadth
"""}
Output the complete revised manuscript in markdown format.
Focus on substantive improvements that address reviewer concerns."""

        response = await self._generate_with_fallback(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=16384,
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

            citations_line = f"\n- Citations: {scores['citations']}/10" if 'citations' in scores else ""
            part = f"""
## {specialist} (Average: {avg}/10)

**Scores:**
- Accuracy: {scores['accuracy']}/10
- Completeness: {scores['completeness']}/10
- Clarity: {scores['clarity']}/10
- Novelty: {scores['novelty']}/10
- Rigor: {scores['rigor']}/10{citations_line}

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

    def _build_revision_checklist(self, reviews: List[Dict]) -> str:
        """Build a structured revision checklist from reviewer weaknesses and suggestions.

        Args:
            reviews: List of review dictionaries

        Returns:
            Numbered checklist string
        """
        items = []
        idx = 1
        for review in reviews:
            reviewer = review["specialist_name"]
            for w in review.get("weaknesses", []):
                items.append(f"{idx}. [{reviewer}] FIX: {w}")
                idx += 1
            for s in review.get("suggestions", []):
                items.append(f"{idx}. [{reviewer}] ADD: {s}")
                idx += 1
        return "\n".join(items) if items else "(No specific items)"

    async def verify_citations(
        self,
        manuscript: str,
        references: List[Reference],
        domain: str = "interdisciplinary research",
    ) -> str:
        """Verify and strengthen citations in the manuscript.

        Checks every substantive claim for proper citation, fills gaps using
        available references, and ensures the References section is complete.

        Args:
            manuscript: Current manuscript text
            references: List of verified references available for citation
            domain: Domain description

        Returns:
            Manuscript with verified and strengthened citations
        """
        refs_text = SourceRetriever.format_for_prompt(references)

        system_prompt = """You are a citation verification specialist. Your ONLY job is to strengthen the citation apparatus of a research manuscript.

Rules:
- Every substantive claim, statistic, or technical assertion MUST have an inline citation [N]
- Use ONLY the provided verified references — never fabricate citations
- Add citations where they are missing; do not remove existing valid ones
- Ensure the References section at the end lists all cited sources with full details
- Do not change the manuscript's arguments, structure, or prose — ONLY add/fix citations
- If a claim cannot be supported by any available reference, flag it with [citation needed]
- Output the complete manuscript with citations fixed"""

        prompt = f"""CITATION VERIFICATION PASS

Review this manuscript and ensure every substantive claim is properly cited.

MANUSCRIPT:
{manuscript}

---

VERIFIED REFERENCES (use these for citations):
{refs_text}

---

INSTRUCTIONS:
1. Read through the manuscript paragraph by paragraph
2. For each substantive claim, check if it has an inline citation [N]
3. If a claim lacks citation but a matching reference exists, add the citation
4. If multiple references support a claim, cite the most relevant one
5. Ensure the References section at the end is complete and matches inline citations
6. Do NOT change the manuscript content, structure, or arguments — only fix citations

Output the complete manuscript with all citations verified and gaps filled."""

        response = await self._generate_with_fallback(
            prompt=prompt,
            system=system_prompt,
            temperature=0.3,
            max_tokens=16384
        )

        return response.content

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

        system_prompt = """You are an expert research writer.

Your writing style:
- Write in flowing academic prose with well-developed paragraphs
- Each paragraph should have a topic sentence, supporting evidence, and analysis
- Clear, precise technical language with logical flow between ideas
- Evidence-based with specific examples and data
- Balanced perspective considering multiple viewpoints
- Academic rigor with proper analysis
- NEVER use bullet-point lists for analysis or discussion
- Reserve lists ONLY for enumerating specific technical specifications or requirements
- Never use "..." or ellipsis to abbreviate content

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
- Write in flowing academic prose, NOT bullet-point lists
- Each paragraph should develop one idea with evidence and analysis
- Reference previous sections naturally when relevant (e.g., "As discussed in the Introduction...")
- Maintain consistent terminology with previous sections
- Provide technical depth appropriate for the {section_spec.depth_level} level
- Include specific examples, data, protocols, and analysis
- Use proper markdown formatting with subheadings (###) where appropriate
- Never use "..." or abbreviate content

Write the complete section now. Focus on quality and comprehensiveness - you have the full token budget for just this section."""

        response = await self._generate_with_fallback(
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

        response = await self._generate_with_fallback(
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
