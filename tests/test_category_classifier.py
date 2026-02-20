"""Tests for topic category classification fixes.

Proves:
1. Keyword fallback correctly classifies biology/medicine topics (no more CS default)
2. suggest_category_llm falls back gracefully when LLM fails
3. Default for unknown topics is no longer computer_science/theory
4. Desk editor receives and uses category information
5. LLM classifier routes 20 diverse topics to correct major/subfield (mock LLM)
6. Desk editor detects field mismatch with mock manuscripts
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

import pytest

from research_cli.categories import (
    suggest_category_from_topic,
    suggest_category_llm,
    ACADEMIC_CATEGORIES,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Keyword fallback: biology/medicine topics must NOT fall to CS
# ---------------------------------------------------------------------------

class TestKeywordFallback:
    """suggest_category_from_topic should classify bio/med topics correctly."""

    def test_crispr_classified_as_biology(self):
        result = suggest_category_from_topic("CRISPR gene editing")
        assert result["major"] == "natural_sciences"
        assert result["subfield"] == "biology"

    def test_gene_therapy_classified_as_biology(self):
        result = suggest_category_from_topic("gene therapy for sickle cell")
        assert result["major"] == "natural_sciences"
        assert result["subfield"] == "biology"

    def test_genome_classified_as_biology(self):
        result = suggest_category_from_topic("whole genome sequencing")
        assert result["major"] == "natural_sciences"
        assert result["subfield"] == "biology"

    def test_stem_cell_classified_as_biology(self):
        result = suggest_category_from_topic("stem cell differentiation")
        assert result["major"] == "natural_sciences"
        assert result["subfield"] == "biology"

    def test_cancer_treatment_classified_as_medicine(self):
        result = suggest_category_from_topic("cancer treatment immunotherapy")
        assert result["major"] == "medicine_health"
        assert result["subfield"] == "clinical"

    def test_immune_therapy_classified_as_medicine(self):
        result = suggest_category_from_topic("immune checkpoint inhibitors")
        assert result["major"] == "medicine_health"
        assert result["subfield"] == "clinical"

    def test_enzyme_classified_as_biology(self):
        result = suggest_category_from_topic("enzyme engineering")
        assert result["major"] == "natural_sciences"
        assert result["subfield"] == "biology"

    def test_virus_classified_as_biology(self):
        result = suggest_category_from_topic("virus mutation patterns")
        assert result["major"] == "natural_sciences"
        assert result["subfield"] == "biology"

    def test_unknown_topic_returns_none_major(self):
        """Completely unknown topic should return major=None, not CS."""
        # Use a string that doesn't substring-match any keyword
        # (e.g. "ux" matches inside "quux", so avoid that)
        result = suggest_category_from_topic("zzznonsensewordzzz")
        assert result["major"] is None
        assert result["subfield"] is None

    def test_existing_cs_topics_still_work(self):
        """Existing CS keyword matching should not break."""
        result = suggest_category_from_topic("deep learning for NLP")
        assert result["major"] == "computer_science"
        assert result["subfield"] == "ai_ml"

    def test_existing_physics_still_works(self):
        result = suggest_category_from_topic("quantum entanglement")
        assert result["major"] == "natural_sciences"
        assert result["subfield"] == "physics"

    def test_blockchain_still_cs_security(self):
        result = suggest_category_from_topic("blockchain consensus mechanisms")
        assert result["major"] == "computer_science"
        assert result["subfield"] == "security"


# ---------------------------------------------------------------------------
# LLM classifier: graceful fallback when LLM fails
# ---------------------------------------------------------------------------

class TestSuggestCategoryLlm:
    def test_llm_success_returns_llm_result(self):
        """When LLM returns valid category, use it."""
        @dataclass
        class FakeResponse:
            content: str = "natural_sciences/biology"
            total_tokens: int = 10
            input_tokens: int = 5
            output_tokens: int = 5

        fake_llm = MagicMock()
        fake_llm.generate = AsyncMock(return_value=FakeResponse())

        with patch("research_cli.model_config.create_llm_for_role", return_value=fake_llm):
            result = _run(suggest_category_llm("CRISPR gene editing"))

        assert result["major"] == "natural_sciences"
        assert result["subfield"] == "biology"

    def test_llm_failure_falls_back_to_keywords(self):
        """When LLM raises exception, fall back to keyword matching."""
        with patch("research_cli.model_config.create_llm_for_role", side_effect=Exception("no API key")):
            result = _run(suggest_category_llm("deep learning for NLP"))

        # Keywords should match AI/ML
        assert result["major"] == "computer_science"
        assert result["subfield"] == "ai_ml"

    def test_llm_failure_with_bio_topic_uses_keyword_bio(self):
        """When LLM fails on a bio topic, keyword fallback should catch it."""
        with patch("research_cli.model_config.create_llm_for_role", side_effect=Exception("timeout")):
            result = _run(suggest_category_llm("CRISPR gene editing"))

        assert result["major"] == "natural_sciences"
        assert result["subfield"] == "biology"

    def test_llm_failure_unknown_topic_not_cs(self):
        """When both LLM and keywords fail, should NOT return CS/theory."""
        with patch("research_cli.model_config.create_llm_for_role", side_effect=Exception("no key")):
            result = _run(suggest_category_llm("zzznonsensewordzzz"))

        # Should fall back to natural_sciences/biology (safe default), not CS/theory
        assert result["major"] != "computer_science"
        assert result["major"] is not None

    def test_llm_returns_garbage_falls_back(self):
        """When LLM returns unparseable text, fall back to keywords."""
        @dataclass
        class FakeResponse:
            content: str = "I think this is about something or other"
            total_tokens: int = 10
            input_tokens: int = 5
            output_tokens: int = 5

        fake_llm = MagicMock()
        fake_llm.generate = AsyncMock(return_value=FakeResponse())

        with patch("research_cli.model_config.create_llm_for_role", return_value=fake_llm):
            result = _run(suggest_category_llm("CRISPR gene editing"))

        # Should fall back to keyword matching → biology
        assert result["major"] == "natural_sciences"
        assert result["subfield"] == "biology"


# ---------------------------------------------------------------------------
# Desk editor: category parameter
# ---------------------------------------------------------------------------

class TestDeskEditorCategory:
    def test_screen_accepts_category_parameter(self):
        """DeskEditorAgent.screen() should accept optional category param."""
        from research_cli.agents.desk_editor import DeskEditorAgent

        # Verify the method signature accepts category
        import inspect
        sig = inspect.signature(DeskEditorAgent.screen)
        params = list(sig.parameters.keys())
        assert "category" in params

    def test_screen_category_included_in_prompt(self):
        """When category is provided, it should appear in the prompt sent to LLM."""
        from research_cli.agents.desk_editor import DeskEditorAgent

        @dataclass
        class FakeResponse:
            content: str = '{"decision": "PASS", "reason": "looks good"}'
            total_tokens: int = 10
            input_tokens: int = 5
            output_tokens: int = 5

        fake_llm = MagicMock()
        fake_llm.generate = AsyncMock(return_value=FakeResponse())
        fake_llm.model = "test-model"

        with patch("research_cli.agents.desk_editor.create_llm_for_role", return_value=fake_llm):
            agent = DeskEditorAgent()
            result = _run(agent.screen(
                "Some manuscript about CRISPR...",
                "CRISPR gene editing",
                category="Computer Science (Theory & Algorithms)"
            ))

        # Check that generate was called with a prompt containing the category
        call_kwargs = fake_llm.generate.call_args
        prompt_sent = call_kwargs.kwargs.get("prompt", "")

        assert "Computer Science (Theory & Algorithms)" in prompt_sent
        assert "academic field" in prompt_sent

    def test_screen_without_category_still_works(self):
        """screen() without category should work as before (backward compatible)."""
        from research_cli.agents.desk_editor import DeskEditorAgent

        @dataclass
        class FakeResponse:
            content: str = '{"decision": "PASS", "reason": "ok"}'
            total_tokens: int = 10
            input_tokens: int = 5
            output_tokens: int = 5

        fake_llm = MagicMock()
        fake_llm.generate = AsyncMock(return_value=FakeResponse())
        fake_llm.model = "test-model"

        with patch("research_cli.agents.desk_editor.create_llm_for_role", return_value=fake_llm):
            agent = DeskEditorAgent()
            result = _run(agent.screen("Some manuscript...", "some topic"))

        assert result["decision"] == "PASS"

    def test_screen_without_category_no_field_check(self):
        """Without category, prompt should NOT contain field mismatch check."""
        from research_cli.agents.desk_editor import DeskEditorAgent

        @dataclass
        class FakeResponse:
            content: str = '{"decision": "PASS", "reason": "ok"}'
            total_tokens: int = 10
            input_tokens: int = 5
            output_tokens: int = 5

        fake_llm = MagicMock()
        fake_llm.generate = AsyncMock(return_value=FakeResponse())
        fake_llm.model = "test-model"

        with patch("research_cli.agents.desk_editor.create_llm_for_role", return_value=fake_llm):
            agent = DeskEditorAgent()
            _run(agent.screen("Some manuscript...", "some topic"))

        prompt_sent = fake_llm.generate.call_args.kwargs.get("prompt", "")
        assert "academic field" not in prompt_sent
        assert "Assigned academic field" not in prompt_sent


# ---------------------------------------------------------------------------
# Integration: CLI import paths
# ---------------------------------------------------------------------------

class TestCliImportPaths:
    def test_cli_uses_llm_classifier_not_keyword(self):
        """Verify cli.py imports suggest_category_llm, not suggest_category_from_topic."""
        import importlib
        import inspect

        source = inspect.getsource(importlib.import_module("research_cli.cli"))

        # The collaborative run function should use suggest_category_llm
        assert "suggest_category_llm" in source
        # The actual category assignment should use the LLM version
        assert "await suggest_category_llm(topic)" in source


# ---------------------------------------------------------------------------
# LLM classifier: 20 diverse topics via mock LLM responses
# ---------------------------------------------------------------------------

# Each entry: (topic, expected LLM response, expected_major, expected_subfield)
_LLM_CLASSIFICATION_CASES = [
    ("CRISPR gene editing", "natural_sciences/biology", "natural_sciences", "biology"),
    ("Quantum computing error correction", "computer_science/theory", "computer_science", "theory"),
    ("Remote work productivity", "business_economics/management", "business_economics", "management"),
    ("Shakespeare literary criticism", "humanities/literature", "humanities", "literature"),
    ("Blockchain consensus mechanisms", "computer_science/systems", "computer_science", "systems"),
    ("Cancer immunotherapy", "medicine_health/clinical", "medicine_health", "clinical"),
    ("Climate change mitigation", "natural_sciences/earth_science", "natural_sciences", "earth_science"),
    ("Supply chain optimization", "business_economics/management", "business_economics", "management"),
    ("Constitutional law reform", "law_policy/law", "law_policy", "law"),
    ("Microbiome gut-brain axis", "natural_sciences/biology", "natural_sciences", "biology"),
    ("Transformer architecture in NLP", "computer_science/ai_ml", "computer_science", "ai_ml"),
    ("Stoic philosophy and modern ethics", "humanities/philosophy", "humanities", "philosophy"),
    ("Renewable energy grid integration", "engineering/electrical", "engineering", "electrical"),
    ("Behavioral economics nudge theory", "social_sciences/economics", "social_sciences", "economics"),
    ("CRISPR-Cas9 off-target effects", "natural_sciences/biology", "natural_sciences", "biology"),
    ("Antibiotic resistance mechanisms", "medicine_health/pharmacology", "medicine_health", "pharmacology"),
    ("Dark matter detection methods", "natural_sciences/physics", "natural_sciences", "physics"),
    ("Urban sociology gentrification", "social_sciences/sociology", "social_sciences", "sociology"),
    ("Lipid nanoparticle drug delivery", "medicine_health/pharmacology", "medicine_health", "pharmacology"),
    ("Archaeological excavation methods", "social_sciences/anthropology", "social_sciences", "anthropology"),
]


class TestLlmClassifierDiverseTopics:
    """Test that suggest_category_llm routes 20 diverse topics correctly (mock LLM)."""

    @pytest.mark.parametrize(
        "topic,llm_response,expected_major,expected_subfield",
        _LLM_CLASSIFICATION_CASES,
        ids=[c[0].replace(" ", "_")[:40] for c in _LLM_CLASSIFICATION_CASES],
    )
    def test_llm_classifies_topic(self, topic, llm_response, expected_major, expected_subfield):
        @dataclass
        class FakeResponse:
            content: str = llm_response
            total_tokens: int = 10
            input_tokens: int = 5
            output_tokens: int = 5

        fake_llm = MagicMock()
        fake_llm.generate = AsyncMock(return_value=FakeResponse())

        with patch("research_cli.model_config.create_llm_for_role", return_value=fake_llm):
            result = _run(suggest_category_llm(topic))

        assert result["major"] == expected_major, f"{topic}: expected major={expected_major}, got {result['major']}"
        assert result["subfield"] == expected_subfield, f"{topic}: expected subfield={expected_subfield}, got {result['subfield']}"

    def test_all_9_major_fields_covered(self):
        """Ensure test cases cover all 9 major academic fields."""
        covered_majors = {c[2] for c in _LLM_CLASSIFICATION_CASES}
        expected_majors = set(ACADEMIC_CATEGORIES.keys())
        assert covered_majors == expected_majors, f"Missing fields: {expected_majors - covered_majors}"


# ---------------------------------------------------------------------------
# Desk editor: field mismatch detection with mock manuscripts
# ---------------------------------------------------------------------------

# Realistic mock manuscripts (first ~500 chars is enough — desk editor reads first 3000)
_BIOLOGY_MANUSCRIPT = """# CRISPR Gene Editing: Mechanisms and Applications

## Introduction

The CRISPR-Cas9 system has revolutionized molecular biology by providing a
programmable tool for precise genome modification. Originally discovered as a
bacterial adaptive immune system, CRISPR (Clustered Regularly Interspaced Short
Palindromic Repeats) has been repurposed for targeted gene editing in eukaryotic
cells. The Cas9 endonuclease, guided by a single guide RNA (sgRNA), introduces
double-strand breaks at specific genomic loci, enabling gene knockout, insertion,
or correction through cellular DNA repair pathways such as NHEJ and HDR.

## Mechanism of Action

The CRISPR-Cas9 complex recognizes a 20-nucleotide target sequence adjacent to a
protospacer adjacent motif (PAM). Upon binding, the Cas9 protein undergoes
conformational changes that activate its two nuclease domains (RuvC and HNH),
cleaving both strands of the DNA double helix.

## Applications in Therapeutics

Recent clinical trials have demonstrated the potential of CRISPR-based therapies
for sickle cell disease, beta-thalassemia, and certain cancers.

## Conclusion

CRISPR gene editing represents a paradigm shift in biological research and medicine.
"""

_CS_MANUSCRIPT = """# Transformer Architectures for Large Language Models

## Introduction

The transformer architecture, introduced by Vaswani et al. (2017), has become
the dominant paradigm in natural language processing. Self-attention mechanisms
enable parallel computation across sequence positions, addressing the sequential
bottleneck of recurrent neural networks. This paper surveys recent advances in
scaling transformer models to hundreds of billions of parameters.

## Architecture

The core transformer block consists of multi-head self-attention followed by
position-wise feed-forward networks. Layer normalization and residual connections
stabilize training at scale. Recent innovations include rotary position embeddings
(RoPE), grouped query attention (GQA), and mixture-of-experts (MoE) layers.

## Conclusion

Transformer scaling continues to yield improvements in language understanding.
"""

_HISTORY_MANUSCRIPT = """# The Fall of the Roman Republic: Economic and Political Factors

## Introduction

The transition from the Roman Republic to the Roman Empire represents one of the
most studied periods in ancient history. This paper examines the interplay between
economic inequality, military reforms, and political dysfunction that led to the
collapse of republican governance in the first century BCE.

## Economic Factors

The influx of wealth from conquered territories created severe economic
stratification. Large slave-operated latifundia displaced small farmers, driving
rural populations into urban centers and creating a volatile proletariat.

## Conclusion

The fall of the Republic was not a single event but a gradual erosion of
institutional norms driven by structural economic and political pressures.
"""


class TestDeskEditorFieldMismatch:
    """Test desk editor prompt construction with matching/mismatching categories."""

    def _make_desk_agent(self, llm_decision: str = "PASS", llm_reason: str = "ok"):
        """Create a DeskEditorAgent with a mocked LLM that returns the given decision."""
        from research_cli.agents.desk_editor import DeskEditorAgent

        @dataclass
        class FakeResponse:
            content: str = f'{{"decision": "{llm_decision}", "reason": "{llm_reason}"}}'
            total_tokens: int = 50
            input_tokens: int = 40
            output_tokens: int = 10

        fake_llm = MagicMock()
        fake_llm.generate = AsyncMock(return_value=FakeResponse())
        fake_llm.model = "test-model"

        patcher = patch("research_cli.agents.desk_editor.create_llm_for_role", return_value=fake_llm)
        patcher.start()
        agent = DeskEditorAgent()
        return agent, fake_llm, patcher

    def _get_prompt(self, fake_llm) -> str:
        return fake_llm.generate.call_args.kwargs.get("prompt", "")

    # --- Matching cases: correct category, should pass ---

    def test_biology_manuscript_with_biology_category_passes(self):
        agent, fake_llm, patcher = self._make_desk_agent("PASS", "Content matches field")
        try:
            result = _run(agent.screen(
                _BIOLOGY_MANUSCRIPT, "CRISPR gene editing",
                category="Natural Sciences (Biology & Life Sciences)"
            ))
            prompt = self._get_prompt(fake_llm)
            assert "Natural Sciences (Biology & Life Sciences)" in prompt
            assert result["decision"] == "PASS"
        finally:
            patcher.stop()

    def test_cs_manuscript_with_cs_category_passes(self):
        agent, fake_llm, patcher = self._make_desk_agent("PASS", "Content matches field")
        try:
            result = _run(agent.screen(
                _CS_MANUSCRIPT, "Transformer architecture in NLP",
                category="Computer Science (Artificial Intelligence & Machine Learning)"
            ))
            prompt = self._get_prompt(fake_llm)
            assert "Computer Science" in prompt
            assert result["decision"] == "PASS"
        finally:
            patcher.stop()

    def test_history_manuscript_with_history_category_passes(self):
        agent, fake_llm, patcher = self._make_desk_agent("PASS", "Content matches field")
        try:
            result = _run(agent.screen(
                _HISTORY_MANUSCRIPT, "Fall of the Roman Republic",
                category="Humanities (History)"
            ))
            prompt = self._get_prompt(fake_llm)
            assert "Humanities (History)" in prompt
            assert result["decision"] == "PASS"
        finally:
            patcher.stop()

    # --- Mismatch cases: wrong category, desk editor should detect ---

    def test_biology_manuscript_assigned_cs_triggers_field_check(self):
        """Biology manuscript assigned to CS — prompt must contain field mismatch check."""
        agent, fake_llm, patcher = self._make_desk_agent(
            "DESK_REJECT", "Biology paper assigned to Computer Science"
        )
        try:
            result = _run(agent.screen(
                _BIOLOGY_MANUSCRIPT, "CRISPR gene editing",
                category="Computer Science (Theory & Algorithms)"
            ))
            prompt = self._get_prompt(fake_llm)
            # Prompt must contain: the assigned category, the field mismatch check criterion
            assert "Computer Science (Theory & Algorithms)" in prompt
            assert "completely different academic field" in prompt
            assert result["decision"] == "DESK_REJECT"
        finally:
            patcher.stop()

    def test_cs_manuscript_assigned_medicine_triggers_field_check(self):
        """CS manuscript assigned to Medicine — prompt must contain field mismatch check."""
        agent, fake_llm, patcher = self._make_desk_agent(
            "DESK_REJECT", "CS paper assigned to Medicine"
        )
        try:
            result = _run(agent.screen(
                _CS_MANUSCRIPT, "Transformer architecture",
                category="Medicine & Health Sciences (Clinical Medicine)"
            ))
            prompt = self._get_prompt(fake_llm)
            assert "Medicine & Health Sciences" in prompt
            assert "completely different academic field" in prompt
            assert result["decision"] == "DESK_REJECT"
        finally:
            patcher.stop()

    def test_history_manuscript_assigned_engineering_triggers_field_check(self):
        """History manuscript assigned to Engineering — mismatch check present."""
        agent, fake_llm, patcher = self._make_desk_agent(
            "DESK_REJECT", "History paper assigned to Engineering"
        )
        try:
            result = _run(agent.screen(
                _HISTORY_MANUSCRIPT, "Roman Republic",
                category="Engineering & Technology (Electrical & Electronics Engineering)"
            ))
            prompt = self._get_prompt(fake_llm)
            assert "Engineering & Technology" in prompt
            assert "completely different academic field" in prompt
        finally:
            patcher.stop()

    # --- No category: backward compatibility ---

    def test_no_category_omits_field_check(self):
        """Without category, field mismatch criterion #5 should not be in prompt."""
        agent, fake_llm, patcher = self._make_desk_agent("PASS", "ok")
        try:
            _run(agent.screen(_BIOLOGY_MANUSCRIPT, "CRISPR gene editing"))
            prompt = self._get_prompt(fake_llm)
            assert "Assigned academic field" not in prompt
            assert "completely different academic field" not in prompt
        finally:
            patcher.stop()

    # --- Prompt structure verification ---

    def test_mismatch_prompt_has_5_criteria(self):
        """With category, prompt should have 5 desk-reject criteria (not 4)."""
        agent, fake_llm, patcher = self._make_desk_agent("PASS", "ok")
        try:
            _run(agent.screen(
                _BIOLOGY_MANUSCRIPT, "CRISPR",
                category="Computer Science (Theory & Algorithms)"
            ))
            prompt = self._get_prompt(fake_llm)
            # Criteria 1-4 always present, #5 only with category
            assert "1." in prompt
            assert "4." in prompt
            assert "5." in prompt
        finally:
            patcher.stop()

    def test_no_category_prompt_has_4_criteria(self):
        """Without category, prompt should have only 4 desk-reject criteria."""
        agent, fake_llm, patcher = self._make_desk_agent("PASS", "ok")
        try:
            _run(agent.screen(_BIOLOGY_MANUSCRIPT, "CRISPR"))
            prompt = self._get_prompt(fake_llm)
            assert "1." in prompt
            assert "4." in prompt
            assert "5." not in prompt
        finally:
            patcher.stop()
