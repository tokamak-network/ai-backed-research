#!/usr/bin/env python3
"""
Model Comparison Benchmark — Support & Reasoning Tier Alternatives

Tests whether cheaper models can replace current tier assignments:
  A. Support tier (Sonnet) → Flash / Haiku / Pro candidates
  B. Reasoning tier (Opus) → Pro candidate

Uses production prompts + real workflow data from results/.

Usage:
    python3 test_model_comparison.py --all
    python3 test_model_comparison.py --group A          # Support tier
    python3 test_model_comparison.py --group B          # Reasoning tier
    python3 test_model_comparison.py --role moderator
    python3 test_model_comparison.py --role team_composer
    python3 test_model_comparison.py --role reviewer
    python3 test_model_comparison.py --role research_notes
"""

import json
import asyncio
import re
import warnings
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import sys

from dotenv import load_dotenv
load_dotenv()

# Suppress google.generativeai FutureWarning
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from research_cli.model_config import _create_llm, get_pricing
from research_cli.utils.json_repair import repair_json

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESULTS_DIR = Path(__file__).parent / "results"

# Models under test
MODELS = {
    "claude-opus-4-6":    {"provider": "anthropic", "model": "claude-opus-4-6",    "short": "Opus"},
    "claude-sonnet-4-5":  {"provider": "anthropic", "model": "claude-sonnet-4-5",  "short": "Sonnet"},
    "claude-haiku-4-5":   {"provider": "anthropic", "model": "claude-haiku-4-5",   "short": "Haiku"},
    "gemini-3-flash-preview":   {"provider": "google",    "model": "gemini-3-flash-preview",   "short": "Flash"},
    "gemini-3-pro-preview":     {"provider": "google",    "model": "gemini-3-pro-preview",     "short": "Pro"},
}

# Support tier test models (exclude Opus — it's the reasoning baseline)
SUPPORT_MODELS = ["claude-sonnet-4-5", "gemini-3-flash-preview", "claude-haiku-4-5", "gemini-3-pro-preview"]

# Reasoning tier test models
REASONING_MODELS = ["claude-opus-4-6", "gemini-3-pro-preview"]


# ---------------------------------------------------------------------------
# Data Loader
# ---------------------------------------------------------------------------

def find_workflow_dirs() -> List[Path]:
    """Find all result directories with workflow_complete.json."""
    dirs = []
    if not RESULTS_DIR.exists():
        return dirs
    for d in sorted(RESULTS_DIR.iterdir()):
        if d.is_dir() and (d / "workflow_complete.json").exists():
            dirs.append(d)
    return dirs


def load_workflow(wf_dir: Path) -> Optional[Dict]:
    """Load workflow_complete.json from a directory."""
    wf_file = wf_dir / "workflow_complete.json"
    if not wf_file.exists():
        return None
    try:
        return json.loads(wf_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def load_manuscript(wf_dir: Path, version: str = "v1") -> str:
    """Load manuscript from a workflow directory."""
    path = wf_dir / f"manuscript_{version}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def select_test_workflows(count: int = 5) -> List[Dict]:
    """Select diverse workflows with reviews for testing.

    Returns list of dicts with: dir, topic, workflow, manuscript, reviews, moderator_decision.
    """
    candidates = []
    for wf_dir in find_workflow_dirs():
        wf = load_workflow(wf_dir)
        if not wf:
            continue
        rounds = wf.get("rounds", [])
        if not rounds:
            continue
        # Need at least round 1 with reviews and moderator decision
        r1 = rounds[0]
        reviews = r1.get("reviews", [])
        mod_dec = r1.get("moderator_decision", {})
        if not reviews or not mod_dec.get("decision"):
            continue
        # Need manuscript_v1
        ms = load_manuscript(wf_dir, "v1")
        if not ms or len(ms) < 500:
            continue

        candidates.append({
            "dir": wf_dir,
            "dir_name": wf_dir.name,
            "topic": wf.get("topic", wf_dir.name),
            "category": wf.get("category", {}),
            "audience_level": wf.get("audience_level", "professional"),
            "research_type": wf.get("research_type", "survey"),
            "workflow": wf,
            "manuscript": ms,
            "reviews": reviews,
            "moderator_decision": mod_dec,
            "expert_team": wf.get("expert_team", []),
            "overall_average": r1.get("overall_average", 0),
        })

    # Sort by recency (newest first)
    candidates.sort(key=lambda c: c["dir_name"], reverse=True)

    # Pick up to `count`, preferring diversity of categories
    selected = []
    seen_categories = set()
    # First pass: one per category
    for c in candidates:
        major = (c["category"] or {}).get("major", "unknown")
        if major not in seen_categories:
            selected.append(c)
            seen_categories.add(major)
            if len(selected) >= count:
                break
    # Second pass: fill remaining slots from newest
    if len(selected) < count:
        for c in candidates:
            if c not in selected:
                selected.append(c)
                if len(selected) >= count:
                    break

    return selected


# ---------------------------------------------------------------------------
# LLM Call Helper
# ---------------------------------------------------------------------------

async def call_llm(provider: str, model: str, prompt: str, system: str,
                   temperature: float, max_tokens: int) -> Dict:
    """Call LLM and return output + token/cost info."""
    llm = _create_llm(provider=provider, model=model)

    # Gemini thinking models: thinking tokens consume max_output_tokens
    effective_max = max_tokens
    if provider == "google" and any(v in model for v in ("2.5", "3-pro", "3-flash")):
        effective_max = max(max_tokens * 8, 2048)

    try:
        resp = await llm.generate(
            prompt=prompt, system=system,
            temperature=temperature, max_tokens=effective_max,
        )
        content = resp.content
        input_tokens = resp.input_tokens or 0
        output_tokens = resp.output_tokens or 0
    except Exception as e:
        print(f"    ERROR ({model}): {e}")
        content = f"[ERROR: {e}]"
        input_tokens = 0
        output_tokens = 0

    pricing = get_pricing(model)
    cost = (
        input_tokens * pricing["input"] / 1_000_000 +
        output_tokens * pricing["output"] / 1_000_000
    )
    return {
        "model": model,
        "provider": provider,
        "output": content,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": cost,
    }


# ---------------------------------------------------------------------------
# Prompt Builders — exact copies of production prompts
# ---------------------------------------------------------------------------

def format_reviews_for_moderator(reviews: List[Dict]) -> str:
    """Format reviews for moderator consumption (from moderator.py:262-290)."""
    formatted = []
    for i, review in enumerate(reviews, 1):
        scores = review.get("scores", {})
        formatted.append(f"""
REVIEWER {i} ({review.get("specialist_name", "Unknown")}):
Average Score: {review.get("average", 0)}/10

Scores:
- Accuracy: {scores.get("accuracy", 0)}/10
- Completeness: {scores.get("completeness", 0)}/10
- Clarity: {scores.get("clarity", 0)}/10
- Novelty: {scores.get("novelty", 0)}/10
- Rigor: {scores.get("rigor", 0)}/10

Summary: {review.get("summary", "")}

Strengths:
{chr(10).join('- ' + s for s in review.get("strengths", []))}

Weaknesses:
{chr(10).join('- ' + w for w in review.get("weaknesses", []))}

Suggestions:
{chr(10).join('- ' + s for s in review.get("suggestions", []))}
""")
    return "\n---\n".join(formatted)


def build_moderator_prompt(
    manuscript: str,
    reviews: List[Dict],
    round_number: int = 1,
    max_rounds: int = 3,
    domain: str = "interdisciplinary research",
    threshold: float = 7.0,
) -> Dict:
    """Build production moderator prompt (from moderator.py:51-202)."""
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

    reviews_summary = format_reviews_for_moderator(reviews)
    overall_avg = sum(r.get("average", 0) for r in reviews) / len(reviews) if reviews else 0

    prompt = f"""You are reviewing a manuscript submission. Exercise your editorial judgment.

SUBMISSION STATUS:
- Round: {round_number} of {max_rounds}
- Average reviewer score: {overall_avg:.1f}/10
- **Acceptance threshold: {threshold}/10** (papers meeting or exceeding this threshold should be accepted unless fundamental flaws exist)
{"- **FINAL ROUND**: You MUST make a binary decision: ACCEPT or REJECT. No further revisions are possible." if round_number >= max_rounds else ""}

PEER REVIEWS:
{reviews_summary}
---

EDITORIAL ANALYSIS REQUIRED:

Before making your decision, evaluate:

1. **Reviewer Calibration**: Are reviewers applying appropriate standards?
2. **Improvement Trajectory**: (Check previous rounds if this is Round {round_number})
3. **Contribution Assessment**: Does this advance understanding in the field?
4. **Issue Severity**: Are remaining weaknesses FATAL or FIXABLE?
5. **Context**: Round {round_number}/{max_rounds}: How much more iteration is realistic?

---

Make your decision in JSON format:

{{
  "decision": "{"ACCEPT|REJECT" if round_number >= max_rounds else "ACCEPT|MINOR_REVISION|MAJOR_REVISION|REJECT"}",
  "confidence": <1-5>,
  "meta_review": "<2-3 paragraphs: synthesize reviews, assess validity of concerns, explain your editorial judgment>",
  "key_strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "key_weaknesses": ["<weakness 1>", "<weakness 2>", "<weakness 3>"],
  "required_changes": ["<change 1>", "<change 2>", "<change 3>"],
  "recommendation": "<clear guidance: accept rationale or what's needed for acceptance>"
}}

{"FINAL ROUND — Binary decision only: ACCEPT or REJECT." if round_number >= max_rounds else "DECISION GUIDANCE (not strict rules):"}
{"" if round_number >= max_rounds else f"- ACCEPT: Score >= {threshold} OR notable contribution"}
{"" if round_number >= max_rounds else "- MINOR_REVISION: Specific small fixes needed"}
{"" if round_number >= max_rounds else "- MAJOR_REVISION: Substantial problems remain"}
{"" if round_number >= max_rounds else "- REJECT: Fundamental flaws or insufficient contribution"}

**CRITICAL THRESHOLD GUIDANCE**:
- If average score >= {threshold}/10 and no fundamental flaws exist, you SHOULD accept.
- Only reject papers above {threshold} if there are clear fundamental problems.

Exercise your judgment now."""

    return {
        "system": system_prompt,
        "prompt": prompt,
        "temperature": 0.3,
        "max_tokens": 2048,
    }


def build_team_composer_prompt(topic: str, num_experts: int = 3) -> Dict:
    """Build production team composer prompt (from team_composer.py:100-167)."""
    system_prompt = """You are an expert research coordinator specializing in assembling optimal peer review teams.

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

    prompt = f"""Analyze the following research topic and propose an optimal team of {num_experts} expert reviewers.

RESEARCH TOPIC:
{topic}

---

Propose a team of expert reviewers with complementary expertise. Each expert should cover a distinct domain or perspective necessary for comprehensive review.

Respond in the following JSON format:

{{
  "analysis": "<brief analysis of topic and required expertise>",
  "experts": [
    {{
      "expert_domain": "<specific domain, e.g., 'Zero-Knowledge Cryptography'>",
      "rationale": "<2-3 sentences: why this expertise is essential for this topic>",
      "focus_areas": [
        "<specific aspect 1>",
        "<specific aspect 2>",
        "<specific aspect 3>"
      ],
      "suggested_model": "claude-opus-4-6",
      "suggested_provider": "anthropic"
    }}
  ]
}}

REQUIREMENTS:
- Exactly {num_experts} experts
- Each expert should have a DISTINCT domain (no overlap)
- Focus areas should be SPECIFIC to this research topic
- Rationale should explain why this expertise is needed for THIS topic
- Ensure comprehensive coverage of the topic's key technical dimensions

Focus on technical expertise most relevant to the research topic."""

    return {
        "system": system_prompt,
        "prompt": prompt,
        "temperature": 0.7,
        "max_tokens": 4096,
    }


def build_reviewer_prompt(
    manuscript: str,
    specialist_system_prompt: str,
    round_number: int = 1,
    research_type: str = "survey",
) -> Dict:
    """Build production reviewer prompt (from orchestrator.py:168-213)."""
    research_type_note = ""
    if research_type == "survey":
        research_type_note = """NOTE: This is a SURVEY / LITERATURE REVIEW paper. Evaluate accordingly:
- Breadth of coverage: Does it comprehensively cover the field?
- Taxonomy/categorization: Are the surveyed works well-organized?
- Gap identification: Does it clearly identify research gaps and future directions?
- Do NOT penalize for lack of novel experimental results
- Evaluate the quality of synthesis, comparison, and critical analysis of existing work

"""

    review_prompt = f"""Review this research manuscript (Round {round_number}) from your expert perspective.

{research_type_note}MANUSCRIPT:
{manuscript}

---

Provide your review in the following JSON format:

{{
  "scores": {{
    "accuracy": <1-10>,
    "completeness": <1-10>,
    "clarity": <1-10>,
    "novelty": <1-10>,
    "rigor": <1-10>,
    "citations": <1-10>
  }},
  "summary": "<2-3 sentence overall assessment>",
  "strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "weaknesses": ["<weakness 1>", "<weakness 2>", "<weakness 3>"],
  "suggestions": ["<suggestion 1>", "<suggestion 2>", "<suggestion 3>"],
  "detailed_feedback": "<paragraph of detailed feedback from your domain expertise>"
}}

Scoring guide:
- 9-10: Exceptional, publication-ready
- 7-8: Strong, minor improvements needed
- 5-6: Adequate, significant improvements needed
- 3-4: Weak, major revisions required
- 1-2: Poor, fundamental issues

Citations scoring guide:
- 9-10: All major claims properly cited with verifiable references
- 7-8: Most claims cited, references are real and checkable
- 5-6: Some citations present but gaps exist, or some references look dubious
- 3-4: Few citations, many unsupported claims
- 1-2: No citations or clearly fabricated references

Penalize: unsupported claims, unverifiable references, hallucinated citations.
Reward: inline citations [1], [2], proper References section, real DOIs/URLs.

Be honest and constructive. Focus on your domain of expertise."""

    return {
        "system": specialist_system_prompt,
        "prompt": review_prompt,
        "temperature": 0.3,
        "max_tokens": 4096,
    }


def build_research_notes_prompt(topic: str, research_questions: List[str], query: str) -> Dict:
    """Production research notes prompt (from test_gemini_flash_roles.py)."""
    return {
        "system": """You are a research assistant conducting literature review.

Your role:
- Search for relevant sources (papers, docs, blogs)
- Extract key findings
- Identify important quotes
- Note questions raised
- Assess relevance to research questions

Take raw research notes - don't worry about polish or readability.""",
        "prompt": f"""Conduct literature search for the following research:

TOPIC: {topic}

RESEARCH QUESTIONS:
{chr(10).join(f'- {q}' for q in research_questions)}

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

Take research notes now. Include 3-5 relevant sources.""",
        "temperature": 0.7,
        "max_tokens": 4096,
    }


# ---------------------------------------------------------------------------
# Scoring Functions
# ---------------------------------------------------------------------------

def score_moderator(output: str, baseline_decision: Dict) -> Dict[str, Any]:
    """Score moderator output against Opus baseline."""
    scores = {
        "json_valid": False,
        "decision_valid": False,
        "decision_match": False,
        "has_meta_review": False,
        "has_strengths_weaknesses": False,
        "confidence_valid": False,
    }

    try:
        data = repair_json(output)
        scores["json_valid"] = True

        decision = data.get("decision", "").upper()
        valid_decisions = {"ACCEPT", "MINOR_REVISION", "MAJOR_REVISION", "REJECT"}
        if decision in valid_decisions:
            scores["decision_valid"] = True
            baseline_dec = baseline_decision.get("decision", "").upper()
            if decision == baseline_dec:
                scores["decision_match"] = True

        meta = data.get("meta_review", "")
        if isinstance(meta, str) and len(meta) >= 50:
            scores["has_meta_review"] = True

        strengths = data.get("key_strengths", [])
        weaknesses = data.get("key_weaknesses", [])
        if isinstance(strengths, list) and len(strengths) >= 1 and isinstance(weaknesses, list) and len(weaknesses) >= 1:
            scores["has_strengths_weaknesses"] = True

        confidence = data.get("confidence", 0)
        if isinstance(confidence, (int, float)) and 1 <= confidence <= 5:
            scores["confidence_valid"] = True

        scores["parsed_decision"] = decision
        scores["parsed_confidence"] = confidence
    except (ValueError, KeyError):
        scores["parsed_decision"] = output[:80] if output else ""

    return scores


def score_team_composer(output: str, expected_count: int = 3) -> Dict[str, Any]:
    """Score team composer output."""
    scores = {
        "json_valid": False,
        "correct_count": False,
        "fields_complete": False,
        "diversity": False,
        "focus_areas_present": False,
        "rationale_quality": False,
    }

    try:
        data = repair_json(output)
        scores["json_valid"] = True

        experts = data.get("experts", [])
        scores["expert_count"] = len(experts)
        if len(experts) == expected_count:
            scores["correct_count"] = True

        if experts:
            required = {"expert_domain", "rationale", "focus_areas"}
            all_complete = all(required.issubset(set(e.keys())) for e in experts)
            scores["fields_complete"] = all_complete

            domains = [e.get("expert_domain", "") for e in experts]
            scores["diversity"] = len(set(domains)) == len(domains) and all(d for d in domains)

            scores["focus_areas_present"] = all(
                isinstance(e.get("focus_areas", []), list) and len(e.get("focus_areas", [])) >= 2
                for e in experts
            )

            scores["rationale_quality"] = all(
                isinstance(e.get("rationale", ""), str) and len(e.get("rationale", "")) >= 30
                for e in experts
            )
    except (ValueError, KeyError):
        scores["expert_count"] = 0

    return scores


def score_reviewer(output: str, baseline_review: Optional[Dict] = None) -> Dict[str, Any]:
    """Score reviewer output against optional Opus baseline."""
    scores = {
        "json_valid": False,
        "scores_valid": False,
        "has_summary": False,
        "has_strengths": False,
        "has_weaknesses": False,
        "has_suggestions": False,
        "has_detailed_feedback": False,
    }

    try:
        data = repair_json(output)
        scores["json_valid"] = True

        review_scores = data.get("scores", {})
        expected_keys = {"accuracy", "completeness", "clarity", "novelty", "rigor", "citations"}
        if expected_keys.issubset(set(review_scores.keys())):
            all_valid = all(
                isinstance(review_scores[k], (int, float)) and 1 <= review_scores[k] <= 10
                for k in expected_keys
            )
            scores["scores_valid"] = all_valid

        summary = data.get("summary", "")
        scores["has_summary"] = isinstance(summary, str) and len(summary) >= 30

        strengths = data.get("strengths", [])
        scores["has_strengths"] = isinstance(strengths, list) and len(strengths) >= 2

        weaknesses = data.get("weaknesses", [])
        scores["has_weaknesses"] = isinstance(weaknesses, list) and len(weaknesses) >= 2

        suggestions = data.get("suggestions", [])
        scores["has_suggestions"] = isinstance(suggestions, list) and len(suggestions) >= 2

        feedback = data.get("detailed_feedback", "")
        scores["has_detailed_feedback"] = isinstance(feedback, str) and len(feedback) >= 100

        # Compute score deviation from baseline if available
        if baseline_review and review_scores and scores["scores_valid"]:
            baseline_scores = baseline_review.get("scores", {})
            if baseline_scores:
                deviations = []
                for k in expected_keys:
                    if k in baseline_scores and k in review_scores:
                        deviations.append(abs(review_scores[k] - baseline_scores[k]))
                if deviations:
                    scores["score_deviation"] = round(sum(deviations) / len(deviations), 2)

        # Output stats
        scores["word_count"] = len(output.split())
        if review_scores and scores["scores_valid"]:
            scores["avg_score"] = round(
                sum(review_scores[k] for k in expected_keys) / len(expected_keys), 1
            )
    except (ValueError, KeyError):
        pass

    return scores


def score_research_notes(output: str) -> Dict[str, Any]:
    """Score research notes output (reused from test_gemini_flash_roles.py)."""
    scores = {
        "json_valid": False,
        "has_sources": False,
        "fields_complete": False,
        "source_type_valid": False,
    }

    try:
        data = repair_json(output)
        scores["json_valid"] = True
        sources = data.get("sources", [])
        scores["source_count"] = len(sources)
        scores["has_sources"] = 3 <= len(sources) <= 7

        if sources:
            required_fields = {"source", "source_type", "key_findings", "relevance"}
            valid_types = {"paper", "documentation", "blog", "github"}
            scores["fields_complete"] = all(
                required_fields.issubset(set(s.keys())) for s in sources
            )
            scores["source_type_valid"] = all(
                s.get("source_type", "").lower() in valid_types for s in sources
            )
    except (ValueError, KeyError):
        scores["source_count"] = 0

    return scores


def compute_score_average(scores: Dict[str, Any]) -> float:
    """Compute average of boolean scores (ignoring non-bool fields)."""
    bools = [v for v in scores.values() if isinstance(v, bool)]
    if not bools:
        return 0.0
    return sum(bools) / len(bools)


# ---------------------------------------------------------------------------
# Specialist System Prompt Reconstruction
# ---------------------------------------------------------------------------

def reconstruct_specialist_prompt(expert: Dict, topic: str) -> str:
    """Reconstruct specialist system prompt from expert team data.

    Mirrors SpecialistFactory._generate_system_prompt().
    """
    domain = expert.get("domain", expert.get("name", "General"))
    focus_areas = expert.get("focus_areas", [])
    focus_list = "\n".join(f"- {area}" for area in focus_areas)

    return f"""You are a research expert specializing in {domain}.
Your role is to provide rigorous peer review from the perspective of {domain}.

You are reviewing research on: {topic}

Your specific areas of focus for this review:
{focus_list}

When reviewing research, you should:
- Apply deep domain expertise in {domain}
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


# ---------------------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------------------

class ModelComparisonTester:
    """Run model comparison benchmarks."""

    def __init__(self):
        self.results: List[Dict] = []
        self.all_test_results: List[Dict] = []

    # ---- Experiment A1: Moderator ----
    async def test_moderator(self) -> Dict:
        """Test moderator role across models using production data."""
        print(f"\n{'='*80}")
        print("MODERATOR — Support tier comparison (baseline: Opus from production)")
        print(f"{'='*80}")

        workflows = select_test_workflows(5)
        if not workflows:
            print("  No workflows found in results/")
            return {}

        print(f"  Selected {len(workflows)} workflows for testing\n")

        examples = []
        for wf in workflows:
            topic_short = wf["topic"][:60]
            baseline = wf["moderator_decision"]
            baseline_dec = baseline.get("decision", "?")
            baseline_conf = baseline.get("confidence", "?")
            print(f"--- {topic_short} ---")
            print(f"  Opus baseline: {baseline_dec} (confidence: {baseline_conf}, avg: {wf['overall_average']})")

            p = build_moderator_prompt(
                manuscript=wf["manuscript"][:6000],  # Truncate for cost control
                reviews=wf["reviews"],
                round_number=1,
                max_rounds=wf["workflow"].get("max_rounds", 3),
                threshold=wf["workflow"].get("threshold", 7.0),
            )

            model_results = {}
            for model_key in SUPPORT_MODELS:
                m = MODELS[model_key]
                result = await call_llm(
                    provider=m["provider"], model=m["model"],
                    prompt=p["prompt"], system=p["system"],
                    temperature=p["temperature"], max_tokens=p["max_tokens"],
                )
                result["scores"] = score_moderator(result["output"], baseline)
                score_avg = compute_score_average(result["scores"])
                dec = result["scores"].get("parsed_decision", "?")
                match = "YES" if result["scores"].get("decision_match") else "NO"
                print(f"  {m['short']:8s} | score={score_avg:.2f} | decision={dec:17s} | match={match:3s} | ${result['cost']:.4f}")
                model_results[model_key] = result

            examples.append({
                "name": topic_short,
                "baseline_decision": baseline_dec,
                "baseline_confidence": baseline_conf,
                "model_results": model_results,
            })

        return self._build_multi_model_result("moderator", "reasoning→support", examples, SUPPORT_MODELS)

    # ---- Experiment A2: Team Composer ----
    async def test_team_composer(self) -> Dict:
        """Test team composer role across models."""
        print(f"\n{'='*80}")
        print("TEAM COMPOSER — Support tier comparison")
        print(f"{'='*80}")

        workflows = select_test_workflows(5)
        if not workflows:
            print("  No workflows found")
            return {}

        print(f"  Selected {len(workflows)} topics for testing\n")

        examples = []
        for wf in workflows:
            topic_short = wf["topic"][:60]
            print(f"--- {topic_short} ---")

            p = build_team_composer_prompt(wf["topic"], num_experts=3)

            model_results = {}
            for model_key in SUPPORT_MODELS:
                m = MODELS[model_key]
                result = await call_llm(
                    provider=m["provider"], model=m["model"],
                    prompt=p["prompt"], system=p["system"],
                    temperature=p["temperature"], max_tokens=p["max_tokens"],
                )
                result["scores"] = score_team_composer(result["output"], expected_count=3)
                score_avg = compute_score_average(result["scores"])
                count = result["scores"].get("expert_count", 0)
                print(f"  {m['short']:8s} | score={score_avg:.2f} | experts={count} | ${result['cost']:.4f}")
                model_results[model_key] = result

            examples.append({
                "name": topic_short,
                "model_results": model_results,
            })

        return self._build_multi_model_result("team_composer", "support", examples, SUPPORT_MODELS)

    # ---- Experiment A3: Research Notes ----
    async def test_research_notes(self) -> Dict:
        """Test research notes role across models."""
        print(f"\n{'='*80}")
        print("RESEARCH NOTES — Support tier comparison")
        print(f"{'='*80}")

        test_cases = [
            {
                "name": "Quantum Drug Discovery - VQE",
                "topic": "Quantum Computing in Drug Discovery",
                "research_questions": [
                    "How do VQE and QPE compare for molecular simulation in drug discovery?",
                    "What are the current qubit requirements for pharmacologically relevant molecules?",
                ],
                "query": "variational quantum eigensolver drug molecule simulation",
            },
            {
                "name": "Indoor Cooking Smoke - Exposure",
                "topic": "Indoor cooking smoke and women's health",
                "research_questions": [
                    "What pollutants are present in indoor cooking smoke from biomass fuels?",
                    "How does chronic exposure affect respiratory and cardiovascular health?",
                ],
                "query": "biomass fuel cooking exposure PM2.5 women health",
            },
            {
                "name": "Dark Matter Detection - WIMPs",
                "topic": "Dark Matter Detection Methods",
                "research_questions": [
                    "What are the current leading methods for direct dark matter detection?",
                    "How do liquid xenon experiments compare to solid-state detectors?",
                ],
                "query": "WIMP dark matter direct detection xenon experiment sensitivity",
            },
        ]

        examples = []
        for tc in test_cases:
            print(f"\n--- {tc['name']} ---")
            p = build_research_notes_prompt(tc["topic"], tc["research_questions"], tc["query"])

            model_results = {}
            for model_key in SUPPORT_MODELS:
                m = MODELS[model_key]
                result = await call_llm(
                    provider=m["provider"], model=m["model"],
                    prompt=p["prompt"], system=p["system"],
                    temperature=p["temperature"], max_tokens=p["max_tokens"],
                )
                result["scores"] = score_research_notes(result["output"])
                score_avg = compute_score_average(result["scores"])
                src_count = result["scores"].get("source_count", 0)
                print(f"  {m['short']:8s} | score={score_avg:.2f} | sources={src_count} | ${result['cost']:.4f}")
                model_results[model_key] = result

            examples.append({
                "name": tc["name"],
                "model_results": model_results,
            })

        return self._build_multi_model_result("research_notes", "support", examples, SUPPORT_MODELS)

    # ---- Experiment B1: Reviewer ----
    async def test_reviewer(self) -> Dict:
        """Test reviewer role: Opus vs Gemini Pro."""
        print(f"\n{'='*80}")
        print("REVIEWER — Reasoning tier comparison (Opus vs Pro)")
        print(f"{'='*80}")

        workflows = select_test_workflows(3)
        if not workflows:
            print("  No workflows found")
            return {}

        print(f"  Selected {len(workflows)} manuscripts for testing\n")

        examples = []
        for wf in workflows:
            topic_short = wf["topic"][:60]
            print(f"--- {topic_short} ---")

            # Get first expert from the team to use as reviewer spec
            team = wf["expert_team"]
            if not team:
                print("  (no expert team, skipping)")
                continue
            expert = team[0]
            specialist_prompt = reconstruct_specialist_prompt(expert, wf["topic"])

            # Find the baseline review from this expert (Opus)
            baseline_review = None
            for r in wf["reviews"]:
                if r.get("model") == "claude-opus-4-6":
                    baseline_review = r
                    break

            research_type = wf.get("research_type", "survey")
            p = build_reviewer_prompt(
                manuscript=wf["manuscript"][:8000],  # Truncate for cost control
                specialist_system_prompt=specialist_prompt,
                round_number=1,
                research_type=research_type,
            )

            if baseline_review:
                baseline_avg = baseline_review.get("average", "?")
                print(f"  Opus baseline: avg={baseline_avg}/10")

            model_results = {}
            for model_key in REASONING_MODELS:
                m = MODELS[model_key]
                result = await call_llm(
                    provider=m["provider"], model=m["model"],
                    prompt=p["prompt"], system=p["system"],
                    temperature=p["temperature"], max_tokens=p["max_tokens"],
                )
                result["scores"] = score_reviewer(result["output"], baseline_review)
                score_avg = compute_score_average(result["scores"])
                review_avg = result["scores"].get("avg_score", "?")
                dev = result["scores"].get("score_deviation", "N/A")
                print(f"  {m['short']:8s} | quality={score_avg:.2f} | review_avg={review_avg} | deviation={dev} | ${result['cost']:.4f}")
                model_results[model_key] = result

            examples.append({
                "name": topic_short,
                "baseline_review_avg": baseline_review.get("average") if baseline_review else None,
                "model_results": model_results,
            })

        return self._build_multi_model_result("reviewer", "reasoning", examples, REASONING_MODELS)

    # ---- Result Builders ----
    def _build_multi_model_result(
        self,
        role: str,
        tier: str,
        examples: List[Dict],
        model_keys: List[str],
    ) -> Dict:
        """Build result summary for a role tested across multiple models."""
        per_model = {}
        for mk in model_keys:
            model_scores = []
            model_costs = []
            decision_matches = []
            for ex in examples:
                mr = ex.get("model_results", {}).get(mk)
                if mr:
                    model_scores.append(compute_score_average(mr["scores"]))
                    model_costs.append(mr["cost"])
                    if "decision_match" in mr["scores"]:
                        decision_matches.append(mr["scores"]["decision_match"])

            avg_score = sum(model_scores) / len(model_scores) if model_scores else 0
            avg_cost = sum(model_costs) / len(model_costs) if model_costs else 0
            match_rate = sum(decision_matches) / len(decision_matches) if decision_matches else None

            # Recommendation logic
            if avg_score >= 0.85:
                rec = "REPLACE"
            elif avg_score >= 0.70:
                rec = "NEEDS_REVIEW"
            else:
                rec = "KEEP_CURRENT"

            per_model[mk] = {
                "avg_score": round(avg_score, 3),
                "avg_cost": round(avg_cost, 6),
                "total_cost": round(sum(model_costs), 6),
                "decision_match_rate": round(match_rate, 3) if match_rate is not None else None,
                "recommendation": rec,
            }

        result = {
            "role": role,
            "tier": tier,
            "examples": examples,
            "per_model": per_model,
            "model_keys": model_keys,
        }
        self.results.append(result)
        return result

    # ---- Output ----
    def print_summary(self):
        """Print comprehensive summary table."""
        print(f"\n{'='*100}")
        print("MODEL COMPARISON SUMMARY")
        print(f"{'='*100}\n")

        header = f"{'Role':<18s} {'Model':<22s} {'Score':>7s} {'Decision Match':>16s} {'Avg Cost':>10s} {'Recommendation':>16s}"
        print(header)
        print("-" * len(header))

        total_cost = 0.0

        for r in self.results:
            for mk in r["model_keys"]:
                pm = r["per_model"].get(mk, {})
                short = MODELS.get(mk, {}).get("short", mk)
                score = pm.get("avg_score", 0)
                match_rate = pm.get("decision_match_rate")
                match_str = f"{match_rate:.0%}" if match_rate is not None else "N/A"
                cost = pm.get("avg_cost", 0)
                rec = pm.get("recommendation", "?")
                total_cost += pm.get("total_cost", 0)

                print(f"{r['role']:<18s} {short:<22s} {score:>7.3f} {match_str:>16s} ${cost:>9.4f} {rec:>16s}")
            print()

        print(f"\nTotal API cost for this benchmark: ${total_cost:.4f}")
        print()

    def save_results(self, filename: str = "model_comparison_results.json"):
        """Save results to JSON files."""
        # Slim version (truncate outputs)
        slim = json.loads(json.dumps(self.results, default=str))
        for role_result in slim:
            for ex in role_result.get("examples", []):
                for mk, mr in ex.get("model_results", {}).items():
                    out = mr.get("output", "")
                    if isinstance(out, str) and len(out) > 500:
                        mr["output"] = out[:500] + f"... [{len(out)} chars total]"

        with open(filename, "w") as f:
            json.dump(slim, f, indent=2, ensure_ascii=False)
        print(f"Results saved to: {filename}")

        # Full version
        full_file = filename.replace(".json", "_full.json")
        with open(full_file, "w") as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False, default=str)
        print(f"Full outputs saved to: {full_file}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(
        description="Model Comparison Benchmark — test alternative models for Support & Reasoning tiers"
    )
    parser.add_argument("--all", action="store_true", help="Run all experiments")
    parser.add_argument("--group", choices=["A", "B"], help="A=Support tier, B=Reasoning tier")
    parser.add_argument("--role", choices=["moderator", "team_composer", "reviewer", "research_notes"],
                        help="Test a specific role")
    args = parser.parse_args()

    # Default to --all if nothing specified
    if not args.all and not args.group and not args.role:
        args.all = True

    tester = ModelComparisonTester()

    run_a = args.all or args.group == "A"
    run_b = args.all or args.group == "B"

    if args.role == "moderator" or run_a:
        await tester.test_moderator()
    if args.role == "team_composer" or run_a:
        await tester.test_team_composer()
    if args.role == "research_notes" or run_a:
        await tester.test_research_notes()
    if args.role == "reviewer" or run_b:
        await tester.test_reviewer()

    tester.print_summary()
    tester.save_results()


if __name__ == "__main__":
    asyncio.run(main())
