"""Writer agent for generating and revising research manuscripts."""

import asyncio
import logging
from typing import Optional, List, Dict
from ..llm.base import LLMResponse
from ..model_config import create_llm_for_role, create_fallback_llm_for_role
from ..models.section import WritingContext, SectionOutput
from ..models.collaborative_research import Reference
from ..utils.source_retriever import SourceRetriever

logger = logging.getLogger(__name__)

# Timeout (seconds) before falling back from Opus to Sonnet
LLM_TIMEOUT_SECONDS = 180  # 3 minutes


def validate_manuscript_completeness(text: str) -> dict:
    """Validate manuscript structural completeness. Detects truncation signs.

    Returns:
        Dict with is_complete (bool), issues (list), word_count (int)
    """
    import re as _re
    issues = []

    # 1. Ends mid-sentence — but ignore if last non-empty line is a URL or reference entry
    stripped = text.rstrip()
    if stripped:
        last_line = stripped.split('\n')[-1].strip()
        is_ref_line = (
            last_line.startswith('[')
            or last_line.startswith('http')
            or last_line.startswith('Available:')
            or last_line.startswith('DOI:')
        )
        if not is_ref_line and stripped[-1] not in '.!?")\']':
            issues.append("ends_mid_sentence")

    # 2. Missing References/Bibliography section
    lower = text.lower()
    if not _re.search(r'##\s+(?:\d+\.?\s+)?(?:references|bibliography)', lower):
        issues.append("missing_references")

    # 3. Conclusion presence is checked by the moderator via prompt, not regex.
    #    Heading variants ("Open Problems and Conclusion", "Summary and Outlook", etc.)
    #    are too diverse for reliable pattern matching.

    return {
        "is_complete": len(issues) == 0,
        "issues": issues,
        "word_count": len(text.split()),
    }


class WriterAgent:
    """AI agent that writes and revises research manuscripts.

    Uses Claude Opus for high-quality research writing with iterative
    refinement based on specialist feedback. Falls back to Sonnet on
    timeout or connection error.
    """

    def __init__(self, role: str = "writer"):
        """Initialize writer agent.

        Args:
            role: Role name for model configuration lookup
        """
        self.role = role
        self.llm = create_llm_for_role(role)
        self.model = self.llm.model

        # Fallback LLM for timeout/connection errors
        self._fallback_llm = create_fallback_llm_for_role(role)

        # Token tracking for last LLM call
        self._last_input_tokens: int = 0
        self._last_output_tokens: int = 0
        self._last_total_tokens: int = 0
        self._last_model_used: str = self.model

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

    @staticmethod
    def _clean_manuscript_output(text: str) -> str:
        """Strip system prompt echo and preamble from LLM output.

        Some models (especially Gemini) may echo the system prompt or
        revision instructions before the actual manuscript content.
        This strips everything before the first ## heading.
        """
        import re as _re
        match = _re.search(r'^(## .+)', text, _re.MULTILINE)
        if match and match.start() > 0:
            text = text[match.start():]
        return text.strip()

    async def _call_llm_once(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 16384,
        timeout: int = LLM_TIMEOUT_SECONDS,
    ) -> LLMResponse:
        """Single LLM call with timeout and fallback. No continuation logic.

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
            return response
        except (asyncio.TimeoutError, Exception) as e:
            is_timeout = isinstance(e, asyncio.TimeoutError)
            reason = f"timeout ({timeout}s)" if is_timeout else f"{type(e).__name__}: {e}"
            fallback_name = self._fallback_llm.model if self._fallback_llm else "same model"
            logger.warning(f"Primary LLM ({self.model}) failed: {reason} — falling back to {fallback_name}")

            # Force-close the primary client to release proxy connections
            try:
                await self.llm.client.close()
            except Exception:
                pass
            # Recreate primary client for future calls
            self.llm = create_llm_for_role(self.role)

            # Small delay to let proxy release the connection slot
            await asyncio.sleep(2)

            # Fallback (also streaming to avoid proxy timeouts)
            fallback = self._fallback_llm if self._fallback_llm else self.llm
            response = await fallback.generate_streaming(
                prompt=prompt,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response

    # Maximum number of continuation attempts when output is truncated
    MAX_CONTINUATIONS = 3

    async def _generate_with_fallback(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 16384,
        timeout: int = LLM_TIMEOUT_SECONDS,
    ) -> LLMResponse:
        """Call LLM with timeout/fallback and auto-continuation on truncation.

        If the LLM response is truncated (stop_reason == "max_tokens" or "length"),
        automatically continues generation up to MAX_CONTINUATIONS times, stitching
        the output together seamlessly.
        """
        response = await self._call_llm_once(
            prompt=prompt, system=system, temperature=temperature,
            max_tokens=max_tokens, timeout=timeout,
        )

        # Track cumulative tokens
        total_input = response.input_tokens or 0
        total_output = response.output_tokens or 0

        accumulated = response.content

        for i in range(self.MAX_CONTINUATIONS):
            if response.stop_reason not in ("max_tokens", "length"):
                break  # Normal completion

            logger.warning(
                f"Output truncated (stop_reason={response.stop_reason}), "
                f"auto-continuing ({i+1}/{self.MAX_CONTINUATIONS})..."
            )

            # Use last ~500 chars as overlap context
            tail = accumulated[-500:]
            continuation_prompt = (
                "You were writing a manuscript but your output was cut off. "
                "Continue EXACTLY where you left off. Do not repeat any content. "
                "Do not add any preamble or explanation.\n\n"
                f"Your text ended with:\n---\n{tail}\n---\n\n"
                "Continue writing from that exact point:"
            )

            response = await self._call_llm_once(
                prompt=continuation_prompt, system=system,
                temperature=temperature, max_tokens=max_tokens, timeout=timeout,
            )

            total_input += response.input_tokens or 0
            total_output += response.output_tokens or 0
            accumulated += response.content

        if response.stop_reason in ("max_tokens", "length"):
            logger.error(
                f"Output still truncated after {self.MAX_CONTINUATIONS} continuations "
                f"({len(accumulated.split())} words). Manuscript may be incomplete."
            )

        # Build combined response
        combined = LLMResponse(
            content=accumulated,
            model=response.model,
            provider=response.provider,
            input_tokens=total_input,
            output_tokens=total_output,
            stop_reason=response.stop_reason,
        )

        self._last_input_tokens = total_input
        self._last_output_tokens = total_output
        self._last_total_tokens = total_input + total_output
        self._last_model_used = response.model
        return combined

    async def write_manuscript(
        self,
        topic: str,
        profile: str = "academic",
        references: Optional[List[Reference]] = None,
        domain: str = "interdisciplinary research",
        article_length: str = "full",
        audience_level: str = "professional",
        research_type: str = "survey",
    ) -> str:
        """Write initial research manuscript.

        Args:
            topic: Research topic
            profile: Writing profile (academic, technical, etc.)
            references: Optional list of real references to cite
            domain: Domain description for specialization context
            article_length: "full" (3,000-5,000 words) or "short" (1,500-2,500 words)
            audience_level: "beginner", "intermediate", or "professional"
            research_type: "survey" or "research" — determines paper structure

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

        # Research type guidance
        research_type_guidance = ""
        if research_type == "survey":
            research_type_guidance = """
PAPER TYPE: Survey / Literature Review
Your task is to SYNTHESIZE existing research, NOT propose new experiments.
Focus on: comprehensive coverage, taxonomy, comparison tables, gap identification.
Structure should include: background, methodology of survey, thematic analysis, comparison, future directions."""
        elif research_type == "explainer":
            research_type_guidance = """
PAPER TYPE: Explainer / Tutorial
Your task is to EXPLAIN concepts clearly, NOT propose new research or survey all literature.

CRITICAL — Concept-first structure:
- BEFORE any technical detail, dedicate a section to explaining prerequisite/difficult concepts in plain language
- Use the "simple first, then precise" pattern: give an intuitive analogy or everyday comparison, THEN the formal definition
- Example: explain "hash function" as "a fingerprint machine for data" before discussing cryptographic properties
- Each new concept must be grounded in something the reader already understands

Focus on: intuitive analogies, step-by-step build-up, concrete real-world examples, and visual/structural clarity.
Assume the reader wants to UNDERSTAND the topic, not review the state-of-the-art."""
        elif research_type == "original":
            research_type_guidance = """
PAPER TYPE: Original Research
Your task is to present NOVEL contributions, analysis, or findings.
Focus on: clear problem statement, methodology, original analysis or experiments, results, and discussion.
Structure should include: introduction with research questions, related work, methodology, results/analysis, discussion, conclusion."""

        system_prompt = f"""You are an expert research writer specializing in {domain}.
{audience_guidance}{research_type_guidance}
Writing rules:
- Flowing academic prose with well-developed paragraphs (topic sentence → evidence → analysis)
- Clear, precise technical language with logical flow
- Evidence-based with specific examples and data; balanced perspective
- Academic rigor with proper citations
- NEVER use bullet-point lists for analysis/discussion (only for technical specs/requirements)
- Never use "..." or truncate content
- {"Accessible to non-specialists while maintaining accuracy" if audience_level == "beginner" else "Accessible with basic domain knowledge" if audience_level == "intermediate" else "Written for domain experts"}"""

        # Build references block for injection
        refs_block = ""
        if references:
            refs_text = SourceRetriever.format_for_prompt(references)
            refs_block = f"""
VERIFIED SOURCES (use these as primary citations):
{refs_text}

CITATION RULES:
- Cite sources using sequential [1], [2], [3]... numbered by order of first appearance in text
- Integrate naturally (e.g., "Recent work [1] shows..."). Combine as [1,3] when appropriate
- Every major claim needs at least one citation
- You may ONLY cite sources from the verified list above. Do not invent or recall references from memory — they may be incorrect
- End with ## References section formatted EXACTLY like this (one blank line between entries):

  [1] Authors (Year). "Title". Venue/Publisher. DOI or URL

  [2] Authors (Year). "Title". Venue/Publisher. DOI or URL
"""

        # Length-dependent prompt segments
        if article_length == "short":
            length_requirement = "- 1,500-2,500 words"
            length_guidance = "\n- Be concise and focused. Prioritize depth over breadth."
        else:
            length_requirement = "- 3,000-5,000 words"
            length_guidance = ""

        # Audience-level determines summary format ONLY
        # Let LLM design section structure freely based on topic and research_type
        if audience_level == "professional":
            summary_section = """START WITH: ## Abstract
Write a formal academic abstract (150-250 words):
- Background/context (1-2 sentences)
- Research objectives/questions
- Key findings/contributions
- Implications and significance
Use precise technical language and cite key references."""

            structure_guidance = f"""
Design your own section structure appropriate for this {research_type} paper in {domain}.
Choose section names and organization that best serve the content.
Common patterns (but feel free to adapt):
- Survey papers often use: Introduction, Background, Taxonomy/Classification, Comparative Analysis, Future Directions
- Explainer papers often use: Introduction, Core Concepts, Technical Details, Applications
- Research papers often use: Introduction, Related Work, Methodology, Results, Discussion
End with ## Conclusion followed by ## References."""

        elif audience_level == "intermediate":
            summary_section = """START WITH: ## TL;DR
Write EXACTLY 3-5 bullet points (MUST use bullet format, NOT sentences):
- [First key finding/point in one line]
- [Second key finding/point in one line]
- [Third key finding/point in one line]
- [Fourth key finding/point - optional]
- [Fifth key finding/point - optional]

Each bullet should be concise (one line) and hit a major point.

THEN: ## Key Takeaways
List 3-5 main points as bullet points:
- Each takeaway should be a complete, actionable insight
- Focus on practical implications and what readers should remember"""

            structure_guidance = f"""
Design your own section structure appropriate for this {research_type} content.
Use clear, descriptive section headings that guide readers.
Focus on practical value and actionable insights.
Organize content logically for readers with basic domain knowledge.
End with ## Conclusion followed by ## References."""

        else:  # beginner
            summary_section = """START WITH: ## TL;DR
Write EXACTLY 3-5 bullet points in plain language (MUST use bullet format, NOT sentences):
- [First key point - explain like to a friend]
- [Second key point - no jargon]
- [Third key point - simple terms]
- [Fourth key point - optional]
- [Fifth key point - optional]

Each bullet should be one line in everyday language.

THEN: ## Why This Matters
Write 1-2 paragraphs explaining:
- Why should anyone care about this topic?
- What real-world problems does it address?
- How might it affect readers' lives or work?
Use zero jargon - if you must use a technical term, define it immediately."""

            structure_guidance = f"""
Design your own section structure that makes this {research_type} content accessible.
Use question-based or descriptive headings (e.g., "What Is X?", "How Does It Work?", "Real-World Examples").
Build up from simple concepts to more complex ones.
Use analogies, examples, and storytelling to make ideas concrete.
End with ## Conclusion followed by ## References (can call it "Learn More" or "Further Reading")."""

        prompt = f"""Write a comprehensive research report on the following topic:

TOPIC: {topic}
{refs_block}
Requirements:
{length_requirement}{length_guidance}

SUMMARY FORMAT:
{summary_section}

STRUCTURE GUIDANCE:
{structure_guidance}
{"- Include inline citations [1], [2] throughout and a References section at the end" if references else ""}

Format: Markdown with proper headings (##, ###).

Write the complete manuscript now."""

        response = await self._generate_with_fallback(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=16384,
        )

        return self._clean_manuscript_output(response.content)

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
        feedback_summary = self._consolidate_feedback_for_response(reviews)

        system_prompt = (
            "You are a research author responding to peer reviews. "
            "Acknowledge valid criticisms directly. For each concern, state the specific change "
            "you will make in the revision. If you disagree with a point, explain with evidence. "
            "Be concise — one sentence per concern."
        )

        # Build dynamic reviewer template
        reviewer_template = ""
        for i, review in enumerate(reviews):
            name = review.get('specialist_name', review.get('expert_name', f'Expert {i+1}'))
            reviewer_template += f"\n**Reviewer {i+1} ({name})**:\n- [Main concern] → [Our action in 1 sentence]\n- [Second concern] → [Our action in 1 sentence]\n"

        prompt = f"""Write a brief, professional response to peer reviews (Round {round_number}).

REVIEWER FEEDBACK:
{feedback_summary}

RESPONSE FORMAT (keep it SHORT and FOCUSED):

## Author Response - Round {round_number}

Thank you for the reviews. Key revisions:
{reviewer_template}
**Summary**: [1-2 sentences on overall revision approach]

Keep each point to ONE sentence. Address the most important concerns from each reviewer."""

        response = await self._generate_with_fallback(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=1024
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
        research_type: str = "survey",
        coauthor_notes: Optional[List[str]] = None,
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
            research_type: "survey" or "research" — adjusts revision focus
            coauthor_notes: Optional list of revision notes from co-authors (collaborative workflow only)

        Returns:
            Revised manuscript text
        """
        # Compact review summaries (scores + feedback); details go in checklist
        feedback_summary = self._consolidate_feedback_compact(reviews)

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

        # Research type revision guidance
        research_type_revision_note = ""
        if research_type == "survey":
            research_type_revision_note = """
PAPER TYPE: Survey / Literature Review
- Focus revisions on breadth of coverage and synthesis quality
- Strengthen taxonomy and categorization of surveyed works
- Improve comparison tables and gap identification
- Do NOT add novel experiments — maintain survey/review focus
"""
        elif research_type == "explainer":
            research_type_revision_note = """
PAPER TYPE: Explainer / Tutorial
- Focus revisions on clarity, accessibility, and correctness of explanations
- If reviewers note confusion, add a plain-language explanation BEFORE the technical detail (not after)
- Ensure prerequisite concepts are explained in their own section before being used elsewhere
- Add more analogies, concrete examples, or visual descriptions where concepts are abstract
- Ensure step-by-step progression: never reference a concept before defining it
- Do NOT add academic rigor beyond what aids understanding
"""
        elif research_type == "original":
            research_type_revision_note = """
PAPER TYPE: Original Research
- Strengthen methodology description and justification
- Add missing experimental details or analysis where reviewers note gaps
- Ensure results are clearly presented with proper evidence
- Clarify novel contributions and differentiation from prior work
"""

        system_prompt = f"""You are an expert research writer revising a manuscript based on peer review feedback.
{audience_revision_note}{research_type_revision_note}
Revision rules:
- Address EVERY item in the revision checklist
- Maintain core structure and arguments where valid
- Add missing analysis and evidence as requested
- Implement every change you commit to — reviewers will verify
- Flowing academic prose only (no bullet-point lists for analysis, no "..." truncation)
- Do not add fluff, change scope, or lose valuable existing content"""

        # Build references block for revision
        refs_block = ""
        if references:
            refs_text = SourceRetriever.format_for_prompt(references)
            refs_block = f"""
VERIFIED SOURCES (available for citation):
{refs_text}

CITATION RULES FOR REVISION:
- Use sequential [1], [2], [3]... numbered by order of first appearance
- If reviewers noted weak/missing citations, add more from this list
- Ensure ## References section is complete, with one blank line between entries
"""

        # Build co-author revision notes block
        coauthor_block = ""
        if coauthor_notes:
            notes_text = "\n\n".join(
                f"--- Co-Author {i+1} ---\n{note}"
                for i, note in enumerate(coauthor_notes) if note
            )
            if notes_text:
                coauthor_block = f"""
CO-AUTHOR REVISION NOTES (domain experts from your writing team):
{notes_text}

These notes are from your co-authors who have domain expertise.
Incorporate their domain-specific suggestions alongside the reviewer feedback.

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

        current_words = len(manuscript.split())
        length_constraint = ""
        if article_length == "short":
            length_constraint = (
                "5. Length constraint:\n"
                "   - Keep the manuscript concise, under 3,000 words\n"
                "   - Do not expand sections unnecessarily\n"
                "   - Prioritize quality and depth over breadth\n"
            )
        else:
            min_words = max(int(current_words * 0.75), 2000)
            max_words = int(current_words * 1.25)
            length_constraint = (
                "5. Length constraint:\n"
                f"   - Keep between {min_words:,}-{max_words:,} words (current: {current_words:,})\n"
                "   - Do NOT inflate the manuscript — improve quality, not add bulk\n"
                "   - If you add content in one area, trim elsewhere to stay within limits\n"
            )

        summary_heading = "## Abstract" if audience_level == "professional" else "## TL;DR"
        structure_requirements = (
            "6. Structural requirements (MANDATORY — never remove these sections):\n"
            f"   - The manuscript MUST start with {summary_heading}\n"
            "   - The manuscript MUST end with ## Conclusion followed by ## References\n"
            "   - Use inline citations [1], [2], [3] — sequential numbering by order of first appearance\n"
            "   - ## References format — one blank line between each entry:\n"
            '     [1] Authors (Year). "Title". Venue. DOI/URL\n'
            "\n"
            '     [2] Authors (Year). "Title". Venue. DOI/URL\n'
            f"   - Preserve structure: {summary_heading.replace('## ', '')} → Body → Conclusion → References\n"
        )

        # Targeted revision: identify which sections need changes
        sections = self._parse_sections(manuscript)
        affected = self._identify_affected_sections(checklist, sections)
        use_targeted = len(affected) < len(sections) * 0.7 and len(sections) > 3

        # Build manuscript block (possibly with [NO CHANGES NEEDED] tags)
        targeted_instruction = ""
        if use_targeted:
            tagged_parts = []
            for i, sec in enumerate(sections):
                if i in affected:
                    tagged_parts.append(sec["content"])
                else:
                    tagged_parts.append(
                        f"## {sec['title']} [NO CHANGES NEEDED]\n"
                        f"[Content preserved — {len(sec['content'].split())} words]"
                    )
            manuscript_block = "\n\n".join(tagged_parts)
            targeted_instruction = (
                "\nTARGETED REVISION: Some sections are marked [NO CHANGES NEEDED]. "
                "For these sections, output ONLY: ## [exact section title] [NO CHANGES]\n"
                "Focus your revision effort on the unmarked sections.\n"
            )
        else:
            manuscript_block = manuscript

        prompt = f"""REVISION ROUND {round_number}

You are revising a research manuscript based on specialist peer reviews.
{targeted_instruction}
CURRENT MANUSCRIPT:
{manuscript_block}

---

SPECIALIST REVIEWS:

{feedback_summary}
{refs_block}
---

REVISION CHECKLIST (you must address every item):
{checklist}

---
{coauthor_block}{accountability_block}
REVISION INSTRUCTIONS:

1. Read all reviews carefully and the revision checklist above
2. Prioritize issues by severity:
   - Factual errors (highest priority)
   - Missing critical analysis
   - Unclear explanations
   - Minor improvements
   If you cannot fully address all items, handle the highest-priority ones thoroughly
   and mark deferred items with [TODO] inline comments.

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
{length_constraint}
{structure_requirements}
Output the complete revised manuscript in markdown format.
Focus on substantive improvements that address reviewer concerns."""

        response = await self._generate_with_fallback(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=16384,
        )

        result = self._clean_manuscript_output(response.content)

        # Post-process: restore unchanged sections if targeted mode was used
        if use_targeted:
            result = self._restore_unchanged_sections(result, sections, affected)

        return result

    def _consolidate_feedback_for_response(self, reviews: List[Dict]) -> str:
        """Slim review format for author response — only actionable items.

        Args:
            reviews: List of review dictionaries

        Returns:
            Formatted feedback with weaknesses and suggestions only
        """
        parts = []
        for review in reviews:
            specialist = review["specialist_name"]
            avg = review["average"]
            weaknesses = "\n".join(f"- {w}" for w in review.get("weaknesses", []))
            suggestions = "\n".join(f"- {s}" for s in review.get("suggestions", []))
            part = (
                f"## {specialist} ({avg}/10)\n\n"
                f"**Weaknesses:**\n{weaknesses}\n\n"
                f"**Suggestions:**\n{suggestions}"
            )
            parts.append(part)
        return "\n---\n".join(parts)

    def _consolidate_feedback(self, reviews: List[Dict]) -> str:
        """Consolidate reviews into structured feedback (full format for author response).

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

    def _consolidate_feedback_compact(self, reviews: List[Dict]) -> str:
        """Compact review format for revision prompt.

        Includes scores + summary only.
        Weaknesses/suggestions are in the separate revision checklist.
        """
        parts = []
        for review in reviews:
            specialist = review["specialist_name"]
            scores = review["scores"]
            avg = review["average"]
            cit = f", cit={scores['citations']}" if 'citations' in scores else ""
            part = (
                f"## {specialist} ({avg}/10)\n"
                f"Scores: acc={scores['accuracy']} comp={scores['completeness']} "
                f"clar={scores['clarity']} nov={scores['novelty']} rig={scores['rigor']}{cit}\n"
                f"Summary: {review['summary']}"
            )
            parts.append(part)
        return "\n---\n".join(parts)

    def _build_revision_checklist(self, reviews: List[Dict]) -> str:
        """Build deduplicated revision checklist with severity tags.

        Groups similar items by keyword overlap so the same issue raised by
        multiple reviewers appears once with a priority indicator.

        Args:
            reviews: List of review dictionaries

        Returns:
            Numbered checklist string with severity tags
        """
        raw_items = []  # (type, reviewer, text)
        for review in reviews:
            reviewer = review["specialist_name"]
            for w in review.get("weaknesses", []):
                raw_items.append(("FIX", reviewer, w))
            for s in review.get("suggestions", []):
                raw_items.append(("ADD", reviewer, s))

        # Group similar items by keyword overlap
        groups: list = []  # list of [type, [reviewers], representative_text]
        for item_type, reviewer, text in raw_items:
            merged = False
            text_words = set(text.lower().split())
            for group in groups:
                g_type, g_reviewers, g_text = group
                if g_type != item_type:
                    continue
                g_words = set(g_text.lower().split())
                overlap = len(text_words & g_words) / max(len(text_words | g_words), 1)
                if overlap > 0.35:  # 35% word overlap threshold
                    g_reviewers.append(reviewer)
                    # Keep longer text as representative
                    if len(text) > len(g_text):
                        group[2] = text
                    merged = True
                    break
            if not merged:
                groups.append([item_type, [reviewer], text])

        # Sort by number of reviewers (descending) for priority
        groups.sort(key=lambda g: len(g[1]), reverse=True)

        # Format with severity tags
        items = []
        total_reviewers = len(reviews)
        for idx, (item_type, reviewers, text) in enumerate(groups, 1):
            n = len(reviewers)
            if n >= 3:
                tag = f"[{n}/{total_reviewers} reviewers — HIGH PRIORITY]"
            elif n >= 2:
                tag = f"[{n}/{total_reviewers} reviewers]"
            else:
                tag = f"[{reviewers[0]}]"
            items.append(f"{idx}. {tag} {item_type}: {text}")

        return "\n".join(items) if items else "(No specific items)"

    @staticmethod
    def _parse_sections(manuscript: str) -> list:
        """Split manuscript by ## headings into sections.

        Args:
            manuscript: Full manuscript text

        Returns:
            List of dicts with 'title' and 'content' keys
        """
        import re
        sections = []
        parts = re.split(r'(?=^## )', manuscript, flags=re.MULTILINE)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            first_line = part.split('\n')[0]
            title_match = re.match(r'^## (.+)', first_line)
            title = title_match.group(1) if title_match else "Untitled"
            sections.append({"title": title, "content": part})
        return sections

    @staticmethod
    def _identify_affected_sections(checklist: str, sections: list) -> set:
        """Identify which sections are referenced in checklist items.

        Args:
            checklist: Revision checklist text
            sections: List of section dicts from _parse_sections

        Returns:
            Set of section indices that need revision
        """
        affected = set()
        checklist_lower = checklist.lower()
        for i, sec in enumerate(sections):
            title_lower = sec["title"].lower()
            # Match by section title words (at least 2-word match)
            title_words = [w for w in title_lower.split() if len(w) > 2]
            if any(w in checklist_lower for w in title_words):
                affected.add(i)
            # Match by section number (e.g., "Section 3")
            # Try extracting leading number from title like "3. Methodology"
            import re
            num_match = re.match(r'(\d+)', sec["title"].strip())
            if num_match:
                num = num_match.group(1)
                if f"section {num}" in checklist_lower:
                    affected.add(i)

        # Citation-related feedback: add References section (not all sections)
        citation_keywords = ["citation", "bibliography", "reference list", "references section"]
        if any(kw in checklist_lower for kw in citation_keywords):
            for i, sec in enumerate(sections):
                if "reference" in sec["title"].lower():
                    affected.add(i)

        # True cross-cutting feedback affects ALL sections
        cross_cutting = ["all sections", "throughout", "entire manuscript", "every section"]
        if any(kw in checklist_lower for kw in cross_cutting):
            affected = set(range(len(sections)))

        # Safe fallback: if nothing matched, affect all
        if not affected:
            affected = set(range(len(sections)))
        return affected

    @staticmethod
    def _restore_unchanged_sections(revised: str, original_sections: list, affected: set) -> str:
        """Replace [NO CHANGES] markers with original section content.

        Args:
            revised: Revised manuscript output from LLM
            original_sections: List of section dicts from _parse_sections
            affected: Set of section indices that were targeted for revision

        Returns:
            Complete manuscript with markers replaced by originals
        """
        import re
        for i, sec in enumerate(original_sections):
            if i not in affected:
                # Match the [NO CHANGES] marker line (flexible whitespace)
                pattern = re.escape(f"## {sec['title']}") + r'\s*\[NO CHANGES\].*'
                revised = re.sub(pattern, sec["content"], revised)
        return revised

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
