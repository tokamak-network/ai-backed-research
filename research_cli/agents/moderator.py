"""Moderator agent for making accept/reject decisions on peer reviews."""

from typing import List, Dict
from ..model_config import create_llm_for_role


class ModeratorAgent:
    """AI moderator that makes final accept/reject decisions.

    Acts as a conference chair/editor who reads all reviews and makes
    the final decision on manuscript acceptance.
    """

    def __init__(self, role: str = "moderator"):
        """Initialize moderator agent.

        Args:
            role: Role name for model config lookup
        """
        self.llm = create_llm_for_role(role)
        self.model = self.llm.model

    async def make_decision(
        self,
        manuscript: str,
        reviews: List[Dict],
        round_number: int,
        max_rounds: int,
        previous_rounds: List[Dict] = None,
        domain: str = "interdisciplinary research",
        completeness_warning: str = None,
    ) -> Dict:
        """Make accept/reject decision based on peer reviews.

        Args:
            manuscript: Current manuscript text
            reviews: List of specialist reviews
            round_number: Current round number
            max_rounds: Maximum rounds allowed
            previous_rounds: Previous round data for trajectory analysis
            domain: Domain description for editorial context

        Returns:
            Dictionary with decision, reasoning, and meta-review
        """
        system_prompt = f"""You are the Editor-in-Chief for a leading research publication in {domain}.

Your role is to exercise EDITORIAL JUDGMENT, not mechanical score calculation.

Core responsibilities:
- Synthesize reviewer feedback and assess its validity
- Evaluate the manuscript's contribution to the field
- Consider improvement trajectory across revision rounds
- Balance rigor with practical contribution
- Make final accept/reject decisions using your expertise

Critical: You are NOT bound by numeric scores. Scores are ONE input among many.

Decision framework:
- ACCEPT: Meets publication standards for the venue (contribution is valuable, major issues resolved)
- MINOR_REVISION: Small fixable issues remain, likely acceptable after revision
- MAJOR_REVISION: Substantial problems that require significant work
- REJECT: Fundamental flaws, out of scope, or insufficient contribution

Editorial discretion factors:
1. **Improvement trajectory**: A paper improving from 6.5→7.5 shows strong revision capability
2. **Reviewer calibration**: Are reviewers too harsh? Demanding standards beyond venue scope?
3. **Substantive vs. nitpicking**: Major conceptual issues vs. minor presentation details
4. **Practical value**: Does it advance understanding even if not "novel research"?
5. **Round context**: After 3 rounds with consistent improvement, be pragmatic
6. **Field standards**: Industry research reports have different standards than pure theory

CRITICAL COMPLETENESS CHECK:
Before making any decision, verify the manuscript is structurally complete:
- Does the text end mid-sentence or appear truncated?
- Are References/Bibliography present?
- Is the Conclusion section present?
If the manuscript appears truncated or incomplete, you MUST issue MAJOR_REVISION
regardless of content quality. An incomplete manuscript cannot be accepted.

Think like a real editor who cares about publishing valuable work, not a score calculator."""

        # Format reviews for moderator
        reviews_summary = self._format_reviews(reviews)
        overall_avg = sum(r["average"] for r in reviews) / len(reviews)

        # Format improvement trajectory if available
        trajectory_summary = ""
        if previous_rounds and len(previous_rounds) > 0:
            trajectory_summary = "\n\nIMPROVEMENT TRAJECTORY:\n"
            for prev_round in previous_rounds:
                prev_avg = prev_round.get("overall_average", 0)
                prev_decision = prev_round.get("moderator_decision", {}).get("decision", "N/A")
                trajectory_summary += f"- Round {prev_round['round']}: Score {prev_avg:.1f}/10, Decision: {prev_decision}\n"

            if len(previous_rounds) > 0:
                first_score = previous_rounds[0].get("overall_average", 0)
                improvement = overall_avg - first_score
                trajectory_summary += f"\nScore change from Round 1: {improvement:+.1f} points"

        # Build completeness warning block
        completeness_block = ""
        if completeness_warning:
            completeness_block = f"""
⚠ {completeness_warning}
An incomplete or truncated manuscript MUST receive MAJOR_REVISION (or REJECT), never ACCEPT.
"""

        prompt = f"""You are reviewing a manuscript submission. Exercise your editorial judgment.

SUBMISSION STATUS:
- Round: {round_number} of {max_rounds}
- Average reviewer score: {overall_avg:.1f}/10
{"- **FINAL ROUND**: You MUST make a binary decision: ACCEPT or REJECT. No further revisions are possible. Consider the full trajectory, improvement shown, and whether remaining issues are minor enough to overlook." if round_number >= max_rounds else ""}
{trajectory_summary}

PEER REVIEWS:
{reviews_summary}
{completeness_block}
---

EDITORIAL ANALYSIS REQUIRED:

Before making your decision, evaluate:

1. **Reviewer Calibration**: Are reviewers applying appropriate standards?
   - Are they demanding theoretical novelty for an industry research report?
   - Are criticisms substantive or nitpicking presentation?
   - Are reviewers too harsh relative to typical venue standards?

2. **Improvement Trajectory**: (Check previous rounds if this is Round {round_number})
   - Has the author addressed major concerns?
   - Is there consistent improvement in scores?
   - Does revision show engagement with feedback?

3. **Contribution Assessment**:
   - Does this advance understanding in the field?
   - Is it valuable to practitioners/researchers even if not groundbreaking?
   - Are the findings/analysis reliable and useful?

4. **Issue Severity**:
   - Are remaining weaknesses FATAL or FIXABLE?
   - Would minor revision truly address concerns?
   - Are "required changes" reasonable or unbounded?

5. **Context**:
   - Round {round_number}/{max_rounds}: How much more iteration is realistic?
   - Have we reached diminishing returns on revisions?

---

Make your decision in JSON format:

{{
  "decision": "{f"ACCEPT|REJECT" if round_number >= max_rounds else "ACCEPT|MINOR_REVISION|MAJOR_REVISION|REJECT"}",
  "confidence": <1-5>,
  "meta_review": "<2-3 paragraphs: synthesize reviews, assess validity of concerns, explain your editorial judgment>",
  "key_strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "key_weaknesses": ["<weakness 1>", "<weakness 2>", "<weakness 3>"],
  "required_changes": ["<change 1>", "<change 2>", "<change 3>"],
  "recommendation": "<clear guidance: accept rationale or what's needed for acceptance>"
}}

{f"FINAL ROUND — Binary decision only: ACCEPT or REJECT. No more revisions possible. If the paper has shown improvement and remaining issues are minor, ACCEPT. If fundamental problems persist, REJECT." if round_number >= max_rounds else "DECISION GUIDANCE (not strict rules):"}
{f"" if round_number >= max_rounds else "- ACCEPT: Contribution is valuable, major issues resolved (often 7.5+, but use judgment)"}
{f"" if round_number >= max_rounds else "- MINOR_REVISION: Specific small fixes needed"}
{f"" if round_number >= max_rounds else "- MAJOR_REVISION: Substantial problems remain"}
{f"" if round_number >= max_rounds else "- REJECT: Fundamental flaws or insufficient contribution"}

Remember: You are an EDITOR, not a score calculator. The average score is advisory, not binding.
A paper at 7.5 with strong improvement trajectory and substantive contribution may merit acceptance.
A paper at 8.0 with valid unresolved fundamental concerns may need revision.

Exercise your judgment now."""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.3,
            max_tokens=2048
        )

        # Parse JSON response
        import json
        import re
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        decision_data = None
        try:
            decision_data = json.loads(content)
        except json.JSONDecodeError:
            # Fallback 1: extract ```json ... ``` block from within text
            json_match = re.search(r'```json\s*\n(.*?)\n```', response.content, re.DOTALL)
            if json_match:
                try:
                    decision_data = json.loads(json_match.group(1).strip())
                except json.JSONDecodeError:
                    pass

            # Fallback 2: find raw JSON object { ... } in the response
            if decision_data is None:
                brace_match = re.search(r'\{.*\}', response.content, re.DOTALL)
                if brace_match:
                    try:
                        decision_data = json.loads(brace_match.group(0))
                    except json.JSONDecodeError:
                        pass

            if decision_data is None:
                raise ValueError(
                    f"Failed to parse moderator decision as JSON: no valid JSON found\n"
                    f"Raw response length: {len(response.content)}\n"
                    f"Cleaned content length: {len(content)}\n"
                    f"Content preview: {content[:200]}..."
                )

        # Add metadata
        decision_data["round"] = round_number
        decision_data["overall_average"] = round(overall_avg, 1)
        decision_data["tokens"] = response.total_tokens

        return decision_data

    def _format_reviews(self, reviews: List[Dict]) -> str:
        """Format reviews for moderator consumption."""
        formatted = []

        for i, review in enumerate(reviews, 1):
            formatted.append(f"""
REVIEWER {i} ({review["specialist_name"]}):
Average Score: {review["average"]}/10

Scores:
- Accuracy: {review["scores"]["accuracy"]}/10
- Completeness: {review["scores"]["completeness"]}/10
- Clarity: {review["scores"]["clarity"]}/10
- Novelty: {review["scores"]["novelty"]}/10
- Rigor: {review["scores"]["rigor"]}/10

Summary: {review["summary"]}

Strengths:
{chr(10).join('- ' + s for s in review["strengths"])}

Weaknesses:
{chr(10).join('- ' + w for w in review["weaknesses"])}

Suggestions:
{chr(10).join('- ' + s for s in review["suggestions"])}
""")

        return "\n---\n".join(formatted)
