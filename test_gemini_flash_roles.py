#!/usr/bin/env python3
"""
Gemini Flash Comprehensive Quality Test

Tests individual roles with **production prompts** and **real seed data** to compare:
- Claude Haiku/Sonnet (current) vs Gemini 2.5 Flash
- Automated quality scoring per role
- Cost comparison

Usage:
    python3 test_gemini_flash_roles.py --phase 1   # categorizer + desk_editor
    python3 test_gemini_flash_roles.py --phase 2   # author_response
    python3 test_gemini_flash_roles.py --phase 3   # citation_verifier + research_notes
    python3 test_gemini_flash_roles.py --phase 0   # all phases
"""

import json
import asyncio
import re
import warnings
from pathlib import Path
from typing import Dict, Any, List, Optional
import sys

from dotenv import load_dotenv
load_dotenv()

# Suppress google.generativeai FutureWarning
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from research_cli.model_config import _create_llm, get_pricing
from research_cli.categories import ACADEMIC_CATEGORIES, _build_category_list

# ---------------------------------------------------------------------------
# Seed data paths
# ---------------------------------------------------------------------------
SEED_ROOT = Path(__file__).parent / "seed-data" / "results"
SEED_DIRS = {
    "quantum": SEED_ROOT / "quantum-computing-in-drug-discovery",
    "homo": SEED_ROOT / "homo-sapiens-20260208-121417",
    "indoor": SEED_ROOT / "indoor-cooking-smoke-and-women-s-health-20260208-121214",
    "derrida": SEED_ROOT / "derrida-s-life-and-philosophy-20260207-163031",
    "perovskite": SEED_ROOT / "perovskite-solar-cells-stability-challenges-and-solutions-20260207-174135",
    "cbdc": SEED_ROOT / "central-bank-digital-currencies-economic-implications-20260207-174129",
    "dark_matter": SEED_ROOT / "dark-matter-detection-methods-current-state-and-challenges-20260207-174123",
    "rag": SEED_ROOT / "retrieval-augmented-generation-architectures-and-limitations-20260207-174154",
}


def _read_seed(key: str, filename: str) -> str:
    """Read a seed data file, return empty string if missing."""
    path = SEED_DIRS.get(key, Path("/dev/null")) / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _read_seed_json(key: str, filename: str) -> Any:
    """Read a seed JSON file."""
    text = _read_seed(key, filename)
    if text:
        return json.loads(text)
    return {}


# ---------------------------------------------------------------------------
# Production prompts — exactly matching the codebase
# ---------------------------------------------------------------------------

CATEGORY_LIST = _build_category_list()


def build_categorizer_prompt(topic: str) -> dict:
    """Production categorizer prompt from categories.py:423-433."""
    return {
        "system": "You classify academic topics. Respond with ONLY the category in major/subfield format. No JSON, no explanation. The topic may be in any language.",
        "prompt": f"""Classify this research topic into exactly one academic category.

TOPIC: {topic}

VALID CATEGORIES (format: major/subfield):
{CATEGORY_LIST}

Respond with ONLY one line in this exact format:
major/subfield

Example: social_sciences/anthropology""",
        "temperature": 0.0,
        "max_tokens": 50,
    }


def build_desk_editor_prompt(manuscript: str, topic: str) -> dict:
    """Production desk editor prompt from agents/desk_editor.py:35-59."""
    return {
        "system": (
            "You are a journal editor performing a quick desk screening. "
            "Decide whether a manuscript should proceed to full peer review "
            "or be desk-rejected for obvious fatal flaws. "
            "Be lenient: only reject manuscripts with clear, undeniable problems. "
            "When in doubt, PASS."
        ),
        "prompt": f"""Screen this manuscript submitted for the topic: "{topic}"

MANUSCRIPT (first 3000 chars):
{manuscript[:3000]}

---

Desk-reject ONLY if ANY of these apply:
1. Content is completely unrelated to the stated topic
2. Manuscript is extremely short or lacks any structure (no sections/headings)
3. Text is meaningless, garbled, or clearly non-academic (e.g. lorem ipsum)
4. Critical sections are entirely missing (no introduction AND no analysis AND no conclusion)

If the manuscript has reasonable content related to the topic, PASS it.

Respond in JSON:
{{"decision": "PASS" or "DESK_REJECT", "reason": "<one sentence explanation>"}}""",
        "temperature": 0.1,
        "max_tokens": 512,
    }


def _consolidate_feedback(reviews: List[Dict]) -> str:
    """Mirror of WriterAgent._consolidate_feedback from writer.py:588-632."""
    parts = []
    for review in reviews:
        specialist = review["specialist_name"]
        scores = review["scores"]
        avg = review["average"]
        citations_line = f"\n- Citations: {scores['citations']}/10" if "citations" in scores else ""
        part = f"""
## {specialist} (Average: {avg}/10)

**Scores:**
- Accuracy: {scores['accuracy']}/10
- Completeness: {scores['completeness']}/10
- Clarity: {scores['clarity']}/10
- Novelty: {scores['novelty']}/10
- Rigor: {scores['rigor']}/10{citations_line}

**Summary:**
{review['summary']}

**Strengths:**
{chr(10).join('- ' + s for s in review['strengths'])}

**Weaknesses:**
{chr(10).join('- ' + w for w in review['weaknesses'])}

**Suggestions:**
{chr(10).join('- ' + s for s in review['suggestions'])}

**Detailed Feedback:**
{review['detailed_feedback']}
"""
        parts.append(part)
    return "\n---\n".join(parts)


def build_author_response_prompt(manuscript: str, reviews: List[Dict], round_number: int = 1) -> dict:
    """Production author response prompt from writer.py:348-416."""
    feedback_summary = _consolidate_feedback(reviews)
    return {
        "system": """You are the author of a research manuscript responding to peer review feedback.

Your role:
- Address each reviewer's concerns directly and professionally
- Explain what changes you will make (or have made)
- Clarify misunderstandings or provide additional context
- Respectfully disagree when reviewer criticism is not applicable
- Show engagement with feedback and willingness to improve

Write a professional author response that demonstrates:
- Careful reading of all reviews
- Clear plan for addressing substantive concerns
- Rationale for decisions (what to change, what to keep)
- Respect for reviewers' time and expertise""",
        "prompt": f"""You have received peer reviews for your manuscript. Write a detailed response addressing each reviewer.

ROUND: {round_number}

MANUSCRIPT SUMMARY:
[Word count: {len(manuscript.split())} words]

REVIEWER FEEDBACK:
{feedback_summary}

---

Write a professional author response with the following structure:

## Author Response - Round {round_number}

### Overview
[1-2 paragraphs: thank reviewers, summarize key themes in feedback, outline revision strategy]

### Response to Reviewer 1 ([Reviewer Name])
**Overall Assessment**: [Acknowledge their score and main concerns]

**Major Points**:
1. [Reviewer concern 1]
   - **Our response**: [What you will change/clarify/explain]
   - **Action taken**: [Specific changes made or planned]

2. [Reviewer concern 2]
   - **Our response**: ...
   - **Action taken**: ...

**Minor Points**: [Address smaller suggestions collectively]

### Response to Reviewer 2 ([Reviewer Name])
[Same structure]

### Response to Reviewer 3 ([Reviewer Name])
[Same structure]

### Summary of Changes
- [List major revisions planned/made]
- [Clarifications added]
- [New analysis/data included]

---

Guidelines:
- Be specific about what you will change
- Provide rationale for disagreements (respectfully)
- Show you understand the criticism even if you disagree
- Keep tone professional and collaborative
- Focus on substantive issues, not minor wording

Write the complete author response now.""",
        "temperature": 0.7,
        "max_tokens": 4096,
    }


def build_citation_verifier_prompt(manuscript: str, references_text: str) -> dict:
    """Production citation verifier prompt from writer.py:676-709."""
    return {
        "system": """You are a citation verification specialist. Your ONLY job is to strengthen the citation apparatus of a research manuscript.

Rules:
- Every substantive claim, statistic, or technical assertion MUST have an inline citation [N]
- Use ONLY the provided verified references — never fabricate citations
- Add citations where they are missing; do not remove existing valid ones
- Ensure the References section at the end lists all cited sources with full details
- Do not change the manuscript's arguments, structure, or prose — ONLY add/fix citations
- If a claim cannot be supported by any available reference, flag it with [citation needed]
- Output the complete manuscript with citations fixed""",
        "prompt": f"""CITATION VERIFICATION PASS

Review this manuscript and ensure every substantive claim is properly cited.

MANUSCRIPT:
{manuscript}

---

VERIFIED REFERENCES (use these for citations):
{references_text}

---

INSTRUCTIONS:
1. Read through the manuscript paragraph by paragraph
2. For each substantive claim, check if it has an inline citation [N]
3. If a claim lacks citation but a matching reference exists, add the citation
4. If multiple references support a claim, cite the most relevant one
5. Ensure the References section at the end is complete and matches inline citations
6. Do NOT change the manuscript content, structure, or arguments — only fix citations

Output the complete manuscript with all citations verified and gaps filled.""",
        "temperature": 0.3,
        "max_tokens": 16384,
    }


def build_research_notes_prompt(topic: str, research_questions: List[str], query: str) -> dict:
    """Production research notes prompt from research_notes_agent.py:73-123."""
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
# Automated scoring functions
# ---------------------------------------------------------------------------

def score_categorizer(output: str, expected_major: str, expected_subfield: str) -> Dict[str, Any]:
    """Score categorizer output against expected category."""
    content = output.strip().lower()
    scores = {"parse_success": False, "valid_category": False, "correct": False}
    parsed_major, parsed_sub = None, None

    for line in content.split("\n"):
        line = line.strip().strip("`").strip('"').strip("'")
        if "/" in line:
            parts = line.split("/")
            parsed_major = parts[0].strip()
            parsed_sub = parts[1].strip()
            scores["parse_success"] = True
            break

    if parsed_major and parsed_sub:
        if parsed_major in ACADEMIC_CATEGORIES and parsed_sub in ACADEMIC_CATEGORIES[parsed_major]["subfields"]:
            scores["valid_category"] = True
        if parsed_major == expected_major and parsed_sub == expected_subfield:
            scores["correct"] = True

    scores["parsed"] = f"{parsed_major}/{parsed_sub}" if parsed_major else content[:80]
    return scores


def score_desk_editor(output: str, expected_decision: str) -> Dict[str, Any]:
    """Score desk editor output."""
    content = output.strip()
    # Strip markdown code fences
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    scores = {"json_valid": False, "decision_valid": False, "correct_decision": False}

    try:
        data = json.loads(content)
        scores["json_valid"] = True
        decision = data.get("decision", "").upper()
        if decision in ("PASS", "DESK_REJECT"):
            scores["decision_valid"] = True
            if decision == expected_decision:
                scores["correct_decision"] = True
        scores["parsed_decision"] = decision
        scores["reason"] = data.get("reason", "")[:200]
    except json.JSONDecodeError:
        # Try to extract decision from non-JSON output
        upper = content.upper()
        if "DESK_REJECT" in upper:
            scores["parsed_decision"] = "DESK_REJECT"
            scores["decision_valid"] = True
            scores["correct_decision"] = (expected_decision == "DESK_REJECT")
        elif "PASS" in upper:
            scores["parsed_decision"] = "PASS"
            scores["decision_valid"] = True
            scores["correct_decision"] = (expected_decision == "PASS")
        else:
            scores["parsed_decision"] = content[:80]

    return scores


def score_author_response(output: str, reviewer_names: List[str]) -> Dict[str, Any]:
    """Score author response quality."""
    content = output.strip()
    words = content.split()
    word_count = len(words)
    lower = content.lower()

    scores = {
        "addresses_all_reviewers": all(
            name.lower() in lower for name in reviewer_names
        ),
        "has_structure": any(
            kw in lower for kw in ["overview", "response to reviewer", "summary of changes"]
        ),
        "word_count_ok": 200 <= word_count <= 5000,
        "professionalism": sum(
            1 for kw in ["acknowledge", "revision", "address", "response", "concern", "suggestion"]
            if kw in lower
        ) >= 3,
    }
    scores["word_count"] = word_count
    return scores


def score_citation_verifier(output: str, original_headings: List[str]) -> Dict[str, Any]:
    """Score citation verifier output."""
    content = output.strip()
    words = content.split()

    # Check for inline citations like [1], [2], etc.
    citation_matches = re.findall(r'\[(\d+)\]', content)
    unique_citations = set(citation_matches)

    # Check last 50 lines for a References heading
    last_lines = "\n".join(content.split("\n")[-50:]).lower()
    has_refs = "## references" in last_lines or "# references" in last_lines

    scores = {
        "is_manuscript": len(words) >= 500 and any(h in content for h in ["##", "# "]),
        "has_citations": len(unique_citations) >= 3,
        "has_references_section": has_refs,
        "no_content_change": sum(1 for h in original_headings if h.lower() in content.lower()) >= len(original_headings) * 0.6,
    }
    scores["citation_count"] = len(unique_citations)
    scores["word_count"] = len(words)
    return scores


def score_research_notes(output: str) -> Dict[str, Any]:
    """Score research notes output."""
    content = output.strip()
    # Strip markdown code fences
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    scores = {"json_valid": False, "has_sources": False, "fields_complete": False, "source_type_valid": False}

    try:
        data = json.loads(content)
        scores["json_valid"] = True
        sources = data.get("sources", [])
        scores["source_count"] = len(sources)
        scores["has_sources"] = 3 <= len(sources) <= 7

        if sources:
            required_fields = {"source", "source_type", "key_findings", "relevance"}
            valid_types = {"paper", "documentation", "blog", "github"}
            fields_ok = all(
                required_fields.issubset(set(s.keys())) for s in sources
            )
            types_ok = all(
                s.get("source_type", "").lower() in valid_types for s in sources
            )
            scores["fields_complete"] = fields_ok
            scores["source_type_valid"] = types_ok
    except json.JSONDecodeError:
        scores["source_count"] = 0

    return scores


def compute_score_average(scores: Dict[str, Any]) -> float:
    """Compute average of boolean scores (ignoring non-bool fields)."""
    bools = [v for v in scores.values() if isinstance(v, bool)]
    if not bools:
        return 0.0
    return sum(bools) / len(bools)


# ---------------------------------------------------------------------------
# Test case definitions
# ---------------------------------------------------------------------------

def get_categorizer_examples() -> List[Dict]:
    """8 topics across 8 fields (including 1 Korean)."""
    return [
        {"name": "Quantum Computing Drug Discovery", "topic": "Quantum Computing in Drug Discovery",
         "expected_major": "medicine_health", "expected_subfield": "pharmacology"},
        {"name": "Homo Sapiens Relatives (Korean)", "topic": "현존하는 육상생물 다 포함하여 homo sapiens와 가장 가까운 근연종",
         "expected_major": "natural_sciences", "expected_subfield": "biology"},
        {"name": "Derrida Philosophy", "topic": "Derrida's Life and Philosophy",
         "expected_major": "humanities", "expected_subfield": "philosophy"},
        {"name": "Indoor Cooking Smoke Health", "topic": "Indoor cooking smoke and women's health",
         "expected_major": "medicine_health", "expected_subfield": "public_health"},
        {"name": "Perovskite Solar Cells", "topic": "Perovskite Solar Cells: Stability Challenges and Solutions",
         "expected_major": "engineering", "expected_subfield": "materials"},
        {"name": "CBDC Economic Implications", "topic": "Central Bank Digital Currencies: Economic Implications",
         "expected_major": "business_economics", "expected_subfield": "finance"},
        {"name": "Dark Matter Detection", "topic": "Dark Matter Detection Methods",
         "expected_major": "natural_sciences", "expected_subfield": "physics"},
        {"name": "RAG Architectures", "topic": "Retrieval-Augmented Generation Architectures and Limitations",
         "expected_major": "computer_science", "expected_subfield": "ai_ml"},
    ]


def get_desk_editor_examples() -> List[Dict]:
    """4 manuscripts: 3 real + 1 synthetic bad."""
    examples = []
    for key, topic, decision in [
        ("quantum", "Quantum Computing in Drug Discovery", "PASS"),
        ("homo", "현존하는 육상생물 다 포함하여 homo sapiens와 가장 가까운 근연종", "PASS"),
        ("indoor", "Indoor cooking smoke and women's health", "PASS"),
    ]:
        ms = _read_seed(key, "manuscript_v1.md")
        if ms:
            examples.append({"name": f"{key} (PASS)", "manuscript": ms, "topic": topic, "expected": decision})

    # Synthetic bad manuscript
    examples.append({
        "name": "Lorem Ipsum (DESK_REJECT)",
        "manuscript": (
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
            "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
            "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris. "
        ) * 20,
        "topic": "Machine Learning in Healthcare",
        "expected": "DESK_REJECT",
    })
    return examples


def get_author_response_examples() -> List[Dict]:
    """3 real review sets from seed data."""
    examples = []
    for key, label in [
        ("quantum", "Quantum Computing"),
        ("indoor", "Indoor Cooking Smoke"),
        ("homo", "Homo Sapiens"),
    ]:
        ms = _read_seed(key, "manuscript_v1.md")
        r1 = _read_seed_json(key, "round_1.json")
        if ms and r1 and "reviews" in r1:
            reviewer_names = [r["specialist_name"] for r in r1["reviews"]]
            examples.append({
                "name": f"{label} (Round 1, {len(r1['reviews'])} reviewers)",
                "manuscript": ms,
                "reviews": r1["reviews"],
                "reviewer_names": reviewer_names,
            })
    return examples


def get_citation_verifier_examples() -> List[Dict]:
    """2 manuscripts with references for citation verification."""
    examples = []
    for key, label in [("quantum", "Quantum Computing"), ("indoor", "Indoor Cooking Smoke")]:
        ms = _read_seed(key, "manuscript_v1.md")
        if not ms:
            continue
        # Extract reference section from manuscript itself
        refs_text = ""
        lines = ms.split("\n")
        ref_start = None
        for i, line in enumerate(lines):
            if line.strip().lower().startswith("## reference"):
                ref_start = i
                break
        if ref_start is not None:
            refs_text = "\n".join(lines[ref_start:])

        if not refs_text:
            refs_text = "(References embedded in manuscript)"

        # Extract headings for quality check
        headings = [l.strip("# ").strip() for l in lines if l.startswith("##")]

        examples.append({
            "name": label,
            "manuscript": ms,
            "references_text": refs_text,
            "headings": headings,
        })
    return examples


def get_research_notes_examples() -> List[Dict]:
    """3 topics with research questions and queries."""
    return [
        {
            "name": "Quantum Drug Discovery - VQE",
            "topic": "Quantum Computing in Drug Discovery",
            "research_questions": [
                "How do VQE and QPE compare for molecular simulation in drug discovery?",
                "What are the current qubit requirements for pharmacologically relevant molecules?",
                "What are the main barriers to quantum advantage in pharmaceutical applications?",
            ],
            "query": "variational quantum eigensolver drug molecule simulation",
        },
        {
            "name": "Indoor Cooking Smoke - Exposure",
            "topic": "Indoor cooking smoke and women's health",
            "research_questions": [
                "What pollutants are present in indoor cooking smoke from biomass fuels?",
                "How does chronic exposure affect respiratory and cardiovascular health?",
                "What intervention strategies have proven effective?",
            ],
            "query": "biomass fuel cooking exposure assessment PM2.5 women health",
        },
        {
            "name": "Dark Matter Detection - WIMPs",
            "topic": "Dark Matter Detection Methods",
            "research_questions": [
                "What are the current leading methods for direct dark matter detection?",
                "How do liquid xenon experiments compare to solid-state detectors?",
                "What are the theoretical constraints on WIMP cross-sections?",
            ],
            "query": "WIMP dark matter direct detection xenon experiment sensitivity",
        },
    ]


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

class ComprehensiveRoleTester:
    """Test roles with production prompts, real data, and automated scoring."""

    # Models
    CLAUDE_HAIKU = {"provider": "anthropic", "model": "claude-haiku-4-5"}
    CLAUDE_SONNET = {"provider": "anthropic", "model": "claude-sonnet-4-5"}
    GEMINI_FLASH = {"provider": "google", "model": "gemini-2.5-flash"}

    def __init__(self):
        self.results: List[Dict] = []

    async def _call_llm(self, provider: str, model: str, prompt: str, system: str,
                        temperature: float, max_tokens: int) -> Dict:
        """Call LLM and return output + token info."""
        llm = _create_llm(provider=provider, model=model)
        # Gemini 2.5 Flash is a "thinking" model — thinking tokens consume
        # max_output_tokens budget, so we need a higher ceiling to get usable output.
        effective_max = max_tokens
        if provider == "google" and "2.5" in model:
            effective_max = max(max_tokens * 8, 2048)

        try:
            resp = await llm.generate(
                prompt=prompt, system=system,
                temperature=temperature, max_tokens=effective_max,
            )
            content = resp.content
            input_tokens = resp.input_tokens
            output_tokens = resp.output_tokens
        except (ValueError, Exception) as e:
            # Gemini safety filter or other API errors
            print(f"    ERROR ({model}): {e}")
            content = f"[ERROR: {e}]"
            input_tokens = 0
            output_tokens = 0

        pricing = get_pricing(model)
        cost = (
            (input_tokens or 0) * pricing["input"] / 1_000_000 +
            (output_tokens or 0) * pricing["output"] / 1_000_000
        )
        return {
            "model": model,
            "output": content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
        }

    # ---- Categorizer ----
    async def test_categorizer(self) -> Dict:
        print(f"\n{'='*80}")
        print("CATEGORIZER — 8 topics, production prompt")
        print(f"{'='*80}")

        examples_out = []
        for ex in get_categorizer_examples():
            p = build_categorizer_prompt(ex["topic"])
            print(f"\n--- {ex['name']} ---")

            claude = await self._call_llm(**self.CLAUDE_HAIKU, **p)
            flash = await self._call_llm(**self.GEMINI_FLASH, **p)

            claude["scores"] = score_categorizer(claude["output"], ex["expected_major"], ex["expected_subfield"])
            flash["scores"] = score_categorizer(flash["output"], ex["expected_major"], ex["expected_subfield"])

            self._print_comparison(ex["name"], claude, flash,
                                   expected=f"{ex['expected_major']}/{ex['expected_subfield']}")
            examples_out.append(self._build_example_result(ex["name"], claude, flash))

        return self._build_role_result("categorizer", "light", examples_out)

    # ---- Desk Editor ----
    async def test_desk_editor(self) -> Dict:
        print(f"\n{'='*80}")
        print("DESK EDITOR — 4 manuscripts, production prompt")
        print(f"{'='*80}")

        examples_out = []
        for ex in get_desk_editor_examples():
            p = build_desk_editor_prompt(ex["manuscript"], ex["topic"])
            print(f"\n--- {ex['name']} ---")

            claude = await self._call_llm(**self.CLAUDE_HAIKU, **p)
            flash = await self._call_llm(**self.GEMINI_FLASH, **p)

            claude["scores"] = score_desk_editor(claude["output"], ex["expected"])
            flash["scores"] = score_desk_editor(flash["output"], ex["expected"])

            self._print_comparison(ex["name"], claude, flash, expected=ex["expected"])
            examples_out.append(self._build_example_result(ex["name"], claude, flash))

        return self._build_role_result("desk_editor", "light", examples_out)

    # ---- Author Response ----
    async def test_author_response(self) -> Dict:
        print(f"\n{'='*80}")
        print("AUTHOR RESPONSE — 3 review sets, production prompt")
        print(f"{'='*80}")

        examples_out = []
        for ex in get_author_response_examples():
            p = build_author_response_prompt(ex["manuscript"], ex["reviews"])
            print(f"\n--- {ex['name']} ---")

            claude = await self._call_llm(**self.CLAUDE_HAIKU, prompt=p["prompt"],
                                          system=p["system"], temperature=p["temperature"],
                                          max_tokens=p["max_tokens"])
            flash = await self._call_llm(**self.GEMINI_FLASH, prompt=p["prompt"],
                                         system=p["system"], temperature=p["temperature"],
                                         max_tokens=p["max_tokens"])

            claude["scores"] = score_author_response(claude["output"], ex["reviewer_names"])
            flash["scores"] = score_author_response(flash["output"], ex["reviewer_names"])

            self._print_comparison(ex["name"], claude, flash)
            examples_out.append(self._build_example_result(ex["name"], claude, flash))

        return self._build_role_result("author_response", "light", examples_out)

    # ---- Citation Verifier ----
    async def test_citation_verifier(self) -> Dict:
        print(f"\n{'='*80}")
        print("CITATION VERIFIER — 2 manuscripts, production prompt")
        print(f"{'='*80}")

        examples_out = []
        for ex in get_citation_verifier_examples():
            p = build_citation_verifier_prompt(ex["manuscript"], ex["references_text"])
            print(f"\n--- {ex['name']} ---")

            claude = await self._call_llm(**self.CLAUDE_SONNET, prompt=p["prompt"],
                                          system=p["system"], temperature=p["temperature"],
                                          max_tokens=p["max_tokens"])
            flash = await self._call_llm(**self.GEMINI_FLASH, prompt=p["prompt"],
                                         system=p["system"], temperature=p["temperature"],
                                         max_tokens=p["max_tokens"])

            claude["scores"] = score_citation_verifier(claude["output"], ex["headings"])
            flash["scores"] = score_citation_verifier(flash["output"], ex["headings"])

            self._print_comparison(ex["name"], claude, flash)
            examples_out.append(self._build_example_result(ex["name"], claude, flash))

        return self._build_role_result("citation_verifier", "support", examples_out)

    # ---- Research Notes ----
    async def test_research_notes(self) -> Dict:
        print(f"\n{'='*80}")
        print("RESEARCH NOTES — 3 topics, production prompt")
        print(f"{'='*80}")

        examples_out = []
        for ex in get_research_notes_examples():
            p = build_research_notes_prompt(ex["topic"], ex["research_questions"], ex["query"])
            print(f"\n--- {ex['name']} ---")

            claude = await self._call_llm(**self.CLAUDE_SONNET, prompt=p["prompt"],
                                          system=p["system"], temperature=p["temperature"],
                                          max_tokens=p["max_tokens"])
            flash = await self._call_llm(**self.GEMINI_FLASH, prompt=p["prompt"],
                                         system=p["system"], temperature=p["temperature"],
                                         max_tokens=p["max_tokens"])

            claude["scores"] = score_research_notes(claude["output"])
            flash["scores"] = score_research_notes(flash["output"])

            self._print_comparison(ex["name"], claude, flash)
            examples_out.append(self._build_example_result(ex["name"], claude, flash))

        return self._build_role_result("research_notes", "support", examples_out)

    # ---- Helpers ----
    def _build_example_result(self, name: str, claude: Dict, flash: Dict) -> Dict:
        claude_cost = claude["cost"]
        flash_cost = flash["cost"]
        return {
            "name": name,
            "claude": claude,
            "flash": flash,
            "cost_savings_pct": ((claude_cost - flash_cost) / claude_cost * 100) if claude_cost > 0 else 0,
        }

    def _build_role_result(self, role: str, tier: str, examples: List[Dict]) -> Dict:
        claude_scores = [compute_score_average(e["claude"]["scores"]) for e in examples]
        flash_scores = [compute_score_average(e["flash"]["scores"]) for e in examples]
        avg_claude = sum(claude_scores) / len(claude_scores) if claude_scores else 0
        avg_flash = sum(flash_scores) / len(flash_scores) if flash_scores else 0
        avg_savings = sum(e["cost_savings_pct"] for e in examples) / len(examples) if examples else 0

        # Recommendation logic
        if avg_flash >= avg_claude - 0.05:
            recommendation = "REPLACE"
        elif avg_flash >= avg_claude - 0.15:
            recommendation = "NEEDS_REVIEW"
        else:
            recommendation = "KEEP_CLAUDE"

        result = {
            "role": role,
            "tier": tier,
            "examples": examples,
            "summary": {
                "claude_avg_score": round(avg_claude, 3),
                "flash_avg_score": round(avg_flash, 3),
                "score_delta": round(avg_flash - avg_claude, 3),
                "avg_cost_savings_pct": round(avg_savings, 1),
                "recommendation": recommendation,
            },
        }
        self.results.append(result)
        return result

    def _print_comparison(self, name: str, claude: Dict, flash: Dict,
                          expected: str = ""):
        """Print side-by-side comparison."""
        c_score = compute_score_average(claude["scores"])
        f_score = compute_score_average(flash["scores"])
        savings = ((claude["cost"] - flash["cost"]) / claude["cost"] * 100) if claude["cost"] > 0 else 0

        if expected:
            print(f"  Expected: {expected}")

        print(f"  {claude['model']:25s} | score={c_score:.2f} | "
              f"{claude.get('input_tokens', 0):>5} in/{claude.get('output_tokens', 0):>5} out | "
              f"${claude['cost']:.6f}")
        print(f"    -> {claude['output'][:120]}...")
        print(f"    scores: {claude['scores']}")

        print(f"  {flash['model']:25s} | score={f_score:.2f} | "
              f"{flash.get('input_tokens', 0):>5} in/{flash.get('output_tokens', 0):>5} out | "
              f"${flash['cost']:.6f}")
        print(f"    -> {flash['output'][:120]}...")
        print(f"    scores: {flash['scores']}")

        print(f"  Cost savings: {savings:.1f}%")

    # ---- Phase runner ----
    async def run_phase(self, phase: int):
        if phase == 1:
            print("\n" + "=" * 80)
            print("PHASE 1: Categorizer + Desk Editor (Light tier)")
            print("=" * 80)
            await self.test_categorizer()
            await self.test_desk_editor()

        elif phase == 2:
            print("\n" + "=" * 80)
            print("PHASE 2: Author Response (Light tier, longer output)")
            print("=" * 80)
            await self.test_author_response()

        elif phase == 3:
            print("\n" + "=" * 80)
            print("PHASE 3: Citation Verifier + Research Notes (Support tier)")
            print("=" * 80)
            await self.test_citation_verifier()
            await self.test_research_notes()

        else:
            print(f"Invalid phase: {phase}")
            return

    def print_summary(self):
        """Print comprehensive summary table."""
        print(f"\n{'='*100}")
        print("COMPREHENSIVE QUALITY & COST COMPARISON")
        print(f"{'='*100}\n")

        header = f"{'Role':22s} {'Tier':8s} {'Claude Score':>12s} {'Flash Score':>12s} {'Delta':>7s} {'Savings':>8s} {'Recommendation':>16s}"
        print(header)
        print("-" * len(header))

        total_claude_cost = 0
        total_flash_cost = 0

        for r in self.results:
            s = r["summary"]
            print(f"{r['role']:22s} {r['tier']:8s} "
                  f"{s['claude_avg_score']:>12.3f} {s['flash_avg_score']:>12.3f} "
                  f"{s['score_delta']:>+7.3f} {s['avg_cost_savings_pct']:>7.1f}% "
                  f"{s['recommendation']:>16s}")

            for ex in r["examples"]:
                total_claude_cost += ex["claude"]["cost"]
                total_flash_cost += ex["flash"]["cost"]

        print("-" * len(header))
        if total_claude_cost > 0:
            total_savings = (total_claude_cost - total_flash_cost) / total_claude_cost * 100
        else:
            total_savings = 0
        print(f"{'TOTAL COST':22s} {'':8s} "
              f"{'$'+f'{total_claude_cost:.6f}':>12s} {'$'+f'{total_flash_cost:.6f}':>12s} "
              f"{'':>7s} {total_savings:>7.1f}%")

        # Flag items needing manual review
        review_items = []
        for r in self.results:
            s = r["summary"]
            if s["recommendation"] == "NEEDS_REVIEW":
                review_items.append(r["role"])
            # Also flag individual examples with big score gaps
            for ex in r["examples"]:
                c_s = compute_score_average(ex["claude"]["scores"])
                f_s = compute_score_average(ex["flash"]["scores"])
                if f_s < c_s - 0.2:
                    review_items.append(f"  - {r['role']}/{ex['name']} (claude={c_s:.2f}, flash={f_s:.2f})")

        if review_items:
            print(f"\nItems needing manual review:")
            for item in review_items:
                print(f"  {item}")

        print()

    def save_results(self, filename: str = "gemini_flash_comprehensive_results.json"):
        """Save full results to JSON."""
        # Truncate large outputs for readability
        slim = json.loads(json.dumps(self.results, default=str))
        for role in slim:
            for ex in role.get("examples", []):
                for model_key in ("claude", "flash"):
                    m = ex.get(model_key, {})
                    out = m.get("output", "")
                    if len(out) > 500:
                        m["output"] = out[:500] + f"... [{len(out)} chars total]"

        with open(filename, "w") as f:
            json.dump(slim, f, indent=2, ensure_ascii=False)
        print(f"Results saved to: {filename}")

        # Also save full outputs separately
        full_file = filename.replace(".json", "_full.json")
        with open(full_file, "w") as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False, default=str)
        print(f"Full outputs saved to: {full_file}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Comprehensive Gemini Flash quality test with production prompts")
    parser.add_argument("--phase", type=int, choices=[0, 1, 2, 3], default=0,
                        help="Test phase: 0=All, 1=categorizer+desk_editor, 2=author_response, 3=citation_verifier+research_notes")
    args = parser.parse_args()

    tester = ComprehensiveRoleTester()

    if args.phase == 0:
        for p in [1, 2, 3]:
            await tester.run_phase(p)
    else:
        await tester.run_phase(args.phase)

    tester.print_summary()
    tester.save_results()


if __name__ == "__main__":
    asyncio.run(main())
