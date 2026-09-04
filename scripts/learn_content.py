"""Academy content aggregator: strategy lessons + glossary concepts.

Merges the two authored prose modules and re-exports the glossary so that
scripts/generate_learn_assets.py has a single import surface:

    from learn_content import LESSONS, CONCEPTS
"""

from lessons_a import LESSONS_A as _LESSONS_A
from lessons_b import LESSONS_B as _LESSONS_B
from learn_concepts import CONCEPTS as _CONCEPTS
from learn_concepts import FAMILIES as _FAMILIES

LESSONS = {}
LESSONS.update(_LESSONS_A)
LESSONS.update(_LESSONS_B)

CONCEPTS = _CONCEPTS
FAMILIES = _FAMILIES
