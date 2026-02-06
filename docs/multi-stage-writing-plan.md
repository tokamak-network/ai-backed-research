# Multi-Stage Research Writing Plan

## Problem Statement

**Current Issue:**
- Writer generates entire manuscript in one call (max_tokens=16384)
- Single-shot writing lacks the iterative refinement of real research
- Quality suffers from attempting comprehensive coverage in one pass
- No opportunity for structural planning before writing
- Missing the natural research process: outline → drafts → integration

**Real Research Process:**
```
Researcher workflow:
1. Literature review & notes
2. Create detailed outline
3. Write introduction (context, motivation)
4. Write individual sections (one at a time)
5. Write technical details (proofs, algorithms)
6. Write evaluation/results
7. Write conclusion
8. Integrate all sections
9. Revise for coherence
10. Polish and finalize
```

---

## Proposed Multi-Stage Writing Architecture

### Stage 1: Research Planning (Pre-Writing)

**Agent: Research Planner**

```python
async def plan_research(topic: str) -> ResearchPlan:
    """
    Analyze topic and create research plan.

    Output:
    - Key research questions
    - Required sections
    - Dependencies between sections
    - Estimated depth per section
    - Reference domains needed
    """
```

**Example Output:**
```json
{
  "topic": "Ethereum EIP-4844 Blob Transactions",
  "research_questions": [
    "What problem does EIP-4844 solve?",
    "How does the blob pricing mechanism work?",
    "What are the security implications?",
    "How does this affect L2 economics?"
  ],
  "sections": [
    {
      "id": "intro",
      "title": "Introduction and Motivation",
      "dependencies": [],
      "estimated_tokens": 2000,
      "key_points": ["Scalability crisis", "Data availability bottleneck"]
    },
    {
      "id": "background",
      "title": "Technical Background",
      "dependencies": ["intro"],
      "estimated_tokens": 3000,
      "key_points": ["Calldata vs blobs", "EIP-1559 pricing", "KZG commitments"]
    },
    {
      "id": "mechanism",
      "title": "Blob Transaction Mechanism",
      "dependencies": ["background"],
      "estimated_tokens": 4000,
      "key_points": ["Transaction format", "Blob lifecycle", "Verification"]
    }
  ]
}
```

### Stage 2: Section-by-Section Writing

**Agent: Section Writer (Enhanced WriterAgent)**

```python
async def write_section(
    section_spec: SectionSpec,
    research_plan: ResearchPlan,
    previous_sections: List[str],
    context: str
) -> str:
    """
    Write one section at a time with full context.

    Benefits:
    - Focused depth on specific topic
    - Reference to previous sections for coherence
    - Can use full token budget per section
    - Natural incremental building
    """
```

**Writing Order:**
1. Introduction (sets context)
2. Background (establishes foundations)
3. Core sections (one by one, referencing previous)
4. Analysis sections (builds on core)
5. Conclusion (synthesizes all)

**Per-Section Context:**
```python
prompt = f"""
You are writing Section {section_number}/{total_sections} of a research paper.

OVERALL RESEARCH PLAN:
{research_plan}

PREVIOUSLY WRITTEN SECTIONS:
{summaries_of_previous_sections}

CURRENT SECTION TO WRITE:
Title: {section.title}
Key Points: {section.key_points}
Estimated Length: {section.estimated_tokens} tokens

YOUR TASK:
Write this section in detail. You have the full token budget for just this section.
- Reference previous sections naturally (e.g., "As discussed in Section 2...")
- Maintain consistent terminology
- Ensure logical flow from previous content
- Provide deep technical detail appropriate for this section
- Include examples, data, and analysis

Write the complete section now in markdown format.
"""
```

### Stage 3: Section Integration

**Agent: Integration Editor**

```python
async def integrate_sections(
    sections: List[str],
    research_plan: ResearchPlan
) -> str:
    """
    Integrate individual sections into coherent manuscript.

    Tasks:
    - Smooth transitions between sections
    - Remove redundancy
    - Ensure consistent terminology
    - Add cross-references
    - Balance section lengths
    """
```

**Integration Process:**
```
1. Concatenate all sections
2. Analyze transitions
3. Add bridging paragraphs
4. Standardize terminology
5. Add "roadmap" sentences (e.g., "The remainder of this paper...")
6. Ensure logical flow
7. Final polish
```

### Stage 4: Iterative Refinement (Existing System)

After integration, use existing peer review workflow:
- Specialist reviews
- Moderator decision
- Author rebuttal
- **Section-level revision** (not entire manuscript)

---

## Implementation Design

### New Classes

**1. ResearchPlanner**
```python
class ResearchPlanner:
    """Plans research structure before writing."""

    async def analyze_topic(self, topic: str) -> TopicAnalysis:
        """Analyze topic complexity and scope."""

    async def create_outline(self, topic: str) -> ResearchPlan:
        """Generate detailed section outline."""

    async def estimate_requirements(self, plan: ResearchPlan) -> Requirements:
        """Estimate tokens, time, expert needs."""
```

**2. SectionWriter (Enhanced WriterAgent)**
```python
class SectionWriter(WriterAgent):
    """Writes individual sections with context."""

    async def write_section(
        self,
        section_spec: SectionSpec,
        context: WritingContext
    ) -> SectionOutput:
        """Write one section with full detail."""

    async def revise_section(
        self,
        section: str,
        feedback: List[Dict],
        context: WritingContext
    ) -> str:
        """Revise specific section based on feedback."""
```

**3. IntegrationEditor**
```python
class IntegrationEditor:
    """Integrates sections into coherent manuscript."""

    async def integrate(
        self,
        sections: List[SectionOutput],
        plan: ResearchPlan
    ) -> str:
        """Combine sections with transitions."""

    async def polish(self, manuscript: str) -> str:
        """Final polish and consistency check."""
```

**4. MultiStageOrchestrator**
```python
class MultiStageOrchestrator:
    """Orchestrates multi-stage writing process."""

    async def run_planning_phase(self) -> ResearchPlan:
        """Stage 1: Create research plan."""

    async def run_writing_phase(self, plan: ResearchPlan) -> List[str]:
        """Stage 2: Write sections sequentially."""

    async def run_integration_phase(self, sections: List[str]) -> str:
        """Stage 3: Integrate into manuscript."""

    async def run_review_phase(self, manuscript: str) -> ReviewResult:
        """Stage 4: Existing peer review workflow."""
```

---

## Data Models

```python
@dataclass
class SectionSpec:
    id: str
    title: str
    key_points: List[str]
    dependencies: List[str]  # Section IDs that must be written first
    estimated_tokens: int
    depth_level: str  # "overview", "detailed", "comprehensive"

@dataclass
class ResearchPlan:
    topic: str
    research_questions: List[str]
    sections: List[SectionSpec]
    total_estimated_tokens: int
    recommended_experts: List[str]

@dataclass
class SectionOutput:
    section_id: str
    content: str
    word_count: int
    tokens_used: int
    metadata: Dict

@dataclass
class WritingContext:
    research_plan: ResearchPlan
    previous_sections: List[SectionOutput]
    section_spec: SectionSpec

    def get_section_summary(self, section_id: str) -> str:
        """Get brief summary of previous section for context."""
```

---

## Workflow Comparison

### Current (Single-Shot):
```
Topic → [Writer: 16K tokens] → Manuscript → Review → Revise
                ↑
        Tries to cover everything at once
        Limited depth per topic
```

### Proposed (Multi-Stage):
```
Topic → Planner → ResearchPlan
              ↓
        Section 1 [Writer: 16K tokens for intro only]
              ↓
        Section 2 [Writer: 16K tokens for background only]
              ↓
        Section 3 [Writer: 16K tokens for mechanism only]
              ↓
        ...
              ↓
        Integrator → Full Manuscript
              ↓
        Review → Rebuttal → Revise SPECIFIC SECTIONS
```

---

## Token Economics

### Current System:
- Single manuscript: 16K tokens
- Typical output: 6,000-8,000 words
- Depth: Limited by trying to cover all topics

### Multi-Stage System:
- 5 sections × 16K tokens each = 80K total
- Per section: 3,000-4,000 words
- Total manuscript: 15,000-20,000 words
- Depth: Each section gets full attention

**Cost Comparison:**
```
Current:
- Writer: 1 call × 16K = 16K tokens
- Total: ~$0.50 (Opus)

Proposed:
- Planner: 1 call × 4K = 4K tokens
- Writer: 5 calls × 16K = 80K tokens
- Integrator: 1 call × 8K = 8K tokens
- Total: ~$3.00 (Opus)

6x cost for 2-3x longer, much deeper papers
```

---

## Revision Strategy

### Section-Level Revision

When reviewers identify issues, revise ONLY affected sections:

```python
# Reviewer: "Section 3 lacks depth on blob pricing"
# System: Revise only Section 3, keep others unchanged

async def revise_sections(
    reviews: List[Dict],
    sections: List[SectionOutput]
) -> List[str]:
    """
    Identify which sections need revision.
    Revise only those sections.
    Re-integrate.
    """

    # Analyze reviews to map feedback to sections
    section_feedback = map_feedback_to_sections(reviews)

    # Revise only affected sections
    revised_sections = []
    for section in sections:
        if section.id in section_feedback:
            revised = await writer.revise_section(
                section.content,
                section_feedback[section.id],
                context
            )
            revised_sections.append(revised)
        else:
            # Keep unchanged
            revised_sections.append(section.content)

    # Re-integrate
    return await integrator.integrate(revised_sections)
```

**Benefits:**
- Surgical revisions (not rewriting everything)
- Preserve good sections
- Focus token budget on problem areas
- Faster iteration

---

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1)
- [ ] Create ResearchPlanner agent
- [ ] Implement SectionSpec and ResearchPlan models
- [ ] Add section-level writing to WriterAgent
- [ ] Test: Generate plan + write 2 sections

### Phase 2: Integration (Week 2)
- [ ] Create IntegrationEditor agent
- [ ] Implement section concatenation + transitions
- [ ] Test: Full 5-section paper generation
- [ ] Compare quality vs. single-shot

### Phase 3: Revision System (Week 3)
- [ ] Implement section-level revision
- [ ] Map reviewer feedback to sections
- [ ] Test: Revise section 3, keep others
- [ ] Measure token efficiency

### Phase 4: Orchestration (Week 4)
- [ ] Create MultiStageOrchestrator
- [ ] Integrate with existing peer review
- [ ] Add progress tracking
- [ ] Web viewer updates (section-by-section view)

### Phase 5: Optimization (Week 5)
- [ ] Parallel section writing (independent sections)
- [ ] Section caching (don't re-generate unchanged)
- [ ] Cost optimization (use Sonnet for planning)
- [ ] Quality metrics

---

## Example: EIP-4844 Paper

### Stage 1: Planning
```
Topic: Ethereum EIP-4844 Blob Transactions

Research Plan:
1. Introduction (2K tokens)
   - Scalability problem
   - Data availability bottleneck
   - EIP-4844 overview

2. Technical Background (3K tokens)
   - Ethereum block structure
   - Calldata vs. blobs
   - KZG commitments primer

3. Blob Transaction Mechanism (4K tokens)
   - Transaction format
   - Blob sidecar
   - Verification process
   - Blob lifecycle (pruning)

4. Pricing and Economics (4K tokens)
   - Blob gas market
   - EIP-1559 adaptation
   - Target/max blobs
   - Fee dynamics

5. L2 Impact Analysis (3K tokens)
   - Cost reduction quantification
   - Rollup adoption
   - Future scaling roadmap

6. Security Considerations (2K tokens)
   - Attack vectors
   - Mitigation strategies

7. Conclusion (1K tokens)
   - Summary
   - Future work

Total: 19K words estimated
```

### Stage 2: Writing (7 passes)
```
Pass 1: Write Introduction (16K budget)
Pass 2: Write Background (16K budget, references Introduction)
Pass 3: Write Mechanism (16K budget, references Background)
Pass 4: Write Economics (16K budget, references Mechanism)
Pass 5: Write L2 Impact (16K budget, references all previous)
Pass 6: Write Security (16K budget)
Pass 7: Write Conclusion (16K budget, synthesizes all)
```

### Stage 3: Integration
```
Integrator:
- Add transitions: "Building on the mechanism described in Section 3..."
- Standardize terms: "blob sidecar" everywhere
- Add cross-refs: "As we will see in Section 5..."
- Polish intro/conclusion to reference all sections
```

### Stage 4: Review
```
Reviewer 1: "Section 4 needs more empirical fee data"
→ Revise ONLY Section 4, add data
→ Re-integrate

Reviewer 2: "Missing discussion of EIP-7594 (PeerDAS)"
→ Add subsection to Section 5
→ Re-integrate
```

---

## Quality Metrics

Track improvements with multi-stage approach:

```python
@dataclass
class QualityMetrics:
    # Depth
    avg_citations_per_section: float
    technical_detail_score: float  # 1-10

    # Coherence
    transition_quality: float  # 1-10
    terminology_consistency: float

    # Completeness
    research_questions_answered: int
    section_coverage: float  # % of plan executed

    # Review scores
    initial_review_avg: float
    final_review_avg: float

    # Efficiency
    revisions_per_section: Dict[str, int]
    token_efficiency: float  # quality / tokens_used
```

---

## Configuration

```yaml
# config/multi_stage.yaml

writing_strategy: multi_stage  # or 'single_shot'

planning:
  model: claude-sonnet-4  # Cheaper for planning
  max_sections: 10
  min_tokens_per_section: 1000
  max_tokens_per_section: 6000

section_writing:
  model: claude-opus-4.5  # Best quality for content
  max_tokens: 16384
  include_previous_sections: true
  max_context_sections: 3  # Only include last 3 sections

integration:
  model: claude-sonnet-4  # Sonnet sufficient for editing
  add_transitions: true
  standardize_terminology: true
  max_tokens: 8192

revision:
  granularity: section  # or 'full_manuscript'
  preserve_unchanged_sections: true
  reintegrate_after_revision: true
```

---

## Benefits Summary

### Quality Improvements
1. **Depth**: Each section gets full token budget
2. **Coherence**: Explicit planning + integration phase
3. **Revision efficiency**: Change only what needs changing
4. **Reviewer satisfaction**: More comprehensive coverage

### Cost Efficiency
1. **Targeted revisions**: Don't regenerate entire manuscript
2. **Section caching**: Reuse unchanged sections
3. **Model flexibility**: Sonnet for planning, Opus for writing
4. **Parallel writing**: Independent sections in parallel

### Process Improvements
1. **Transparency**: Clear section-by-section progress
2. **Debugging**: Identify weak sections easily
3. **Iteration**: Revise specific sections quickly
4. **Collaboration**: Multiple writers could work on different sections

---

## Risk Mitigation

### Risk: Sections don't integrate well
**Mitigation**:
- Strong planning phase
- Each section references previous ones
- Dedicated integration phase with editor agent

### Risk: Cost explosion
**Mitigation**:
- Use Sonnet for planning/integration
- Cache unchanged sections during revision
- Parallel writing only for independent sections
- Configuration limits on section count

### Risk: Slower iteration
**Mitigation**:
- Section-level revision (not full rewrite)
- Parallel section writing where possible
- Skip integration if only one section changed

### Risk: Loss of holistic view
**Mitigation**:
- Writer sees summaries of previous sections
- Integration phase ensures coherence
- Final review treats manuscript as whole

---

## Success Criteria

### Must Achieve:
- [ ] Paper length: 15,000+ words (vs. current 6,000)
- [ ] Initial review score: 7.5+ (vs. current 6.5)
- [ ] Revision efficiency: 50% token reduction per round
- [ ] Section depth: 3,000+ words per core section

### Nice to Have:
- [ ] Acceptance rate: 50%+ (vs. current 0%)
- [ ] Cost per accepted paper: <$10
- [ ] Time to completion: <2 hours
- [ ] Reviewer satisfaction: 8.0+ on completeness

---

## Next Steps

1. **Get Approval**: Review this plan with user
2. **Implement Phase 1**: ResearchPlanner + SectionWriter
3. **Test on EIP-4844**: Generate first multi-stage paper
4. **Compare Quality**: Side-by-side vs. single-shot
5. **Iterate**: Refine based on results
6. **Full Rollout**: Replace single-shot writing

---

## Open Questions

1. **Section count**: 5-7 sections optimal? Or dynamic based on topic?
2. **Integration frequency**: After each section, or batch at end?
3. **Parallel writing**: Which sections can be written in parallel?
4. **Context window**: How many previous sections to include?
5. **Revision granularity**: Always section-level, or full manuscript for major changes?
6. **Cost-quality tradeoff**: Is 6x cost worth 2-3x quality?

---

*This plan transforms the writing process from a single-shot attempt to a structured, iterative research workflow that mirrors how real researchers write papers. The result should be deeper, more coherent, and more comprehensive research reports that pass peer review.*
