"""Skill name normalization: the identity function for the skill vocabulary.

Deliberately conservative: lowercase, trim, collapse whitespace. Symbols are kept because they
carry meaning in tech skills ("c" vs "c++" vs "c#", ".net", "node.js"). Spelling variants
("postgres" vs "postgresql") are handled by the alias table, not by clever string rules,
because rules like "strip dots" would merge "node.js" with a hypothetical "nodejs" skill
correctly but also mangle ".net" into "net".
"""

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
MAX_SKILL_LENGTH = 64


def normalize_skill_name(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw)
    return _WHITESPACE.sub(" ", text).strip().lower()
