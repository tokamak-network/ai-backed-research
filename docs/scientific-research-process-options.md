# Scientific Research Process Options

## 현재 접근 방식의 한계

**Current: Section-by-Section Writing**
```
Topic → Plan → Write Intro → Write Background → ... → Integrate → Review
```

**문제점:**
- 실제 연구 과정 없이 바로 글쓰기
- 데이터/증거 수집 단계 없음
- 분석 없이 기존 지식만 종합
- "Research" 아니라 "Survey" 수준

---

## Option 1: Literature Review First (Survey 기반)

### Process
```
1. Topic Analysis
   ↓
2. Literature Search & Collection
   - Query academic databases
   - Fetch relevant papers/docs
   - Extract key findings
   ↓
3. Literature Synthesis
   - Identify themes
   - Find gaps
   - Map landscape
   ↓
4. Research Questions Formulation
   - Based on gaps found
   - Based on contradictions
   ↓
5. Structured Writing (with evidence)
```

### Implementation
```python
class LiteratureReviewAgent:
    async def search_literature(topic: str) -> List[Paper]:
        """
        Search for relevant papers:
        - arXiv (cryptography, CS)
        - Ethereum Research Forum
        - GitHub repos
        - Protocol documentation
        """

    async def extract_key_findings(papers: List[Paper]) -> KnowledgeBase:
        """Extract and structure findings."""

    async def synthesize_literature(kb: KnowledgeBase) -> LiteratureSurvey:
        """Create literature map with gaps."""
```

### 장점
- 실제 논문들을 인용
- 증거 기반 주장
- Gap analysis 가능

### 단점
- 새로운 분석은 여전히 없음
- Survey paper 수준

---

## Option 2: Data Collection & Analysis (실증 연구)

### Process
```
1. Research Question
   ↓
2. Data Collection Strategy
   - What data do we need?
   - Where to get it?
   ↓
3. Data Collection
   - On-chain data (Dune, Etherscan)
   - Protocol parameters
   - Historical metrics
   ↓
4. Data Analysis
   - Statistical analysis
   - Trend identification
   - Comparative analysis
   ↓
5. Results Interpretation
   ↓
6. Writing with Evidence
```

### Implementation
```python
class DataCollectionAgent:
    async def design_data_collection(question: str) -> DataStrategy:
        """Design what data to collect."""

    async def collect_onchain_data(strategy: DataStrategy) -> Dataset:
        """
        Collect from:
        - Dune Analytics
        - Etherscan API
        - Subgraphs
        - L2Beat API
        """

    async def analyze_data(dataset: Dataset) -> Analysis:
        """
        Perform:
        - Descriptive statistics
        - Trend analysis
        - Comparative analysis
        - Visualization
        """
```

### 장점
- 실제 데이터 기반
- 정량적 결과
- Original contribution

### 단점
- 데이터 접근 제한
- 분석 복잡도
- 시간 소요

---

## Option 3: Protocol Analysis & Simulation (메커니즘 연구)

### Process
```
1. Protocol Selection
   ↓
2. Code Review & Specification Analysis
   - Read protocol docs
   - Analyze smart contracts
   - Identify mechanisms
   ↓
3. Mechanism Modeling
   - Game-theoretic model
   - Economic model
   - Security model
   ↓
4. Simulation
   - Test under different conditions
   - Identify edge cases
   - Measure properties
   ↓
5. Results & Implications
   ↓
6. Writing with Models
```

### Implementation
```python
class ProtocolAnalysisAgent:
    async def analyze_protocol(protocol: str) -> ProtocolModel:
        """
        - Fetch documentation
        - Read smart contracts
        - Extract mechanisms
        """

    async def model_mechanism(protocol: ProtocolModel) -> GameTheoryModel:
        """
        Create formal model:
        - Agents
        - Actions
        - Payoffs
        - Equilibria
        """

    async def simulate(model: GameTheoryModel) -> SimulationResults:
        """
        Run scenarios:
        - Normal conditions
        - Attack scenarios
        - Stress tests
        """
```

### 장점
- Formal analysis
- Attack vector 발견
- Design 개선 제안

### 단점
- 복잡한 모델링 필요
- 시뮬레이션 infrastructure

---

## Option 4: Comparative Study (비교 연구)

### Process
```
1. Select Protocols/Solutions to Compare
   ↓
2. Define Comparison Criteria
   - Security properties
   - Performance metrics
   - Economic costs
   ↓
3. Collect Data for Each
   - Documentation
   - Metrics
   - Case studies
   ↓
4. Systematic Comparison
   - Feature matrix
   - Quantitative comparison
   - Trade-off analysis
   ↓
5. Synthesis & Recommendations
```

### Implementation
```python
class ComparativeStudyAgent:
    async def design_comparison(topic: str) -> ComparisonFramework:
        """
        Define:
        - What to compare (protocols)
        - How to compare (criteria)
        - Metrics to collect
        """

    async def collect_for_protocol(protocol: str, criteria: List) -> ProtocolData:
        """Collect all required data for one protocol."""

    async def compare(data: List[ProtocolData]) -> ComparisonTable:
        """
        Generate:
        - Feature comparison matrix
        - Performance comparison
        - Trade-off analysis
        """
```

### 장점
- 실용적 가치
- 명확한 구조
- Decision making 도움

### 단점
- Fair comparison 어려움
- Apples-to-apples 비교 제한

---

## Option 5: Case Study (실제 사례 연구)

### Process
```
1. Select Case (Protocol/Event)
   ↓
2. Historical Context
   - Timeline
   - Background
   ↓
3. Deep Dive Analysis
   - What happened?
   - Why did it happen?
   - Technical details
   - Economic factors
   ↓
4. Lessons Learned
   - What went wrong/right?
   - Design implications
   ↓
5. Generalization
   - Broader principles
   - Recommendations
```

### Implementation
```python
class CaseStudyAgent:
    async def select_case(topic: str) -> Case:
        """
        Examples:
        - Arbitrum One launch
        - Optimism Bedrock upgrade
        - zkSync Era hack (if any)
        - Base onboarding
        """

    async def collect_case_data(case: Case) -> CaseData:
        """
        Gather:
        - Timeline of events
        - Technical changes
        - Metrics before/after
        - Community response
        """

    async def analyze_case(data: CaseData) -> CaseAnalysis:
        """
        Analyze:
        - Root causes
        - Impact
        - Counterfactuals
        """
```

### 장점
- 구체적
- 교육적 가치
- Real-world 검증

### 단점
- Generalization 제한
- 데이터 가용성

---

## Option 6: Iterative Drafting (과학자 실제 프로세스)

### Process (가장 realistic)
```
1. Research Question
   ↓
2. Background Reading (minimal)
   ↓
3. Quick Draft 1 (brain dump)
   - Write what you know
   - Identify what you don't know
   ↓
4. Gap Identification
   - What evidence is missing?
   - What data do we need?
   - What analysis is needed?
   ↓
5. Fill Gaps (iteratively)
   - Collect missing data
   - Run needed analysis
   - Read specific papers
   ↓
6. Draft 2 (with evidence)
   ↓
7. Peer Feedback
   ↓
8. Draft 3 (refinement)
   ↓
9. Repeat until satisfied
```

### Implementation
```python
class IterativeDraftingOrchestrator:
    async def initial_draft(topic: str) -> Draft:
        """Write based on existing knowledge."""

    async def identify_gaps(draft: Draft) -> List[Gap]:
        """
        AI identifies:
        - Unsupported claims
        - Missing data
        - Weak arguments
        """

    async def fill_gap(gap: Gap) -> Evidence:
        """
        Based on gap type:
        - Data gap → collect data
        - Literature gap → search papers
        - Analysis gap → run analysis
        """

    async def revise_with_evidence(draft: Draft, evidence: List[Evidence]) -> Draft:
        """Integrate new evidence into draft."""
```

### 장점
- 가장 자연스러운 프로세스
- 효율적 (필요한 것만 찾음)
- Iterative improvement

### 단점
- 여러 iteration 필요
- Gap filling 자동화 어려움

---

## Option 7: Hypothesis Testing (실험 과학)

### Process
```
1. Formulate Hypothesis
   - "Optimistic rollups are cheaper than ZK rollups for simple transfers"
   ↓
2. Design Test
   - Metrics to measure
   - Conditions to test
   ↓
3. Collect Data
   - Run experiments
   - Gather measurements
   ↓
4. Statistical Analysis
   - Test hypothesis
   - Calculate significance
   ↓
5. Interpret Results
   - Accept/reject hypothesis
   - Explain why
   ↓
6. Write Paper
```

### Implementation
```python
class HypothesisTestingAgent:
    async def formulate_hypothesis(topic: str) -> Hypothesis:
        """
        Generate testable hypothesis:
        - Independent variable
        - Dependent variable
        - Expected relationship
        """

    async def design_experiment(hypothesis: Hypothesis) -> ExperimentDesign:
        """
        Design:
        - What to measure
        - How to measure
        - Control variables
        """

    async def run_experiment(design: ExperimentDesign) -> Results:
        """
        Execute:
        - Collect data
        - Run tests
        - Statistical analysis
        """

    async def interpret_results(results: Results) -> Interpretation:
        """
        - Hypothesis supported?
        - Effect size
        - Confidence level
        """
```

### 장점
- Scientific rigor
- Clear methodology
- Falsifiable

### 단점
- Blockchain data 제약
- Causality 입증 어려움

---

## Option 8: Multi-Agent Research Team (실제 연구팀 모방)

### Process
```
Research Lead
   ↓
분업:
├─ Theorist (formal modeling)
├─ Data Scientist (empirical analysis)
├─ Engineer (protocol analysis)
└─ Economist (mechanism design)

각자 독립 작업 → 통합 → 논의 → 반복
```

### Implementation
```python
class ResearchTeam:
    theorist: TheoreticalAnalysisAgent
    data_scientist: DataAnalysisAgent
    engineer: ProtocolAnalysisAgent
    economist: EconomicAnalysisAgent

    async def collaborative_research(topic: str) -> Paper:
        """
        1. Research lead assigns tasks
        2. Agents work in parallel
        3. Share findings
        4. Identify conflicts/gaps
        5. Iterate
        6. Integrate into paper
        """
```

### 장점
- 다각도 분석
- Specialization
- 실제 연구팀과 유사

### 단점
- Coordination 복잡
- Conflict resolution 필요

---

## Option 9: Claim-Evidence Framework (구조화된 접근)

### Process
```
1. Identify Key Claims
   - "Fraud proofs provide security equivalent to L1"
   - "7-day challenge window is sufficient"
   ↓
2. For Each Claim:
   a. What evidence supports it?
   b. Collect that evidence
   c. Evaluate strength
   ↓
3. Write Section with Claim-Evidence pairs
   ↓
4. Link Evidence to Claims
```

### Implementation
```python
class ClaimEvidenceAgent:
    async def extract_claims(topic: str) -> List[Claim]:
        """Identify all claims that will be made."""

    async def find_evidence(claim: Claim) -> List[Evidence]:
        """
        For each claim, find:
        - Papers that support/refute
        - Data that validates
        - Examples that illustrate
        """

    async def evaluate_evidence(evidence: List[Evidence]) -> EvidenceStrength:
        """Rate evidence quality."""

    async def write_with_evidence(claims: List[Claim]) -> Section:
        """Write section with explicit claim-evidence links."""
```

### 장점
- 명확한 구조
- Evidence traceability
- Reviewer가 검증 쉬움

### 단점
- 기계적일 수 있음
- Flow 저해 가능

---

## Option 10: Tool-Augmented Research (도구 활용)

### Process
```
1. Research Question
   ↓
2. Identify Needed Tools
   - Code analyzer
   - Data fetcher
   - Calculator
   - Simulator
   ↓
3. Use Tools to Generate Evidence
   ↓
4. Write with Tool Outputs
```

### Tools Integration
```python
class ToolAugmentedWriter:
    tools = {
        "etherscan_api": EtherscanAPI(),
        "dune_analytics": DuneAPI(),
        "contract_analyzer": SlitherWrapper(),
        "economic_simulator": GameTheorySimulator(),
        "citation_finder": SemanticScholar()
    }

    async def write_section_with_tools(section: Section) -> SectionOutput:
        """
        While writing:
        1. Detect when data/analysis needed
        2. Call appropriate tool
        3. Integrate result
        4. Continue writing
        """
```

### Example
```
Writer: "Optimistic rollups cost X per transaction"
  → Tool: fetch_actual_tx_costs("arbitrum", "optimism")
  → Result: {arbitrum: $0.15, optimism: $0.12}
  → Writer: "Optimistic rollups cost $0.12-0.15 per transaction (as of Feb 2024)"
```

### 장점
- Real-time data
- Accurate numbers
- Reproducible

### 단점
- Tool availability
- API rate limits
- Integration complexity

---

## Recommended Hybrid Approach

### Tier 1: Essential (모든 논문)
```
1. Literature Review (Option 1)
   - 기본 context 확보
   - 기존 연구 파악

2. Claim-Evidence Framework (Option 9)
   - 주장 명확화
   - Evidence requirement 식별

3. Iterative Drafting (Option 6)
   - Draft → Gap → Fill → Revise
```

### Tier 2: Topic-Dependent
```
If 실증 연구 가능:
  → Data Collection (Option 2)

If 프로토콜 분석:
  → Protocol Analysis (Option 3)

If 비교 연구:
  → Comparative Study (Option 4)

If historical event:
  → Case Study (Option 5)
```

### Tier 3: Advanced (선택)
```
If hypothesis 있음:
  → Hypothesis Testing (Option 7)

If 복잡한 topic:
  → Multi-Agent Team (Option 8)

If tools 사용 가능:
  → Tool-Augmented (Option 10)
```

---

## Implementation Priority

### Phase 1: Foundation (즉시)
```
✅ Section-by-section writing (Done)
□ Claim-Evidence framework
□ Gap identification system
```

### Phase 2: Evidence Collection (Week 1-2)
```
□ Literature search agent
□ Web data collection
□ On-chain data fetcher (Dune/Etherscan)
```

### Phase 3: Analysis (Week 3-4)
```
□ Data analysis agent
□ Protocol analysis agent
□ Comparative framework
```

### Phase 4: Iteration (Week 5-6)
```
□ Iterative drafting orchestrator
□ Gap filling automation
□ Evidence integration
```

### Phase 5: Advanced (Week 7+)
```
□ Multi-agent research team
□ Tool augmentation
□ Hypothesis testing
```

---

## Example: EIP-4844 Paper with Hybrid Approach

### Step 1: Initial Draft (Section-by-section)
```
Write 5 sections based on existing knowledge
```

### Step 2: Gap Identification
```
AI reviews draft:
- "Claim: Blob transactions reduce costs by 10x"
  Gap: No actual data

- "Claim: 4096-epoch retention is sufficient"
  Gap: No analysis of why

- "Claim: EIP-4844 enables 100k TPS"
  Gap: No calculation shown
```

### Step 3: Evidence Collection
```
For each gap:
- Gap 1 → Fetch Dune data: L2 costs before/after EIP-4844
- Gap 2 → Analyze: What's actual data requirement for 7-day challenge?
- Gap 3 → Calculate: With 6 blobs/block, what's theoretical max TPS?
```

### Step 4: Revision with Evidence
```
Revise sections with:
- Dune chart showing cost reduction
- Calculation showing 4096 epochs = 18.2 days > 7 days
- TPS calculation: 6 blobs * 128KB * 12s block = 384KB/12s = 200-400 TPS
```

### Step 5: Peer Review
```
Existing system with reviewers
```

### Result
```
Before: "EIP-4844 reduces costs significantly"
After: "EIP-4844 reduced Arbitrum One median transaction costs from $0.40
       to $0.04 (90% reduction) according to Dune Analytics data from
       March 13-April 13, 2024 [cite Dune dashboard]"
```

---

## 어떤 옵션 조합으로 진행할까?

**추천 조합 (realistic + impactful):**
1. **Iterative Drafting** (Option 6) - core framework
2. **Claim-Evidence** (Option 9) - structure
3. **Data Collection** (Option 2) - empirical grounding
4. **Tool-Augmented** (Option 10) - real-time data

**이유:**
- Iterative: 자연스러운 research flow
- Claim-Evidence: 명확한 논증 구조
- Data Collection: 정량적 증거
- Tool-Augmented: 실제 데이터 활용

**구현 순서:**
1주차: Claim-Evidence framework
2주차: Data collection tools (Dune, Etherscan)
3주차: Gap identification + iterative drafting
4주차: Integration + testing
