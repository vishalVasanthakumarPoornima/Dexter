from __future__ import annotations

import re


COMMON_SKILLS = [
    "python",
    "typescript",
    "javascript",
    "react",
    "fastapi",
    "sql",
    "sqlite",
    "postgres",
    "docker",
    "aws",
    "gcp",
    "azure",
    "linux",
    "git",
    "machine learning",
    "llm",
    "rag",
    "cybersecurity",
    "security",
    "backend",
    "frontend",
    "api",
    "playwright",
    "automation",
    "java",
    "c++",
    "go",
    "node",
]


def extract_skills(text: str, configured: list[str] | None = None) -> list[str]:
    blob = (text or "").lower()
    skills = []
    for skill in [*(configured or []), *COMMON_SKILLS]:
        pattern = r"\b" + re.escape(skill.lower()) + r"\b"
        if re.search(pattern, blob) and skill.lower() not in [s.lower() for s in skills]:
            skills.append(skill)
    return skills
