"""Writer Team Composer agent - AI proposes optimal writer team for topic."""

import json
from typing import Dict
from ..model_config import create_llm_for_role


class WriterTeamComposerAgent:
    """
    AI agent that analyzes research topic and proposes optimal writer team.

    Proposes:
    - Lead author with appropriate expertise
    - Co-authors with complementary skills
    - Rationale for each team member
    """

    def __init__(self, role: str = "team_composer"):
        """Initialize writer team composer agent."""
        self.llm = create_llm_for_role(role)
        self.model = self.llm.model

    async def propose_writer_team(
        self,
        topic: str,
        major_field: str,
        subfield: str,
        num_coauthors: int = 2
    ) -> Dict:
        """Propose writer team for research topic.

        Args:
            topic: Research topic
            major_field: Major academic field
            subfield: Subfield
            num_coauthors: Number of co-authors (0-3)

        Returns:
            Dictionary with lead_author and coauthors proposals
        """

        system_prompt = """You are an academic research advisor specializing in team composition.

Your role: Analyze research topics and propose optimal author teams with complementary expertise.

For each author, consider:
- What specific expertise is needed for this research?
- What focus areas will they contribute?
- How do they complement other team members?
- What unique perspective or skillset do they bring?

Propose realistic, specific expertise areas, not generic roles."""

        prompt = f"""Analyze this research topic and propose an optimal writer team.

RESEARCH TOPIC: {topic}

ACADEMIC FIELD: {major_field} → {subfield}

TEAM SIZE: 1 lead author + {num_coauthors} co-authors

---

TASK: Propose a research team with complementary expertise.

For the LEAD AUTHOR:
- What primary expertise is most critical for this research?
- What specific focus areas should they have?
- Why are they best suited to lead this research?

For each CO-AUTHOR (if any):
- What complementary expertise do they bring?
- What specific focus areas should they cover?
- How do they enhance the research beyond what the lead can do?
- What unique contribution will they make?

IMPORTANT:
- Be specific about expertise (e.g., "Zero-Knowledge Cryptography" not just "Cryptography")
- Focus areas should be concrete (e.g., "zkSNARK proof systems" not just "proofs")
- Ensure no overlap between team members
- Each member should have a clear, distinct role

Return JSON format:
{{
  "lead_author": {{
    "name": "Specific expertise area + 'Expert' (e.g., 'Distributed Consensus Expert')",
    "expertise": "Primary area of expertise",
    "focus_areas": ["focus1", "focus2", "focus3"],
    "rationale": "Why they should lead this research"
  }},
  "coauthors": [
    {{
      "name": "Specific expertise area + 'Expert'",
      "expertise": "Complementary area",
      "focus_areas": ["focus1", "focus2", "focus3"],
      "contributions": ["contribution1", "contribution2"],
      "rationale": "Why they're valuable to the team"
    }}
  ]
}}"""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.8,  # Higher temperature for creative team composition
            max_tokens=4096
        )

        # Parse response
        try:
            team_proposal = json.loads(response.content)
        except json.JSONDecodeError:
            content = response.content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
                team_proposal = json.loads(json_str)
            else:
                raise

        return team_proposal

    def create_author_config(
        self,
        author_data: Dict,
        author_id: str,
        role: str,
        model: str = "claude-opus-4.5"
    ) -> Dict:
        """Convert proposal to AuthorRole config."""
        return {
            "id": author_id,
            "name": author_data["name"],
            "role": role,
            "expertise": author_data["expertise"],
            "focus_areas": author_data["focus_areas"],
            "contributions": author_data.get("contributions", []),
            "model": model,
            "provider": "anthropic"
        }

    async def propose_and_format_team(
        self,
        topic: str,
        major_field: str,
        subfield: str,
        num_coauthors: int = 2
    ) -> Dict:
        """Propose team and format as ready-to-use configs."""

        # Get proposal
        proposal = await self.propose_writer_team(
            topic=topic,
            major_field=major_field,
            subfield=subfield,
            num_coauthors=num_coauthors
        )

        # Format lead author
        lead_config = self.create_author_config(
            author_data=proposal["lead_author"],
            author_id="lead",
            role="lead"
        )

        # Format co-authors
        coauthor_configs = []
        for i, coauthor_data in enumerate(proposal["coauthors"][:num_coauthors]):
            coauthor_config = self.create_author_config(
                author_data=coauthor_data,
                author_id=f"coauthor_{i+1}",
                role="coauthor"
            )
            coauthor_configs.append(coauthor_config)

        return {
            "lead_author": lead_config,
            "coauthors": coauthor_configs,
            "proposal_metadata": {
                "topic": topic,
                "field": major_field,
                "subfield": subfield,
                "team_size": 1 + len(coauthor_configs)
            }
        }
