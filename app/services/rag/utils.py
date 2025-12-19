"""RAG utility functions.

This module provides utility functions for RAG operations,
including building template variables from channel config.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.collector.clusterer import TopicCluster


def build_template_vars_from_channel_config(
    channel_config: dict[str, Any],
    topic: Any,
    cluster: "TopicCluster | None" = None,
) -> dict[str, Any]:
    """Build template variables from channel config and topic.

    This function extracts persona, communication style, and perspective
    from channel config YAML and combines with topic information to create
    template variables for prompt rendering.

    Args:
        channel_config: Loaded channel configuration dictionary
        topic: ScoredTopic or NormalizedTopic with title, keywords, etc.
        cluster: Optional TopicCluster with aggregated multi-source info

    Returns:
        Dictionary of template variables for Mako template rendering
    """
    persona = channel_config.get("persona", {})
    communication = persona.get("communication", {})
    speech_patterns = communication.get("speech_patterns", {})
    avoid_patterns = communication.get("avoid_patterns", {})
    perspective = persona.get("perspective", {})
    content = channel_config.get("content", {})

    # Build template variables
    return {
        # Persona
        "persona_name": persona.get("name"),
        "persona_tagline": persona.get("tagline"),
        "persona_description": f"{persona.get('name', '')} - {persona.get('tagline', '')}".strip(
            " -"
        ),
        "persona_expertise": perspective.get("core_values", []),
        # Communication style
        "communication_tone": communication.get("tone"),
        "communication_formality": communication.get("formality"),
        "sentence_endings": speech_patterns.get("sentence_endings", []),
        "connectors": speech_patterns.get("connectors", []),
        "avoid_words": avoid_patterns.get("words", []),
        # Perspective
        "perspective_values": perspective.get("core_values", []),
        "perspective_biases": ", ".join(perspective.get("contrarian_views", [])),
        "perspective_contrarian": len(perspective.get("contrarian_views", [])) > 0,
        # Topic
        "topic_title": getattr(topic, "title_normalized", str(topic)),
        "topic_summary": getattr(topic, "summary", None),
        "topic_keywords": getattr(topic, "keywords", []) or [],
        "topic_categories": getattr(topic, "categories", []) or [],
        # Generation config
        "video_format": content.get("format", "shorts"),
        "target_duration": content.get("target_duration", 55),
        "content_style": "opinion",
        # Retrieved content (empty for demo, would come from RAG)
        "similar_content": None,
        "opinions": None,
        "examples": None,
        "hooks": None,
        # Multi-source cluster info (if available)
        "multi_source": cluster is not None and cluster.source_count > 1,
        "source_count": cluster.source_count if cluster else 1,
        "source_names": list(cluster.sources) if cluster else [],
        "related_titles": (
            [t.title_original for t in cluster.related_topics[:5]]
            if cluster and cluster.related_topics
            else []
        ),
        "combined_keywords": cluster.combined_keywords if cluster else [],
        "total_engagement": cluster.total_engagement if cluster else 0,
    }


__all__ = ["build_template_vars_from_channel_config"]
