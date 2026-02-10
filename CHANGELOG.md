# Changelog

All notable changes to Autonomous Research Press will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-02-10

### Added
- **Audience-Level Formatting**: Three distinct output formats
  - Professional: Academic abstract (150-250 words)
  - Intermediate: TL;DR + Key Takeaways (practical focus)
  - Beginner: TL;DR + Why This Matters (accessible, no jargon)
- **Auto-Title Generation**: LLM generates academic titles from manuscript content
  - Uses Claude Haiku for cost efficiency
  - Replaces raw topic with polished academic title
- **Dynamic Category Classification**: POST `/api/classify-topic` endpoint
  - Auto-classifies research topics into primary + secondary categories
  - Uses Claude Haiku for stable, accurate classification
- **Dynamic Reviewer Generation**: Refactored `/api/propose-reviewers`
  - Generates topic-specific reviewers via LLM (not fixed pool)
  - Creates 3 expert reviewers tailored to the specific research topic
- **UI 2-Step Flow** (ask-topic.html):
  - Step 1: "Analyze Topic" → auto-classify category
  - Step 2: "Generate Team & Reviewers" → create authors + reviewers
- **Model Management**: Centralized configuration in `config/models.json`
  - New roles: `categorizer`, `title_generator`
  - All lightweight tasks use `tier: light` (Claude Haiku)
- **Lessons Documentation**: `tasks/lessons.md` for pattern tracking
- **Version Tracking**: VERSION file and CHANGELOG.md

### Changed
- **Section Structure**: LLM now freely designs section structure based on topic (removed fixed templates)
- **Moderator Threshold**: Explicitly pass threshold to moderator for better decision-making
  - Scores >= threshold should be accepted unless fundamental flaws exist
- **LLM Response Parsing**: All `dict["key"]` → `.get("key", fallback)` for safety
- **Frontend Title Display**: Show generated title instead of raw topic in article.html and review.html

### Fixed
- **Orphan Directory Detection**: Improved `scan_interrupted_workflows` to handle crashed workflows
- **Reviewer Fallback**: Fixed `focus_areas` empty list issue in fallback reviewers
- **Citation Gaps**: Better fallback handling for missing LLM response fields

### Performance
- **Cost Optimization**: Lightweight tasks (categorization, title generation) use Haiku instead of Opus/Sonnet
- **Stability**: Switched from Gemini to Claude Haiku for classification tasks (more reliable)

---

## Version Format

- **MAJOR**: Breaking changes (incompatible API changes)
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

Example: `1.2.3` = Major version 1, Minor version 2, Patch version 3
