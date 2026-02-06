"""Research planner agent for creating section-level writing plans."""

from typing import List
import json
from ..llm import ClaudeLLM
from ..config import get_config
from ..models.section import ResearchPlan, SectionSpec


class ResearchPlannerAgent:
    """AI agent that plans research structure before writing.

    Creates detailed section-by-section plans that guide multi-stage writing.
    """

    def __init__(self, model: str = "claude-sonnet-4"):
        """Initialize research planner.

        Args:
            model: Claude model to use (Sonnet for cost efficiency)
        """
        config = get_config()
        llm_config = config.get_llm_config("anthropic", model)
        self.llm = ClaudeLLM(
            api_key=llm_config.api_key,
            model=llm_config.model,
            base_url=llm_config.base_url
        )
        self.model = model

    async def create_research_plan(
        self,
        topic: str,
        target_length: str = "comprehensive"  # "short", "medium", "comprehensive"
    ) -> ResearchPlan:
        """Create detailed research plan with section breakdown.

        Args:
            topic: Research topic
            target_length: Desired paper length

        Returns:
            Complete research plan with sections
        """
        system_prompt = """You are an expert research planner specializing in blockchain and distributed systems.

Your role:
- Analyze research topics and identify key questions
- Break down topics into logical sections
- Create detailed section specifications
- Ensure comprehensive coverage with proper dependencies

You plan research like a senior researcher planning a paper before writing."""

        length_guidance = {
            "short": "5-7 sections, ~10,000 words total",
            "medium": "7-10 sections, ~15,000 words total",
            "comprehensive": "10-15 sections, ~20,000 words total"
        }

        prompt = f"""Create a detailed research plan for the following topic:

TOPIC: {topic}

TARGET LENGTH: {target_length} ({length_guidance.get(target_length, length_guidance['medium'])})

Your task is to create a section-by-section plan that will guide the writing process.

REQUIREMENTS:

1. Identify 3-5 key research questions this paper should answer
2. Break the topic into logical sections (Introduction, Background, Core Sections, Analysis, Conclusion)
3. For each section, specify:
   - Unique ID (e.g., "intro", "background", "mechanism-design")
   - Clear title
   - 3-5 key points to cover
   - Dependencies (which sections must be written first)
   - Estimated tokens (1500-5000 per section)
   - Depth level ("overview", "detailed", or "comprehensive")

4. Ensure logical flow:
   - Introduction sets context
   - Background establishes foundations
   - Core sections build on each other
   - Analysis synthesizes
   - Conclusion wraps up

5. Consider:
   - What does the reader need to understand first?
   - Which concepts build on others?
   - What level of technical detail is appropriate?

Output your plan in the following JSON format:

{{
  "topic": "{topic}",
  "research_questions": [
    "Question 1?",
    "Question 2?",
    "Question 3?"
  ],
  "sections": [
    {{
      "id": "intro",
      "title": "Introduction and Motivation",
      "key_points": [
        "Point 1",
        "Point 2",
        "Point 3"
      ],
      "dependencies": [],
      "estimated_tokens": 2000,
      "depth_level": "overview",
      "order": 1
    }},
    {{
      "id": "background",
      "title": "Technical Background",
      "key_points": ["..."],
      "dependencies": ["intro"],
      "estimated_tokens": 3000,
      "depth_level": "detailed",
      "order": 2
    }}
  ],
  "recommended_experts": [
    "Expert domain 1",
    "Expert domain 2"
  ]
}}

Create the complete research plan now."""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=4096
        )

        # Parse JSON response
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            plan_data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse research plan as JSON: {e}\n"
                f"Content preview: {content[:500]}..."
            )

        # Convert to ResearchPlan object
        sections = [
            SectionSpec(
                id=s["id"],
                title=s["title"],
                key_points=s["key_points"],
                dependencies=s.get("dependencies", []),
                estimated_tokens=s.get("estimated_tokens", 3000),
                depth_level=s.get("depth_level", "detailed"),
                order=s.get("order", idx)
            )
            for idx, s in enumerate(plan_data["sections"], 1)
        ]

        total_tokens = sum(s.estimated_tokens for s in sections)

        plan = ResearchPlan(
            topic=plan_data["topic"],
            research_questions=plan_data["research_questions"],
            sections=sections,
            total_estimated_tokens=total_tokens,
            recommended_experts=plan_data.get("recommended_experts", [])
        )

        return plan
