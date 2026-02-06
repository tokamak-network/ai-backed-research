"""Moderator agent for making accept/reject decisions on peer reviews."""

from typing import List, Dict
from ..llm import ClaudeLLM
from ..config import get_config


class ModeratorAgent:
    """AI moderator that makes final accept/reject decisions.

    Acts as a conference chair/editor who reads all reviews and makes
    the final decision on manuscript acceptance.
    """

    def __init__(self, model: str = "claude-opus-4.5"):
        """Initialize moderator agent.

        Args:
            model: Claude model to use (Opus for critical decisions)
        """
        config = get_config()
        llm_config = config.get_llm_config("anthropic", model)
        self.llm = ClaudeLLM(
            api_key=llm_config.api_key,
            model=llm_config.model,
            base_url=llm_config.base_url
        )
        self.model = model

    async def make_decision(
        self,
        manuscript: str,
        reviews: List[Dict],
        round_number: int,
        max_rounds: int,
        previous_rounds: List[Dict] = None
    ) -> Dict:
        """Make accept/reject decision based on peer reviews.

        Args:
            manuscript: Current manuscript text
            reviews: List of specialist reviews
            round_number: Current round number
            max_rounds: Maximum rounds allowed
            previous_rounds: Previous round data for trajectory analysis

        Returns:
            Dictionary with decision, reasoning, and meta-review
        """
        system_prompt = """You are the Editor-in-Chief for a leading research publication in blockchain and distributed systems.

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

Think like a real editor who cares about publishing valuable work, not a score calculator.

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

        prompt = f"""You are reviewing a manuscript submission. Exercise your editorial judgment.

SUBMISSION STATUS:
- Round: {round_number} of {max_rounds}
- Average reviewer score: {overall_avg:.1f}/10
{"- FINAL ROUND: Consider accepting if substantial improvement shown and major issues resolved" if round_number >= max_rounds else ""}
{trajectory_summary}

PEER REVIEWS:
{reviews_summary}

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
  "decision": "ACCEPT|MINOR_REVISION|MAJOR_REVISION|REJECT",
  "confidence": <1-5>,
  "meta_review": "<2-3 paragraphs: synthesize reviews, assess validity of concerns, explain your editorial judgment>",
  "key_strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "key_weaknesses": ["<weakness 1>", "<weakness 2>", "<weakness 3>"],
  "required_changes": ["<change 1>", "<change 2>", "<change 3>"],
  "recommendation": "<clear guidance: accept rationale or what's needed for acceptance>"
}}

DECISION GUIDANCE (not strict rules):
- ACCEPT: Contribution is valuable, major issues resolved (often 7.5+, but use judgment)
- MINOR_REVISION: Specific small fixes needed
- MAJOR_REVISION: Substantial problems remain
- REJECT: Fundamental flaws or insufficient contribution

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
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            decision_data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse moderator decision as JSON: {e}\n"
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
