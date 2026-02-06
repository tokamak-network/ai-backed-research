"""Data analysis agent for collecting and analyzing data."""

from typing import List, Dict, Optional, Any
from pathlib import Path
from datetime import datetime
import json

from ..llm import ClaudeLLM
from ..config import get_config
from ..models.research_notes import DataAnalysisNote


class DataAnalysisAgent:
    """AI agent that collects data, analyzes it, and creates visualizations.

    This agent:
    - Collects data from various sources
    - Performs statistical analysis
    - Creates charts and graphs
    - Records findings in research notes
    """

    def __init__(self, model: str = "claude-sonnet-4"):
        """Initialize data analysis agent.

        Args:
            model: Claude model to use
        """
        config = get_config()
        llm_config = config.get_llm_config("anthropic", model)
        self.llm = ClaudeLLM(
            api_key=llm_config.api_key,
            model=llm_config.model,
            base_url=llm_config.base_url
        )
        self.model = model

    async def design_data_collection(
        self,
        research_question: str,
        topic: str
    ) -> Dict:
        """Design data collection strategy.

        Args:
            research_question: Question to answer with data
            topic: Research topic

        Returns:
            Data collection strategy
        """
        system_prompt = """You are a data scientist designing data collection.

Your role:
- Identify what data is needed
- Determine data sources
- Design collection methodology
- Plan analysis approach"""

        prompt = f"""Design data collection for this research:

TOPIC: {topic}
RESEARCH QUESTION: {research_question}

YOUR TASK:

Design a data collection strategy:
1. What specific data points are needed?
2. Where can we get this data? (APIs, on-chain, documentation)
3. What analysis methods are appropriate?
4. What visualizations would be helpful?

Output in JSON:

{{
  "data_needed": [
    {{
      "metric": "Transaction cost",
      "description": "Median transaction cost over time",
      "source": "Dune Analytics / L2Beat",
      "collection_method": "API query / web scraping"
    }}
  ],
  "analysis_methods": [
    "Descriptive statistics",
    "Comparative analysis",
    "Trend analysis"
  ],
  "visualizations": [
    "Time series chart: Cost over time",
    "Bar chart: Protocol comparison"
  ]
}}"""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.6,
            max_tokens=2048
        )

        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            strategy = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse strategy: {e}\n{content[:200]}")

        return strategy

    async def collect_mock_data(
        self,
        data_spec: Dict,
        topic: str
    ) -> Dict:
        """Collect mock data based on specification.

        Args:
            data_spec: Data specification from design phase
            topic: Research topic

        Returns:
            Collected data
        """
        # For now, generate realistic mock data
        # In production, this would call actual APIs

        system_prompt = """You are collecting data for research.

Your role:
- Generate realistic data based on the topic
- Use real-world ranges and patterns
- Include timestamps and metadata"""

        prompt = f"""Generate realistic research data for:

TOPIC: {topic}

DATA SPECIFICATION:
{json.dumps(data_spec, indent=2)}

YOUR TASK:

Generate realistic mock data that matches the specification.
Make it plausible for the topic (e.g., if it's about transaction costs,
use realistic $ amounts; if it's about TPS, use realistic numbers).

Output in JSON:

{{
  "data": {{
    "protocol_name": [
      {{"date": "2024-01-01", "value": 123.45, "unit": "USD"}},
      {{"date": "2024-01-02", "value": 120.00, "unit": "USD"}}
    ]
  }},
  "metadata": {{
    "collection_date": "2024-02-06",
    "source": "Mock data for research",
    "notes": "Based on typical ranges for this metric"
  }}
}}

Generate at least 10-20 data points per metric."""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.8,
            max_tokens=4096
        )

        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse data: {e}\n{content[:200]}")

        return data

    async def analyze_data(
        self,
        data: Dict,
        analysis_methods: List[str]
    ) -> List[str]:
        """Analyze collected data.

        Args:
            data: Collected data
            analysis_methods: Analysis methods to apply

        Returns:
            List of findings
        """
        system_prompt = """You are a data analyst analyzing research data.

Your role:
- Perform statistical analysis
- Identify patterns and trends
- Calculate key metrics
- Draw insights"""

        prompt = f"""Analyze this research data:

DATA:
{json.dumps(data, indent=2)}

ANALYSIS METHODS:
{chr(10).join(f'- {m}' for m in analysis_methods)}

YOUR TASK:

Perform the specified analyses and report findings.

For each finding:
- State the finding clearly
- Include specific numbers
- Note any limitations

Output as JSON:

{{
  "findings": [
    "Finding 1 with specific numbers",
    "Finding 2 with specific numbers",
    "Finding 3 with specific numbers"
  ]
}}"""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.5,
            max_tokens=2048
        )

        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            result = json.loads(content)
            return result.get("findings", [])
        except json.JSONDecodeError:
            return ["Analysis completed but parsing failed"]

    def create_visualizations(
        self,
        data: Dict,
        output_dir: Path,
        viz_specs: List[str]
    ) -> List[str]:
        """Create data visualizations.

        Args:
            data: Data to visualize
            output_dir: Directory to save charts
            viz_specs: Visualization specifications

        Returns:
            List of file paths to created charts
        """
        # Create visualizations using matplotlib/plotly
        # For now, create placeholder files

        output_dir.mkdir(parents=True, exist_ok=True)
        chart_paths = []

        try:
            import matplotlib.pyplot as plt
            import matplotlib
            matplotlib.use('Agg')  # Non-interactive backend

            for i, spec in enumerate(viz_specs):
                # Create simple chart based on data
                fig, ax = plt.subplots(figsize=(10, 6))

                # Extract first data series for demo
                if "data" in data and data["data"]:
                    first_key = list(data["data"].keys())[0]
                    series = data["data"][first_key]

                    if isinstance(series, list) and series:
                        # Extract values
                        if isinstance(series[0], dict):
                            values = [item.get("value", 0) for item in series]
                            labels = [item.get("date", f"Point {j}") for j, item in enumerate(series)]
                        else:
                            values = series
                            labels = list(range(len(series)))

                        # Create plot based on spec
                        if "time series" in spec.lower() or "line" in spec.lower():
                            ax.plot(labels, values, marker='o')
                        elif "bar" in spec.lower():
                            ax.bar(range(len(values)), values)
                            ax.set_xticks(range(len(labels)))
                            ax.set_xticklabels(labels, rotation=45, ha='right')
                        else:
                            ax.plot(labels, values)

                        ax.set_title(spec)
                        ax.set_xlabel("Time / Category")
                        ax.set_ylabel("Value")
                        ax.grid(True, alpha=0.3)

                chart_path = output_dir / f"chart_{i+1}.png"
                plt.tight_layout()
                plt.savefig(chart_path, dpi=100, bbox_inches='tight')
                plt.close()

                chart_paths.append(str(chart_path))

        except Exception as e:
            # If matplotlib fails, create placeholder
            print(f"Warning: Could not create charts: {e}")
            for i, spec in enumerate(viz_specs):
                placeholder = output_dir / f"chart_{i+1}_placeholder.txt"
                placeholder.write_text(f"Chart: {spec}\n\nVisualization would be generated here.")
                chart_paths.append(str(placeholder))

        return chart_paths

    async def perform_analysis(
        self,
        research_question: str,
        topic: str,
        output_dir: Path
    ) -> DataAnalysisNote:
        """Perform complete data analysis workflow.

        Args:
            research_question: Question to answer
            topic: Research topic
            output_dir: Directory for output files

        Returns:
            Data analysis note
        """
        # 1. Design data collection
        strategy = await self.design_data_collection(research_question, topic)

        # 2. Collect data (mock for now)
        data_spec = strategy.get("data_needed", [{}])[0] if strategy.get("data_needed") else {}
        collected_data = await self.collect_mock_data(data_spec, topic)

        # 3. Analyze data
        analysis_methods = strategy.get("analysis_methods", ["Descriptive statistics"])
        findings = await self.analyze_data(collected_data, analysis_methods)

        # 4. Create visualizations
        viz_specs = strategy.get("visualizations", ["Data visualization"])
        chart_paths = self.create_visualizations(collected_data, output_dir, viz_specs)

        # 5. Create note
        note = DataAnalysisNote(
            analysis_type="Comprehensive",
            data_source="Research data collection",
            raw_data=collected_data,
            findings=findings,
            visualizations=chart_paths,
            methodology=f"Methods: {', '.join(analysis_methods)}",
            limitations=["Mock data used for demonstration", "Requires validation with real data"]
        )

        return note
