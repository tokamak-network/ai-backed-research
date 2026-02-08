# AI Research CLI

An AI-native research workflow system that generates high-quality research reports through iterative multi-provider LLM peer review.

## Overview

This system implements a novel approach to AI-generated research:

1. **Initial Draft**: AI writer generates comprehensive research manuscript
2. **Specialist Review**: Multiple domain expert AI reviewers (cryptography, economics, distributed systems) provide detailed feedback
3. **Iterative Refinement**: Manuscript is revised based on feedback until quality threshold is met
4. **Multi-Provider**: Uses different LLM providers (Claude, Gemini, GPT) for diverse perspectives

## Architecture

### Hybrid System

- **Python CLI Tool**: Core workflow orchestration (this package)
- **Web Viewer**: Visualization of research results (in `/web` directory)
- **Static JSON Output**: Results saved as files, no backend required

### Key Components

```
research_cli/
├── llm/                 # Multi-provider LLM abstractions
│   ├── base.py         # Unified LLM interface
│   ├── claude.py       # Anthropic Claude
│   ├── gemini.py       # Google Gemini
│   └── openai.py       # OpenAI GPT
├── agents/             # AI agents (to be implemented)
│   ├── writer.py       # Initial draft writer
│   ├── reviewer.py     # Base reviewer
│   └── specialists/    # Domain experts
├── workflow/           # Review orchestration (to be implemented)
│   ├── scoring.py      # Quality scoring
│   └── orchestrator.py # Main workflow
└── cli.py              # Command-line interface
```

## Installation

### 1. Clone Repository

```bash
git clone <repository-url>
cd ai-backed-research
```

### 2. Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate environment
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install anthropic openai google-generativeai click pydantic python-dotenv rich aiohttp pyyaml
```

### 3. Configure API Keys

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```env
# Shared router key (LiteLLM/OpenRouter — covers all providers)
LLM_API_KEY=your_router_key_here
LLM_BASE_URL=https://your-endpoint/v1

# Or use provider-specific keys (override LLM_API_KEY)
# ANTHROPIC_API_KEY=your_claude_api_key_here
# OPENAI_API_KEY=your_openai_api_key_here
# GOOGLE_API_KEY=your_gemini_api_key_here
```

### 4. Verify Setup

```bash
# Check configuration
python -m research_cli.cli status --check-keys

# Test LLM providers
python -m research_cli.cli test --test-providers
```

## Usage

### Initialize Research Project

```bash
python -m research_cli.cli init "Layer 2 Fee Structures" --profile suhyeon
```

### List Projects

```bash
python -m research_cli.cli list
```

### Check Status

```bash
python -m research_cli.cli status
```

### Run Full Workflow (Coming in Phase 2-3)

```bash
# Full workflow with default settings
python -m research_cli.cli run "Layer 2 Fee Structures"

# Custom configuration
python -m research_cli.cli run "Layer 2 Fee Structures" \
  --writer-model claude-opus \
  --max-rounds 3 \
  --threshold 8.0
```

## Review Process

### Scoring System

Each specialist reviewer evaluates the manuscript on 5 criteria (1-10 scale):

- **Accuracy**: Factual correctness, no hallucinations
- **Completeness**: Covers all important aspects
- **Clarity**: Well-structured, understandable
- **Novelty**: Original insights beyond existing literature
- **Rigor**: Proper methodology, citations, evidence

### Termination Conditions

- ✅ **Success**: Average score ≥ 8.0/10 across all specialists
- 🔄 **Continue**: Score < 8.0, revision needed (max 3 rounds)
- ⏱️ **Max Rounds**: Stop after 3 review rounds

### Specialist Reviewers

1. **Cryptography Expert**
   - Focus: Security proofs, attack vectors, cryptographic assumptions
   - Provider: Claude Opus 4.5 (best at technical rigor)

2. **Economics Expert**
   - Focus: Incentive structures, game theory, tokenomics
   - Provider: Gemini 2.0 Pro (quantitative reasoning)

3. **Distributed Systems Expert**
   - Focus: Scalability, fault tolerance, performance
   - Provider: GPT-4 (broad systems knowledge)

## Output Structure

Each research project creates:

```
results/
└── [topic-name]/
    ├── metadata.json      # Project metadata
    ├── manuscript.md      # Current version
    ├── rounds/            # Review history
    │   ├── round_1.json   # First review round
    │   ├── round_2.json   # Second round
    │   └── ...
    └── final.md           # Approved final version
```

### Round JSON Schema

```json
{
  "round": 1,
  "manuscript_version": "v1.0",
  "reviews": [
    {
      "specialist": "cryptography",
      "provider": "claude-opus-4-5",
      "scores": {
        "accuracy": 7,
        "completeness": 8,
        "clarity": 9,
        "novelty": 6,
        "rigor": 7
      },
      "average": 7.4,
      "feedback": "Detailed comments...",
      "suggestions": ["Fix X", "Add Y", "Clarify Z"]
    }
  ],
  "overall_average": 7.6,
  "passed": false,
  "revision_prompt": "Combined feedback for revision..."
}
```

## Cost Estimation

Per research project (5000-word manuscript):

- Initial draft: ~$2 (Claude Opus, 20K tokens)
- Review round (3 specialists): ~$3 (15K tokens each)
- Revision: ~$2 (20K tokens)
- **Total per round**: ~$5
- **3 rounds max**: ~$17 per project

## Development Status

### ✅ Phase 1: Core Infrastructure (COMPLETED)

- [x] Python package structure
- [x] Multi-provider LLM system (Claude, Gemini, OpenAI)
- [x] Configuration management
- [x] CLI scaffolding with Rich UI
- [x] Basic commands (init, list, status, test)

### 🚧 Phase 2: Writer & Reviewers (NEXT)

- [ ] Writer agent implementation
- [ ] Base Reviewer class
- [ ] 3 specialist reviewers with system prompts
- [ ] Scoring logic

### 🔜 Phase 3: Workflow Orchestration

- [ ] Orchestrator implementation
- [ ] Score aggregation and pass/fail logic
- [ ] Revision prompt generation
- [ ] Round iteration with state saving

### 🔜 Phase 4: Web Viewer

- [ ] HTML viewer page
- [ ] JavaScript JSON loader
- [ ] Timeline visualization
- [ ] Score charts
- [ ] Manuscript diff viewer

### 🔜 Phase 5: Testing & Refinement

- [ ] End-to-end workflow tests
- [ ] Real research project generation
- [ ] Threshold tuning
- [ ] Documentation

## Testing

### Run Basic Tests

```bash
# Test configuration and LLM connectivity
python test_setup.py
```

### Manual CLI Tests

```bash
# Activate venv
source venv/bin/activate

# Test commands
python -m research_cli.cli --help
python -m research_cli.cli status --check-keys
python -m research_cli.cli init "Test Topic"
python -m research_cli.cli list
```

## Contributing

This is an experimental research tool. Contributions welcome for:

- Additional specialist reviewers
- Alternative LLM providers
- Improved scoring algorithms
- Web viewer enhancements

## License

[Your License Here]

## Future Enhancements

- Debate mode (reviewers discuss with each other)
- Human-in-the-loop approval
- Citation validation and fact-checking
- Plagiarism detection
- Integration with academic databases
- Automatic scheduling
- Email notifications

---

**Built with:**
- [Anthropic Claude](https://www.anthropic.com/) - Primary writer and reviewer
- [OpenAI GPT](https://openai.com/) - Cross-validation
- [Google Gemini](https://deepmind.google/technologies/gemini/) - Alternative perspectives
- [Rich](https://github.com/Textualize/rich) - Beautiful terminal UI
- [Click](https://click.palletsprojects.com/) - CLI framework
