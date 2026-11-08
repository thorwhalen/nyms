"""nyms: reversible pseudonymisation of text before it reaches an AI.

A deterministic (non-AI) pass detects personal and sensitive identifiers in Danish and English
text, replaces them with surrogates from a configurable strategy, remembers the mapping per
project so the same person is the same pseudonym in every document, and puts the originals
back into whatever the AI answers.

>>> from nyms import Pseudonymiser
>>> p = Pseudonymiser(store={})
>>> p.pseudonymise("Mail hans.jensen@example.dk, tlf. 12 34 56 78").text
'Mail [EMAIL_1], tlf. [PHONE_1]'
"""

from nyms.core import CAVEAT, Pseudonymiser, Reidentified, Result
from nyms.detect import Detector, default_detectors, detect, gazetteer_detector
from nyms.mapping import MappingStore, local_mapping_store, normalise
from nyms.policy import Policy
from nyms.spans import Span, apply_replacements, resolve_overlaps
from nyms.surrogates import Aliases, Counter, KeyedWords, RandomWords, readable, words_from_bytes
from nyms.taxonomy import ENTITY_TYPES, EntityType

__all__ = [
    "CAVEAT", "Pseudonymiser", "Reidentified", "Result", "Detector", "default_detectors", "detect",
    "gazetteer_detector", "MappingStore", "local_mapping_store", "normalise", "Policy", "Span",
    "apply_replacements", "resolve_overlaps", "Aliases", "Counter", "KeyedWords", "RandomWords",
    "readable", "words_from_bytes", "ENTITY_TYPES", "EntityType",
]
