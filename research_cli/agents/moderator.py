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
        max_rounds: int
    ) -> Dict:
        """Make accept/reject decision based on peer reviews.

        Args:
            manuscript: Current manuscript text
            reviews: List of specialist reviews
            round_number: Current round number
            max_rounds: Maximum rounds allowed

        Returns:
            Dictionary with decision, reasoning, and meta-review
        """
        system_prompt = """You are a senior editor/conference chair for a top-tier academic venue in blockchain and distributed systems research.

Your role:
- Read all peer reviews carefully
- Make an objective accept/reject decision
- Write a meta-review that synthesizes reviewer feedback
- Provide clear guidance to authors

Decision categories:
- ACCEPT: Ready for publication (≥8.0 average, all major issues resolved)
- MINOR REVISION: Nearly ready, small improvements needed (7.0-7.9)
- MAJOR REVISION: Significant issues to address (5.0-6.9)
- REJECT: Fundamental flaws, not salvageable (<5.0)

Be rigorous but fair. Focus on scientific merit, not politics."""

        # Format reviews for moderator
        reviews_summary = self._format_reviews(reviews)
        overall_avg = sum(r["average"] for r in reviews) / len(reviews)

        prompt = f"""You are reviewing a manuscript submission. Read the peer reviews and make your decision.

ROUND: {round_number} of {max_rounds}
OVERALL AVERAGE SCORE: {overall_avg:.1f}/10

PEER REVIEWS:
{reviews_summary}

---

Make your decision in JSON format:

{{
  "decision": "ACCEPT|MINOR_REVISION|MAJOR_REVISION|REJECT",
  "confidence": <1-5>,
  "meta_review": "<2-3 paragraph synthesis of reviews>",
  "key_strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "key_weaknesses": ["<weakness 1>", "<weakness 2>", "<weakness 3>"],
  "required_changes": ["<change 1>", "<change 2>", "<change 3>"],
  "recommendation": "<clear guidance to authors>"
}}

Guidelines:
- ACCEPT if average ≥8.0 AND all reviewers satisfied
- MINOR REVISION if 7.0-7.9 with specific fixable issues
- MAJOR REVISION if 5.0-6.9 with significant problems
- REJECT if <5.0 or fundamental flaws

Consider:
- Are reviewers' concerns valid and substantive?
- Can issues be addressed in revision?
- Is this the final round? (be more lenient if max_rounds reached)
- Scientific merit vs. minor presentation issues

Make your decision now."""

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
