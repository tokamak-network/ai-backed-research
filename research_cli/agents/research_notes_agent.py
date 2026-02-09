"""Research notes agent for conducting research and taking notes."""

from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path
import json

from ..model_config import create_llm_for_role
from ..utils.json_repair import repair_json
from ..models.research_notes import (
    ResearchNotebook,
    LiteratureNote,
    DataAnalysisNote,
    ObservationNote,
    QuestionNote
)


class ResearchNotesAgent:
    """AI agent that conducts research and takes raw notes.

    This agent works like a researcher:
    - Reads literature and takes notes
    - Identifies gaps and questions
    - Records observations
    - No focus on readability (raw notes)
    """

    def __init__(self, role: str = "research_notes"):
        """Initialize research notes agent.

        Args:
            role: Role name for model config lookup
        """
        self.llm = create_llm_for_role(role)
        self.model = self.llm.model

    async def start_research(
        self,
        topic: str,
        research_questions: List[str]
    ) -> ResearchNotebook:
        """Start a new research notebook.

        Args:
            topic: Research topic
            research_questions: Initial research questions

        Returns:
            New research notebook
        """
        return ResearchNotebook(
            topic=topic,
            research_questions=research_questions,
            start_date=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
            status="active"
        )

    async def literature_search(
        self,
        notebook: ResearchNotebook,
        query: str
    ) -> List[LiteratureNote]:
        """Search for relevant literature and take notes.

        Args:
            notebook: Research notebook
            query: Search query

        Returns:
            List of literature notes
        """
        system_prompt = """You are a research assistant conducting literature review.

Your role:
- Search for relevant sources (papers, docs, blogs)
- Extract key findings
- Identify important quotes
- Note questions raised
- Assess relevance to research questions

Take raw research notes - don't worry about polish or readability."""

        prompt = f"""Conduct literature search for the following research:

TOPIC: {notebook.topic}

RESEARCH QUESTIONS:
{chr(10).join(f'- {q}' for q in notebook.research_questions)}

SEARCH QUERY: {query}

YOUR TASK:

Imagine you're searching academic databases, documentation sites, and GitHub repos.
For each relevant source you find, take notes.

Output your findings in JSON format:

{{
  "sources": [
    {{
      "source": "Paper/Doc title or URL",
      "source_type": "paper|documentation|blog|github",
      "key_findings": [
        "Finding 1",
        "Finding 2",
        "Finding 3"
      ],
      "quotes": [
        "Important quote 1",
        "Important quote 2"
      ],
      "questions_raised": [
        "What about X?",
        "How does Y work?"
      ],
      "relevance": "How this relates to our research questions"
    }}
  ]
}}

Take research notes now. Include 3-5 relevant sources."""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=4096
        )

        # Parse JSON
        data = repair_json(response.content)

        notes = []
        for source_data in data.get("sources", []):
            note = LiteratureNote(
                source=source_data["source"],
                source_type=source_data["source_type"],
                key_findings=source_data["key_findings"],
                quotes=source_data.get("quotes", []),
                questions_raised=source_data.get("questions_raised", []),
                relevance=source_data.get("relevance", "")
            )
            notes.append(note)

        return notes

    async def record_observation(
        self,
        notebook: ResearchNotebook,
        observation: str,
        evidence: List[str] = None
    ) -> ObservationNote:
        """Record an observation or insight.

        Args:
            notebook: Research notebook
            observation: The observation
            evidence: Supporting evidence

        Returns:
            Observation note
        """
        system_prompt = """You are analyzing a research observation.

Your role:
- Assess the observation's implications
- Evaluate confidence level
- Identify supporting evidence needs"""

        prompt = f"""Analyze this research observation:

RESEARCH CONTEXT:
Topic: {notebook.topic}

OBSERVATION: {observation}

EVIDENCE PROVIDED:
{chr(10).join(f'- {e}' for e in (evidence or []))}

YOUR TASK:

Analyze this observation:
1. What are the implications?
2. How confident should we be? (low/medium/high)
3. What additional evidence would strengthen this?

Output in JSON:

{{
  "implications": ["implication 1", "implication 2"],
  "confidence": "low|medium|high",
  "additional_evidence_needed": ["evidence 1", "evidence 2"]
}}"""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.5,
            max_tokens=1024
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
        except json.JSONDecodeError:
            # Fallback
            data = {
                "implications": [],
                "confidence": "medium",
                "additional_evidence_needed": []
            }

        note = ObservationNote(
            observation=observation,
            supporting_evidence=evidence or [],
            implications=data.get("implications", []),
            confidence=data.get("confidence", "medium")
        )

        return note

    async def identify_gaps(
        self,
        notebook: ResearchNotebook
    ) -> List[QuestionNote]:
        """Identify research gaps and questions.

        Args:
            notebook: Research notebook

        Returns:
            List of question notes
        """
        system_prompt = """You are analyzing research to identify gaps.

Your role:
- Identify unanswered questions
- Spot missing evidence
- Note contradictions
- Suggest investigation approaches"""

        # Summarize notebook
        notebook_summary = f"""
Topic: {notebook.topic}

Research Questions:
{chr(10).join(f'- {q}' for q in notebook.research_questions)}

Literature Sources: {len(notebook.literature_notes)}
Data Analyses: {len(notebook.data_analysis_notes)}
Observations: {len(notebook.observations)}
"""

        prompt = f"""Analyze this research notebook and identify gaps:

{notebook_summary}

YOUR TASK:

Based on the research conducted so far, identify:
1. What questions remain unanswered?
2. What evidence is missing?
3. What contradictions exist?
4. What should be investigated next?

Output in JSON:

{{
  "questions": [
    {{
      "question": "What is X?",
      "why_important": "Because it affects Y",
      "potential_approaches": [
        "Approach 1",
        "Approach 2"
      ]
    }}
  ]
}}

Identify 3-5 key gaps."""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.7,
            max_tokens=2048
        )

        data = repair_json(response.content)

        questions = []
        for q_data in data.get("questions", []):
            question = QuestionNote(
                question=q_data["question"],
                why_important=q_data["why_important"],
                potential_approaches=q_data.get("potential_approaches", []),
                answered=False
            )
            questions.append(question)

        return questions

    async def synthesize_notes(
        self,
        notebook: ResearchNotebook
    ) -> str:
        """Synthesize research notes into key findings summary.

        Args:
            notebook: Research notebook

        Returns:
            Summary text
        """
        system_prompt = """You are synthesizing research notes.

Your role:
- Summarize key findings
- Identify main themes
- Note confidence levels
- Highlight gaps"""

        prompt = f"""Synthesize these research notes:

TOPIC: {notebook.topic}

RESEARCH CONDUCTED:
- {len(notebook.literature_notes)} literature sources reviewed
- {len(notebook.data_analysis_notes)} data analyses completed
- {len(notebook.observations)} observations recorded
- {len([q for q in notebook.questions if not q.answered])} open questions

YOUR TASK:

Write a brief synthesis (3-5 paragraphs) of:
1. Main findings
2. Key themes
3. Confidence in findings
4. Important gaps

This is internal notes - be honest about uncertainties."""

        response = await self.llm.generate(
            prompt=prompt,
            system=system_prompt,
            temperature=0.6,
            max_tokens=2048
        )

        return response.content
