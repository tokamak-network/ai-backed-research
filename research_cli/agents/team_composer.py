"""AI agent for composing optimal expert review teams."""

import json
from typing import List

from ..model_config import create_llm_for_role, get_role_config
from ..models.expert import ExpertProposal


class TeamComposerAgent:
    """AI agent that analyzes research topics and proposes expert teams."""

    def __init__(self, role: str = "team_composer"):
        """Initialize team composer.

        Args:
            role: Role name for model configuration lookup
        """
        self.llm = create_llm_for_role(role)
        self.model = self.llm.model

        # Get configured reviewer model to ensure proposals match infrastructure
        reviewer_config = get_role_config("reviewer")
        self.reviewer_model = reviewer_config.primary.model
        self.reviewer_provider = reviewer_config.primary.provider

    async def propose_team(
        self,
        topic: str,
        num_experts: int = 3,
        additional_context: str = "",
        secondary_category: str = "",
    ) -> List[ExpertProposal]:
        """Analyze topic and propose optimal expert team.

        Args:
            topic: Research topic to analyze
            num_experts: Number of expert reviewers to propose
            additional_context: Optional additional context about requirements
            secondary_category: Optional secondary domain description for interdisciplinary topics

        Returns:
            List of ExpertProposal objects
        """
        prompt = self._build_proposal_prompt(topic, num_experts, additional_context, secondary_category)
        system_prompt = self._get_system_prompt()

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,  # Allow creative team composition
            max_tokens=2048
        )

        # Parse JSON response
        content = response.content.strip()

        # Try to extract JSON from markdown code blocks
        import re
        json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
        if json_match:
            content = json_match.group(1)
        else:
            # Fallback: find the first { and last }
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                content = content[start : end + 1]

        try:
            proposals_data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse team proposal as JSON: {e}\n"
                f"Raw response length: {len(response.content)}\n"
                f"Cleaned content length: {len(content)}\n"
                f"Content preview: {content[:200]}..."
            )

        # Convert to ExpertProposal objects
        proposals = []
        for p in proposals_data["experts"]:
            # Use configured model if suggestion is missing or generic
            model = p.get("suggested_model", self.reviewer_model)

            # If the model matches our configured model (ignoring minor formatting diffs),
            # force it to the exact configured string to ensure compatibility
            if self.reviewer_model.replace("-", "").replace(".", "") in model.replace("-", "").replace(".", ""):
                model = self.reviewer_model

            proposal = ExpertProposal(
                expert_domain=p["expert_domain"],
                rationale=p["rationale"],
                focus_areas=p["focus_areas"],
                suggested_model=model,
                suggested_provider=p.get("suggested_provider", self.reviewer_provider)
            )
            proposals.append(proposal)

        return proposals

    def _get_system_prompt(self) -> str:
        """Get system prompt for team composition."""
        return """You are an expert research coordinator specializing in assembling optimal peer review teams.

Your expertise includes:
- Understanding research domains and their interdependencies
- Identifying required expertise for comprehensive review
- Ensuring balanced coverage without redundancy
- Matching reviewer expertise to research complexity

When proposing expert teams:
1. Analyze the core technical domains involved
2. Consider interdisciplinary aspects
3. Ensure complementary (not overlapping) expertise
4. Match expert focus to paper requirements
5. Recommend appropriate LLM models based on task complexity

You propose high-quality, diverse expert teams for rigorous peer review."""

    def _build_proposal_prompt(
        self,
        topic: str,
        num_experts: int,
        additional_context: str,
        secondary_category: str = "",
    ) -> str:
        """Build prompt for team proposal."""
        prompt = f"""Analyze the following research topic and propose an optimal team of {num_experts} expert reviewers.

RESEARCH TOPIC:
{topic}
"""

        if secondary_category:
            prompt += f"\nSECONDARY DOMAIN: {secondary_category}\nOne reviewer should specifically cover the intersection of the primary topic and this secondary domain.\n"

        if additional_context:
            prompt += f"\nADDITIONAL CONTEXT:\n{additional_context}\n"

        prompt += f"""
---

Propose a team of expert reviewers with complementary expertise. Each expert should cover a distinct domain or perspective necessary for comprehensive review.

Respond in the following JSON format:

{{
  "analysis": "<brief analysis of topic and required expertise>",
  "experts": [
    {{
      "expert_domain": "<specific domain — be precise, not broad. Examples by field: CS: 'Distributed Consensus Protocols', Medicine: 'Tumor Immunology & Checkpoint Therapy', Law: 'International Trade Law', Physics: 'Condensed Matter & Topological Insulators', Economics: 'Behavioral Finance & Market Microstructure', Humanities: 'Post-Colonial Literary Theory', Engineering: 'MEMS Sensor Design & Fabrication'>",
      "rationale": "<2-3 sentences: why this expertise is essential for this topic>",
      "focus_areas": [
        "<specific aspect 1>",
        "<specific aspect 2>",
        "<specific aspect 3>"
      ],
      "suggested_model": "{self.reviewer_model}",
      "suggested_provider": "{self.reviewer_provider}"
    }}
  ]
}}

REQUIREMENTS:
- Exactly {num_experts} experts
- Each expert should have a DISTINCT domain (no overlap)
- Focus areas should be SPECIFIC to this research topic
- Rationale should explain why this expertise is needed for THIS topic
- Use {self.reviewer_model} for reviewers (configured standard)
- Ensure comprehensive coverage of the topic's key technical dimensions

Focus on technical expertise most relevant to the research topic."""

        return prompt
