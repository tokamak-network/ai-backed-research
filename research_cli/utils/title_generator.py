"""Title generator using LLM to create academic titles from manuscript content."""

import logging
import re
from ..model_config import create_llm_for_role

logger = logging.getLogger(__name__)

_AUDIENCE_GUIDANCE = {
    "beginner": (
        "The target audience is BEGINNERS (general public, students).\n"
        "- Use clear, accessible language that a non-specialist can understand\n"
        "- Prefer concrete nouns over abstract jargon\n"
        "- Convey the practical relevance or 'why it matters'\n"
        "- Example tone: 'How Blockchain Rollups Speed Up Ethereum Transactions'"
    ),
    "intermediate": (
        "The target audience is INTERMEDIATE readers (practitioners, graduate students).\n"
        "- Use standard domain terminology but avoid deep specialist jargon\n"
        "- Balance accessibility with technical precision\n"
        "- Convey both the subject and the analytical angle\n"
        "- Example tone: 'Evaluating Security Trade-offs in Optimistic Versus ZK Rollup Architectures'"
    ),
    "professional": (
        "The target audience is PROFESSIONAL researchers and domain experts.\n"
        "- Use precise academic terminology appropriate for peer-reviewed literature\n"
        "- Emphasize methodology, scope, or novel contribution\n"
        "- Formal and specific — assume reader familiarity with the field\n"
        "- Example tone: 'Formal Verification of Fraud Proof Mechanisms in Optimistic Rollup Protocols'"
    ),
}


async def generate_title_from_manuscript(
    manuscript_text: str,
    original_topic: str,
    audience_level: str = "professional",
) -> str:
    """Generate an academic title from manuscript content.

    Generates an English title whose register matches the audience level.
    Falls back to original topic on any failure.

    Args:
        manuscript_text: Full manuscript text
        original_topic: Original user-provided topic (for fallback)
        audience_level: "beginner", "intermediate", or "professional"

    Returns:
        Generated title (or original topic if generation fails)
    """
    try:
        preview = manuscript_text[:4000]

        audience_guide = _AUDIENCE_GUIDANCE.get(audience_level, _AUDIENCE_GUIDANCE["professional"])

        llm = create_llm_for_role("title_generator")

        prompt = f"""Based on the following research manuscript, generate a concise title IN ENGLISH.

ORIGINAL TOPIC: {original_topic}

AUDIENCE LEVEL:
{audience_guide}

MANUSCRIPT PREVIEW:
{preview}

REQUIREMENTS:
- The title MUST be in English, even if the topic is in another language
- The title MUST be different from the original topic above — transform it into a proper title
- 8-15 words maximum
- Match the register to the audience level described above
- Specific enough to convey the actual research focus and key findings
- Avoid generic phrases like "A Study of" or "An Analysis of"
- Do NOT use colons or subtitles unless absolutely necessary
- Capitalize properly (title case)

Respond with ONLY the title text on a single line. No quotes, no explanation, no markdown, no prefix."""

        response = await llm.generate(
            prompt=prompt,
            system="You generate concise English titles from manuscript content. Match the tone and vocabulary to the specified audience level. Respond with only the title text, nothing else.",
            temperature=0.7,
            max_tokens=100,
        )

        title = response.content.strip()

        # Clean up common issues
        title = title.strip('"').strip("'").strip()
        title = re.sub(r'^Title:\s*', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\*\*', '', title)  # Remove markdown bold
        title = re.sub(r'\n.*', '', title)  # Take only the first line

        # Validate: must be reasonable length
        if len(title) < 15 or len(title) > 200:
            logger.warning(
                f"Title length out of range ({len(title)} chars): {title!r}, "
                f"using original topic"
            )
            return original_topic

        # Reject if title is identical to original topic
        if title.strip().lower() == original_topic.strip().lower():
            logger.warning(
                f"Generated title identical to topic: {title!r}, "
                f"using original topic (title generator did not differentiate)"
            )
            return original_topic

        return title

    except Exception as e:
        logger.warning(f"Title generation failed: {e}, using original topic")
        return original_topic
