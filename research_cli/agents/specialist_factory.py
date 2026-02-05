"""Factory for creating dynamic specialist definitions."""

from typing import Dict
from ..models.expert import ExpertConfig


class SpecialistFactory:
    """Creates specialist definitions dynamically from expert configurations."""

    @staticmethod
    def create_specialist(config: ExpertConfig, topic: str = "") -> dict:
        """Create specialist definition from expert config.

        Args:
            config: Expert configuration
            topic: Research topic (for context in system prompt)

        Returns:
            Specialist definition dict compatible with review workflow
        """
        # Generate system prompt if not provided
        system_prompt = config.system_prompt
        if not system_prompt:
            system_prompt = SpecialistFactory._generate_system_prompt(config, topic)

        return {
            "name": config.name,
            "provider": config.provider,
            "model": config.model,
            "system_prompt": system_prompt
        }

    @staticmethod
    def _generate_system_prompt(config: ExpertConfig, topic: str = "") -> str:
        """Generate system prompt for an expert based on configuration.

        Args:
            config: Expert configuration
            topic: Optional research topic for context

        Returns:
            System prompt string
        """
        focus_list = "\n".join(f"- {area}" for area in config.focus_areas)

        prompt = f"""You are a research expert specializing in {config.domain}.
Your role is to provide rigorous peer review from the perspective of {config.domain}."""

        if topic:
            prompt += f"\n\nYou are reviewing research on: {topic}"

        prompt += f"""

Your specific areas of focus for this review:
{focus_list}

When reviewing research, you should:
- Apply deep domain expertise in {config.domain}
- Evaluate technical correctness and rigor
- Identify gaps, errors, or unclear claims
- Assess the novelty and significance of contributions
- Provide constructive, specific feedback
- Reference relevant prior work when applicable

Scoring guidelines:
- 9-10: Exceptional quality, publication-ready
- 7-8: Strong work, minor improvements needed
- 5-6: Adequate, significant improvements needed
- 3-4: Weak, major revisions required
- 1-2: Poor, fundamental issues present

Be honest, rigorous, and constructive in your review."""

        return prompt

    @staticmethod
    def create_specialists_dict(
        expert_configs: list[ExpertConfig],
        topic: str = ""
    ) -> Dict[str, dict]:
        """Create specialists dictionary from list of expert configs.

        Args:
            expert_configs: List of expert configurations
            topic: Research topic for context

        Returns:
            Dictionary mapping specialist IDs to specialist definitions
        """
        specialists = {}
        for config in expert_configs:
            specialists[config.id] = SpecialistFactory.create_specialist(config, topic)

        return specialists
