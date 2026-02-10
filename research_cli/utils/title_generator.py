"""Title generator using LLM to create academic titles from manuscript content."""

import re
from ..model_config import create_llm_for_role


async def generate_title_from_manuscript(manuscript_text: str, original_topic: str) -> str:
    """Generate an academic title from manuscript content using gemini-flash.

    Args:
        manuscript_text: Full manuscript text
        original_topic: Original user-provided topic (for fallback)

    Returns:
        Generated academic title (or original topic if generation fails)
    """
    try:
        # Extract first 3000 characters (enough for intro + abstract)
        preview = manuscript_text[:3000]

        llm = create_llm_for_role("title_generator")

        prompt = f"""Based on the following research manuscript, generate a concise, professional academic title.

MANUSCRIPT PREVIEW:
{preview}

REQUIREMENTS:
- 10-15 words maximum
- Professional academic tone
- Specific enough to convey the research focus
- Avoid generic phrases like "A Study of" or "An Analysis of"
- Do NOT use colons or subtitles unless absolutely necessary
- Capitalize properly (title case)

Respond with ONLY the title, no quotes, no explanation, no markdown."""

        response = await llm.generate(
            prompt=prompt,
            system="You generate concise academic titles from manuscript content. Respond with only the title text.",
            temperature=0.7,
            max_tokens=100,
        )

        title = response.content.strip()

        # Clean up common issues
        title = title.strip('"').strip("'").strip()
        title = re.sub(r'^Title:\s*', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\*\*', '', title)  # Remove markdown bold

        # Validate title length
        if len(title.split()) < 4 or len(title.split()) > 20:
            return original_topic

        return title

    except Exception as e:
        # Fallback to original topic on error
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Title generation failed: {e}, using original topic")
        return original_topic
