# Quick Start: Automated AI Research Platform

## Installation

```bash
cd /home/jazz/git/ai-backed-research
source venv/bin/activate
```

## Basic Usage

### 1. Run Complete Workflow (Interactive)
```bash
# AI will propose expert team, you review and edit
python -m research_cli.cli run "Your Research Topic"
```

**What happens:**
1. AI analyzes topic and proposes expert team
2. You see proposed experts with rationale
3. Interactive menu lets you accept/edit/add/remove experts
4. Workflow generates manuscript and runs peer review
5. Results exported with performance metrics

### 2. Run with Auto-Accept Team
```bash
# AI proposes team, automatically accepted
python -m research_cli.cli run "Optimistic Rollups Security" --auto-accept-team
```

### 3. Custom Team Size
```bash
# Request specific number of experts
python -m research_cli.cli run "MEV in Ethereum" --num-experts 5
```

### 4. Use Existing Manuscript
```bash
# Skip manuscript generation, use your own
python -m research_cli.cli run "Privacy Pools" --manuscript my_paper.md
```

### 5. Custom Parameters
```bash
# Full control over workflow
python -m research_cli.cli run "Layer 2 Bridges" \
    --num-experts 4 \
    --max-rounds 5 \
    --threshold 7.5 \
    --auto-accept-team
```

## Command Options

| Option | Default | Description |
|--------|---------|-------------|
| `--num-experts` | 3 | Number of expert reviewers (2-10+) |
| `--auto-accept-team` | false | Skip interactive editing |
| `--max-rounds` | 3 | Maximum review rounds |
| `--threshold` | 8.0 | Score threshold for acceptance (0-10) |
| `--manuscript` | None | Path to existing manuscript file |

## Interactive Team Editor

When not using `--auto-accept-team`, you'll see:

```
Team Editing Menu:
  [A] Accept team and continue
  [E] Edit an expert
  [D] Delete an expert
  [N] Add new expert
  [V] View current team
  [Q] Quit (cancel workflow)
```

### Editing an Expert
- Change domain/expertise area
- Modify focus areas
- Select model (Opus 4.5 or Sonnet 4.5)

### Adding an Expert
- Enter domain (e.g., "Game Theory Specialist")
- Add focus areas (one per line)
- Select model

### Requirements
- Minimum 2 experts required
- At least 1 focus area per expert

## Output

### Directory Structure
```
results/
└── your-research-topic/
    ├── manuscript_v1.md           # Initial draft
    ├── manuscript_v2.md           # After round 1 revision
    ├── manuscript_final.md        # Final accepted version
    ├── round_1.json              # Round 1 reviews
    ├── round_2.json              # Round 2 reviews
    └── workflow_complete.json    # Complete workflow data
```

### Workflow Data
`workflow_complete.json` contains:
- Expert team configuration
- All review rounds
- Performance metrics (timing, tokens, cost)
- Final scores and decision

### Web Viewer
After completion, results are auto-exported to:
```
web/data/workflows.json
```

View at: `http://localhost:8080/web/review-viewer.html`

## Performance Metrics

The system tracks:
- Total workflow duration
- Team composition time
- Initial draft generation time
- Per-round timing:
  - Each reviewer's time
  - Moderator decision time
  - Revision time
- Token usage per operation
- Estimated cost

View in:
1. CLI output (summary after completion)
2. Web viewer (charts and detailed breakdown)

## Examples

### Example 1: Blockchain Research (4 experts)
```bash
python -m research_cli.cli run "Zero-Knowledge Rollup Security Models" --num-experts 4
```

**Expected team:**
- Zero-Knowledge Cryptography Expert
- Smart Contract Security Expert
- Distributed Systems Expert
- Economics/Incentives Expert

### Example 2: Quick Analysis (Auto-accept)
```bash
python -m research_cli.cli run "EIP-4844 Proto-Danksharding" \
    --auto-accept-team \
    --num-experts 3 \
    --max-rounds 2
```

### Example 3: Deep Review (Large team, high threshold)
```bash
python -m research_cli.cli run "Cross-Chain Bridge Security" \
    --num-experts 6 \
    --threshold 8.5 \
    --max-rounds 5
```

## Troubleshooting

### "No LLM API key configured"
Set your API key:
```bash
# Option 1: Shared router key (LiteLLM/OpenRouter)
export LLM_API_KEY="your-router-key"
export LLM_BASE_URL="https://your-endpoint/v1"

# Option 2: Direct provider key
export ANTHROPIC_API_KEY="your-anthropic-key"

# Or create .env file with the above variables
```

### Workflow takes too long
- Reduce `--num-experts` (fewer reviewers = faster)
- Use `--auto-accept-team` (skips manual editing)
- Reduce `--max-rounds`

### Team composition seems off
- Don't use `--auto-accept-team` - review and edit the team
- Add specific context about your research needs
- Manually add/remove experts in interactive mode

## Advanced Usage

### Save Team Templates (Future)
Team configurations can be reused by saving the expert team from `workflow_complete.json`.

### Performance Analysis
Compare timing across different team sizes:
```bash
# 3 experts
python -m research_cli.cli run "Topic" --num-experts 3 --auto-accept-team

# 5 experts
python -m research_cli.cli run "Topic" --num-experts 5 --auto-accept-team
```

View performance comparison in web viewer.

## Tips

1. **Let AI compose first**: The AI is good at identifying needed expertise
2. **Use interactive mode**: Review team proposals, they're not always perfect
3. **Adjust team size**: Complex topics benefit from 4-5 experts
4. **Set realistic thresholds**: 8.0 is challenging, 7.5 more achievable
5. **Check performance metrics**: Identify bottlenecks in web viewer

## Other CLI Commands

### Initialize project
```bash
python -m research_cli.cli init "Topic Name"
```

### List projects
```bash
python -m research_cli.cli list
```

### Check configuration
```bash
python -m research_cli.cli status --check-keys
```

### Test LLM providers
```bash
python -m research_cli.cli test --test-providers
```

## Support

- Documentation: `README_CLI.md`
- Implementation details: `IMPLEMENTATION_SUMMARY.md`
- Issues: https://github.com/anthropics/claude-code/issues
