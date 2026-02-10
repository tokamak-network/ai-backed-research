"""Research planner agent for creating section-level writing plans."""

from typing import List
from ..model_config import create_llm_for_role
from ..utils.json_repair import repair_json
from ..models.section import ResearchPlan, SectionSpec


class ResearchPlannerAgent:
    """AI agent that plans research structure before writing.

    Creates detailed section-by-section plans that guide multi-stage writing.
    """

    def __init__(self, role: str = "research_planner"):
        """Initialize research planner.

        Args:
            role: Role name for model config lookup
        """
        self.llm = create_llm_for_role(role)
        self.model = self.llm.model

    async def create_research_plan(
        self,
        topic: str,
        target_length: str = "comprehensive",  # "short", "medium", "comprehensive"
        domain: str = "interdisciplinary research",
    ) -> ResearchPlan:
        """Create detailed research plan with section breakdown.

        Args:
            topic: Research topic
            target_length: Desired paper length
            domain: Domain description for specialization context

        Returns:
            Complete research plan with sections
        """
        system_prompt = f"""You are an expert research planner specializing in {domain}.

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
        plan_data = repair_json(response.content)

        # Convert to ResearchPlan object
        sections = [
            SectionSpec(
                id=s.get("id", f"section_{idx}"),
                title=s.get("title", f"Section {idx}"),
                key_points=s.get("key_points", []),
                dependencies=s.get("dependencies", []),
                estimated_tokens=s.get("estimated_tokens", 3000),
                depth_level=s.get("depth_level", "detailed"),
                order=s.get("order", idx)
            )
            for idx, s in enumerate(plan_data.get("sections", []), 1)
        ]

        total_tokens = sum(s.estimated_tokens for s in sections)

        plan = ResearchPlan(
            topic=plan_data.get("topic", ""),
            research_questions=plan_data.get("research_questions", []),
            sections=sections,
            total_estimated_tokens=total_tokens,
            recommended_experts=plan_data.get("recommended_experts", [])
        )

        return plan
