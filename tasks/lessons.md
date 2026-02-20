# Lessons Learned

## LLM Response Parsing Safety

**Date**: 2025-02-10
**Trigger**: KeyError crashes when LLM omitted expected JSON fields

### Rule
After `repair_json()` or `json.loads()` on LLM output, **never** use `dict["key"]` directly. Always use `.get("key", fallback)`.

### Why
LLMs can and will omit fields from the requested JSON schema, especially under:
- Token limits / truncation
- Malformed JSON that `repair_json()` partially recovers
- Model confusion about which fields are required

### Fallback conventions
| Field type | Fallback |
|---|---|
| Identifier (`id`) | `f"section_{idx}"` (index-based) |
| Title/name | `f"Section {idx}"` or `"Untitled"` |
| Text field (`description`, `purpose`) | `""` |
| List field (`key_points`, `evidence`) | `[]` |
| Numeric (`order`, `year`, `target_length`) | Sensible default (idx, 0, 500) |

### Applies to
All files under `research_cli/agents/` that parse LLM JSON responses.

---

## Orphan Result Directories

**Date**: 2025-02-10
**Trigger**: Server reload detected orphan directory with no checkpoint/complete marker, causing confusion

### Rule
`scan_interrupted_workflows` must handle **three** cases:
1. Checkpoint exists, no complete = interrupted (resumable)
2. No checkpoint, no complete, but has files = orphan/early-crash (mark as failed, allow retry)
3. Complete exists = finished (ignore)

### Why
If a workflow crashes during team formation or before the first checkpoint is saved, the result directory exists but has no checkpoint. Without explicit detection, these directories are invisible to the UI and can cause issues on reload.

---

## SDK 마이그레이션 시 플랜의 필드명/메서드명을 맹신하지 말 것

**Date**: 2026-02-19
**Trigger**: `google-generativeai` → `google-genai` 마이그레이션에서 플랜에 적힌 필드명·메서드명이 3개 틀렸고, API 테스트 없이 "106 tests passed"로 완료 처리함

### 틀렸던 것
1. **토큰 필드명**: 플랜은 `input_tokens`/`output_tokens`라 했지만 실제는 `prompt_token_count`/`candidates_token_count` — 토큰 카운트가 전부 `None`으로 나옴
2. **스트리밍 메서드명**: 플랜은 `stream_generate_content`라 했지만 실제는 `generate_content_stream` — `AttributeError` 발생
3. **스트리밍 호출 방식**: `async for chunk in coro()`가 아니라 `stream = await coro()` 후 `async for chunk in stream` — `TypeError` 발생

### Rule
- SDK 마이그레이션 시 **플랜에 적힌 API 이름을 그대로 코드에 쓰지 말 것**
- 코드 작성 전에 `dir(obj)` 또는 SDK 소스를 읽어서 실제 메서드명/필드명을 확인
- 임포트·구문 검사만 통과하는 단위 테스트는 SDK 마이그레이션 검증이 아님
- **실제 API 호출 테스트를 반드시 구현 직후에 실행** — 특히 마이그레이션 동기가 API 오류였으면 더더욱

### Applies to
`research_cli/llm/` 아래 모든 프로바이더, 향후 SDK 업그레이드/전환 작업 전반.

---

## 소스 파이프라인 참고문헌 중복 제거

**Date**: 2026-02-20
**Trigger**: 리뷰어가 "fabricated references"로 REJECT — 근본 원인은 환각이 아니라 같은 논문이 다른 ID/포맷으로 38개 중복 저장

### 중복 발생 지점
1. **`source_retriever.py` `search_all()`**: API마다 같은 논문의 제목이 미세하게 다름 (`"Title"` vs `"Title | Journal"` vs `"Title - PMC"`)
2. **`collaborative_research.py` `_integrate_contributions()`**: co-author가 `available_references`로 받은 소스를 다시 반환 → 새 ID로 또 추가

### 제목 정규화 시 잡아야 할 패턴
| 패턴 | 예시 |
|---|---|
| `\|` 파이프 접미사 | `"Title \| ICML 2024"` |
| `–` `—` em-dash 접미사 | `"Title – Proceedings"` |
| ` - ` 하이픈 접미사 | `"Title - PMC"`, `"Title - ScienceDirect"` |
| arXiv ID prefix | `"[2412.01708] Title"` |
| 구두점/공백 차이 | `"Title!"` vs `"Title"`, 다중 공백 |

### Rule
- 참고문헌 dedup은 **DOI 우선** → **정규화된 제목** 순서로 비교
- `add_reference()`는 중복 시 **기존 Reference를 반환**하여 citation ID 리매핑 가능하게
- 정규화 함수는 `utils/normalize_ref.py`에 단일 소스로 관리 (중복 코드 금지)
- LLM이 반환하는 bogus DOI (`"Not provided"`, `"N/A"` 등)는 `clean_doi()`로 필터링

### 검증 시 배운 점
1. **정규화는 실데이터 기반 반복 개선 필수** — 코드 리뷰만으론 `" - PMC"`, arXiv prefix 같은 패턴을 못 잡음. E2E 출력을 열어서 남은 중복을 직접 확인해야 함
2. **다음 과제: manuscript writing 유령 citation** — dedup 해결 후에도 LLM이 research_notes 밖의 citation을 자체 생성하는 문제 잔존 (CS E2E에서 ref [20] 발견). 소스 파이프라인이 아니라 manuscript writing 프롬프트 제약이 필요

### Applies to
`research_cli/utils/normalize_ref.py`, `research_cli/utils/source_retriever.py`, `research_cli/models/collaborative_research.py`, `research_cli/workflow/collaborative_research.py`
