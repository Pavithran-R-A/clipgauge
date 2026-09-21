"""Bounded content-category guidance for model interpretation."""

from __future__ import annotations

from dataclasses import dataclass

CONTENT_CATEGORIES = (
    "auto",
    "general",
    "knowledge",
    "business",
    "opinion",
    "experience",
    "speech",
    "content_review",
    "entertainment",
)


@dataclass(frozen=True)
class ContentCategoryProfile:
    category: str
    editorial_characteristics: str
    hook_payoff: str
    story_shapes: tuple[str, ...]
    title_tone: str
    collection_hint: str
    duration_hint: str

    @property
    def guidance(self) -> str:
        return (
            f"Category: {self.category}. Editorial focus: {self.editorial_characteristics} "
            f"Hook/payoff: {self.hook_payoff} Story shapes: {', '.join(self.story_shapes)}. "
            f"Title tone: {self.title_tone}. Collection hint: {self.collection_hint}. "
            f"Duration guidance: {self.duration_hint}. Treat this as bounded guidance, "
            "not evidence. Do not invent facts or override measured signals."
        )


_PROFILES = {
    "auto": ContentCategoryProfile("auto", "Use the clip's observed subject and structure.", "Prefer an observable opening and payoff.", ("general",), "clear", "group by premise", "use measured fit"),
    "general": ContentCategoryProfile("general", "Prioritize clarity and complete thought.", "Make the opening understandable and the ending coherent.", ("setup-payoff", "explanation"), "clear", "group by topic", "use measured fit"),
    "knowledge": ContentCategoryProfile("knowledge", "Prioritize useful explanations and concrete insight.", "Reward a clear question, answer, or surprising fact.", ("question-answer", "claim-evidence"), "informative", "group by lesson", "favor self-contained context"),
    "business": ContentCategoryProfile("business", "Prioritize decisions, tradeoffs, and practical outcomes.", "Reward a problem, decision, or measurable consequence.", ("problem-solution", "case-study"), "precise", "group by business theme", "favor complete rationale"),
    "opinion": ContentCategoryProfile("opinion", "Prioritize a stated viewpoint and supporting reasoning.", "Reward a clear stance followed by a reason or implication.", ("claim-reason", "contrast"), "distinctive", "group by viewpoint", "preserve enough reasoning"),
    "experience": ContentCategoryProfile("experience", "Prioritize personal events, emotion, and reflection.", "Reward an identifiable moment and its consequence.", ("story", "turning-point"), "human", "group by experience theme", "preserve story context"),
    "speech": ContentCategoryProfile("speech", "Prioritize spoken clarity and memorable phrasing.", "Reward a complete spoken point with a strong cadence.", ("statement", "question-answer"), "natural", "group by speaker theme", "preserve conversational context"),
    "content_review": ContentCategoryProfile("content_review", "Prioritize a concrete evaluation and supporting detail.", "Reward a clear verdict connected to observed evidence.", ("verdict-reason", "comparison"), "specific", "group by reviewed subject", "preserve evidence"),
    "entertainment": ContentCategoryProfile("entertainment", "Prioritize comedic, dramatic, or surprising moments.", "Reward a visible setup and earned reaction or payoff.", ("setup-punchline", "reveal"), "lively", "group by theme", "use measured pacing"),
}


def validate_category(value: str | None) -> str:
    normalized = str(value or "auto").strip().lower()
    if normalized not in CONTENT_CATEGORIES:
        raise ValueError(f"content category must be one of: {', '.join(CONTENT_CATEGORIES)}")
    return normalized


def category_profile(value: str | None) -> ContentCategoryProfile:
    return _PROFILES[validate_category(value)]
