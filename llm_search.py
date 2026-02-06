"""
LLM-powered search summary generation using Arcee AI Trinity model.
"""

import os
from typing import Optional
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()


def is_available() -> bool:
    """Check if ARCEE_API_KEY is configured."""
    return bool(os.getenv("ARCEE_API_KEY"))


def generate_summary(query: str, results: list) -> Optional[str]:
    """
    Use Arcee AI Trinity model to generate a natural language summary of search results.

    Args:
        query: The user's search query
        results: List of dictionaries with keys: id, name, title, bio, unit, type, tag_names

    Returns:
        A 2-3 sentence summary that directly answers the user's query,
        or None if the API fails or is not configured.
    """
    api_key = os.getenv("ARCEE_API_KEY")
    if not api_key:
        return None

    if not results:
        return None

    # Format results for the LLM context
    formatted_results = _format_results(results)

    # Build the prompt
    prompt = f"""You are a helpful assistant for the HBS Faculty & Fellows database. Based on the search query and matching results, provide a brief 2-3 sentence summary that helps the user understand who the relevant experts are and their areas of expertise.

Query: {query}
Matching Results:
{formatted_results}

Summary:"""

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.arcee.ai/v1"
        )

        response = client.chat.completions.create(
            model="trinity",
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=256,
            temperature=0.7
        )

        # Handle different response formats
        if isinstance(response, str):
            # Arcee may return raw string
            summary = response
        elif hasattr(response, 'choices') and response.choices:
            # Standard OpenAI format
            summary = response.choices[0].message.content
        else:
            summary = str(response) if response else None

        return summary.strip() if summary else None

    except Exception as e:
        # Log the error but return None gracefully
        print(f"LLM summary generation failed: {e}")
        return None


def _format_results(results: list) -> str:
    """
    Format search results into a readable string for the LLM context.

    Args:
        results: List of result dictionaries

    Returns:
        Formatted string representation of results
    """
    formatted_lines = []

    for i, result in enumerate(results, 1):
        name = result.get("name", "Unknown")
        title = result.get("title", "")
        unit = result.get("unit", "")
        person_type = result.get("type", "")
        tag_names = result.get("tag_names", [])
        bio = result.get("bio", "")

        # Build a concise representation
        lines = [f"{i}. {name}"]

        if title:
            lines.append(f"   Title: {title}")

        if unit:
            lines.append(f"   Unit: {unit}")

        if person_type:
            lines.append(f"   Type: {person_type}")

        if tag_names:
            if isinstance(tag_names, list):
                tags_str = ", ".join(tag_names[:5])  # Limit to first 5 tags
                if len(tag_names) > 5:
                    tags_str += f" (+{len(tag_names) - 5} more)"
            else:
                tags_str = str(tag_names)
            lines.append(f"   Expertise: {tags_str}")

        if bio:
            # Truncate bio to keep context manageable
            truncated_bio = bio[:300] + "..." if len(bio) > 300 else bio
            lines.append(f"   Bio: {truncated_bio}")

        formatted_lines.append("\n".join(lines))

    return "\n\n".join(formatted_lines)
