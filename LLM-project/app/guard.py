"""Entity guard: a cheap lexical check layered on top of cosine similarity.

Dense embeddings encode topic well but are nearly blind to the one token that
changes the answer. With bge-small-en-v1.5:

    "reverse a singly linked list in Python?"  vs  "... in Java?"   -> 0.979

That clears any sensible threshold, so a pure-cosine cache would answer a Java
question with Python code. The guard extracts salient entities (programming
languages/tools, numbers, mid-sentence proper nouns) and refuses a hit unless
both queries mention the same set.
"""

import re
from typing import FrozenSet

# Matched even when lower-cased. Words that double as plain English ("go",
# "spring", "node", "express", "windows") are left out; the capitalisation rule
# below still catches them when written as names.
TECH_TERMS = frozenset(
    """
    python java javascript js typescript ts c c++ cpp c# csharp golang rust ruby php
    kotlin scala haskell perl lua dart julia matlab elixir erlang clojure fortran cobol
    bash zsh powershell sql nosql html css sass
    react vue angular svelte nextjs django flask fastapi rails laravel nodejs deno
    pandas numpy scipy pytorch tensorflow keras sklearn scikit-learn jax hadoop kafka
    docker kubernetes k8s terraform ansible aws azure gcp linux macos ios android ubuntu
    postgres postgresql mysql sqlite mongodb redis cassandra elasticsearch qdrant
    git github gitlab
    """.split()
)

# Capitalised words that carry no entity information.
_CAPITAL_STOPWORDS = frozenset({"i", "ok", "okay", "please", "thanks"})

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#\-]*|\d+(?:\.\d+)?")
_SENTENCE_BREAK_RE = re.compile(r"[.?!:;\n]\s*")


def extract_entities(text: str) -> FrozenSet[str]:
    entities = set()
    for sentence in _SENTENCE_BREAK_RE.split(text):
        for i, raw in enumerate(_TOKEN_RE.findall(sentence)):
            token = raw.lower()
            if token[0].isdigit() or token in TECH_TERMS:
                entities.add(token)
            elif len(raw) > 1 and (raw.isupper() or any(ch.isupper() for ch in raw[1:])):
                # Acronyms (REST, CDN) and CamelCase names (GraphQL) at any position.
                entities.add(token)
            elif i > 0 and raw[0].isupper() and token not in _CAPITAL_STOPWORDS:
                # Proper noun / acronym in the middle of a sentence (France, TCP, AWS).
                entities.add(token)
    return frozenset(entities)


def entities_match(a: str, b: str) -> bool:
    return extract_entities(a) == extract_entities(b)
