"""Benchmark workload: 200 labelled queries.

    120 base queries        unique, should MISS on first sight
     60 paraphrases         of the first 60 bases, should HIT their base
     20 entity swaps        same wording, different entity, should MISS

Base + swaps = 140 unique questions; paraphrases = 30% of the workload.
The swaps are the ones a pure-cosine cache gets wrong. Two of them
(Celsius/Fahrenheit direction, sin/cos) are deliberately beyond the entity
guard too, so the report shows its limits rather than hiding them.
"""

import random
from dataclasses import dataclass
from typing import List, Optional

# (base, paraphrase, entity_swap)
_ROWS = [
    # --- programming ---
    ("How do I reverse a singly linked list in Python?", "Write Python code to reverse a singly linked list", "How do I reverse a singly linked list in Java?"),
    ("How do I read a CSV file with pandas?", "What's the way to load a CSV file using pandas?", "How do I read a CSV file in R?"),
    ("What is the difference between a list and a tuple in Python?", "Python: list vs tuple, what's the difference?", None),
    ("How do I remove duplicates from an array in JavaScript?", "Best way to dedupe a JavaScript array", "How do I remove duplicates from an array in PHP?"),
    ("Explain how async/await works in JavaScript", "How does async await work in JavaScript?", "Explain how async/await works in Rust"),
    ("How do I create a virtual environment in Python?", "Steps to set up a Python virtual environment", None),
    ("What is a closure in programming?", "Can you explain what closures are in programming?", None),
    ("How do I merge two dictionaries in Python?", "Combine two Python dicts into one", "How do I merge two dictionaries in C#?"),
    ("How do I handle exceptions in Java?", "What's the proper way to do exception handling in Java?", "How do I handle exceptions in Kotlin?"),
    ("What is the time complexity of binary search?", "How fast is binary search in terms of time complexity?", None),
    ("How do I write a unit test with pytest?", "Show me how to write unit tests using pytest", None),
    ("What does the yield keyword do in Python?", "Explain Python's yield keyword", None),
    # --- web / devops ---
    ("How do I build a Docker image from a Dockerfile?", "Command to build a Docker image using a Dockerfile", "How do I build a Podman image from a Containerfile?"),
    ("What is the difference between a Kubernetes Deployment and a StatefulSet?", "Kubernetes Deployment vs StatefulSet differences", None),
    ("How do I undo the last git commit?", "How can I revert my most recent commit in git?", None),
    ("What is a reverse proxy?", "Can you explain what a reverse proxy does?", None),
    ("How do I set up HTTPS with Let's Encrypt on Nginx?", "Configure HTTPS on Nginx using Let's Encrypt", "How do I set up HTTPS with Let's Encrypt on Apache?"),
    ("What is CORS and why does my browser block requests?", "Why is my browser blocking requests because of CORS?", None),
    ("How do I resolve a merge conflict in git?", "Steps to fix a git merge conflict", None),
    ("What are the benefits of using a CDN?", "Why should I use a content delivery network?", None),
    ("How does DNS resolution work?", "Explain how DNS lookups work", None),
    ("What is the difference between REST and GraphQL?", "REST vs GraphQL: which is better and how do they differ?", None),
    ("How do I schedule a cron job on Linux?", "How to set up a cron job in Linux", "How do I schedule a cron job on macOS?"),
    ("What is a load balancer?", "Explain what load balancers do", None),
    # --- databases ---
    ("How do I find duplicate rows in SQL?", "SQL query to detect duplicate records", None),
    ("What is the difference between INNER JOIN and LEFT JOIN?", "Explain INNER JOIN vs LEFT JOIN", None),
    ("What is database normalization?", "Can you explain normalization in databases?", None),
    ("How do I create an index in PostgreSQL?", "Syntax for adding an index in PostgreSQL", "How do I create an index in MongoDB?"),
    ("What are ACID properties in databases?", "Explain the ACID properties of database transactions", None),
    ("When should I use Redis?", "What are good use cases for Redis?", None),
    # --- machine learning ---
    ("What is overfitting in machine learning?", "Explain overfitting in machine learning models", None),
    ("How does gradient descent work?", "Explain the gradient descent algorithm", None),
    ("What is the difference between supervised and unsupervised learning?", "Supervised vs unsupervised learning explained", None),
    ("What is a transformer model?", "Explain how transformer neural networks work", None),
    ("How do I train a random forest with scikit-learn?", "Train a random forest classifier using scikit-learn", "How do I train a random forest with XGBoost?"),
    ("What is the vanishing gradient problem?", "Explain the vanishing gradient issue in deep networks", None),
    ("What is cross-validation?", "Why do we use cross-validation in machine learning?", None),
    ("What does a confusion matrix show?", "How do I read a confusion matrix?", None),
    ("What is retrieval-augmented generation?", "Can you explain retrieval augmented generation?", None),
    ("How do I choose the learning rate for a neural network?", "Tips for picking a good learning rate when training neural networks", None),
    ("What is the difference between precision and recall?", "Precision vs recall, explained simply", None),
    ("How do word embeddings work?", "Explain how word embeddings represent meaning", None),
    # --- science ---
    ("Why is the sky blue?", "What makes the sky appear blue?", None),
    ("What causes the seasons on Earth?", "Why does Earth have seasons?", None),
    ("How do vaccines work?", "Explain how vaccines train the immune system", None),
    ("What is photosynthesis?", "Explain the process of photosynthesis", None),
    ("What is Einstein's theory of relativity?", "Can you explain Einstein's theory of relativity?", None),
    ("How do black holes form?", "What is the process by which black holes are formed?", None),
    ("What is the boiling point of water at sea level?", "At what temperature does water boil at sea level?", "What is the boiling point of water at 3000 meters altitude?"),
    ("What is DNA made of?", "What are the building blocks of DNA?", None),
    ("Why do we have tides?", "What causes ocean tides?", None),
    ("What is quantum entanglement?", "Explain quantum entanglement in simple terms", None),
    ("How far is the Moon from Earth?", "What is the distance between Earth and the Moon?", "How far is Mars from Earth?"),
    ("What is the speed of light?", "How fast does light travel?", None),
    # --- geography / history ---
    ("What is the capital of Australia?", "Which city is Australia's capital?", "What is the capital of Canada?"),
    ("Who was the first president of the United States?", "Name the first president of the United States", "Who was the first president of France?"),
    ("What caused World War I?", "What were the main causes of World War I?", "What caused World War II?"),
    ("When did the Roman Empire fall?", "When was the fall of the Roman Empire?", None),
    ("What is the longest river in the world?", "Which river is the longest in the world?", None),
    ("What was the Industrial Revolution?", "Explain the Industrial Revolution", None),
    # --- everything else: base only ---
    ("How many hours of sleep do adults need?", None, None),
    ("What are the health benefits of green tea?", None, None),
    ("How do I make sourdough bread at home?", None, None),
    ("What is a good beginner workout routine?", None, None),
    ("How do I cook rice on the stove?", None, None),
    ("What is compound interest?", None, None),
    ("How does a credit score work?", None, None),
    ("What is the difference between a Roth IRA and a traditional IRA?", None, None),
    ("How do I make a budget?", None, None),
    ("What is inflation?", None, None),
    ("How do I write a cover letter?", None, None),
    ("Tips for a successful job interview", None, None),
    ("How do I improve my public speaking?", None, None),
    ("What is the Pomodoro technique?", None, None),
    ("How do I learn a new language quickly?", None, None),
    ("How do I change a flat tire?", None, None),
    ("What should I pack for a camping trip?", None, None),
    ("How do I get rid of fruit flies in my kitchen?", None, None),
    ("How do I remove a red wine stain from carpet?", None, None),
    ("How often should I water succulents?", None, None),
    ("What is the plot of Hamlet?", None, None),
    ("Who painted the Mona Lisa?", None, None),
    ("Recommend some classic science fiction novels", None, None),
    ("What are the rules for castling in chess?", None, None),
    ("How does the offside rule work in soccer?", None, None),
    ("What is the best way to memorize a speech?", None, None),
    ("How do I meditate as a beginner?", None, None),
    ("How do airplanes stay in the air?", None, None),
    ("How does a refrigerator keep food cold?", None, None),
    ("What is blockchain technology?", None, None),
    ("How do solar panels generate electricity?", None, None),
    ("What is the greenhouse effect?", None, None),
    ("How do I convert Celsius to Fahrenheit?", None, "How do I convert Fahrenheit to Celsius?"),
    ("What is the Pythagorean theorem?", None, None),
    ("How do I calculate the area of a circle?", None, None),
    ("What is a prime number?", None, None),
    ("What is the derivative of sin(x)?", None, "What is the derivative of cos(x)?"),
    ("Explain Bayes' theorem", None, None),
    ("What is a hash table?", None, None),
    ("How does HTTPS encryption work?", None, None),
    ("What is two-factor authentication?", None, None),
    ("How do I create a strong password?", None, None),
    ("What is phishing and how do I spot it?", None, None),
    ("What is the difference between RAM and storage?", None, None),
    ("How do I speed up a slow laptop?", None, None),
    ("What is the difference between a process and a thread?", None, None),
    ("How do I center a div in CSS?", None, None),
    ("What is dependency injection?", None, None),
    ("What is the CAP theorem?", None, None),
    ("How does garbage collection work in Java?", None, "How does garbage collection work in Go?"),
    ("What is a memory leak?", None, None),
    ("How do I profile a slow Python script?", None, "How do I profile a slow Ruby script?"),
    ("What is the difference between HTTP GET and POST?", None, None),
    ("What is WebAssembly?", None, None),
    ("How do I write a haiku?", None, None),
    ("Give me a recipe for chocolate chip cookies", None, None),
    ("What is the difference between weather and climate?", None, None),
    ("How do earthquakes happen?", None, None),
    ("What is stoicism?", None, None),
    ("What is the trolley problem?", None, None),
]


@dataclass
class Query:
    text: str
    group: str  # answers are interchangeable within a group
    kind: str  # "base" | "paraphrase" | "swap"
    parent: Optional[str] = None  # base text this query is derived from


def build_workload(seed: int = 7, min_gap: int = 20) -> List[Query]:
    """Shuffle, but keep every derived query at least `min_gap` slots after its base
    so concurrent requests cannot race a paraphrase ahead of the entry it should hit."""
    rng = random.Random(seed)
    bases, derived = [], []
    for i, (base, para, swap) in enumerate(_ROWS):
        bases.append(Query(base, f"g{i:03d}", "base"))
        if para:
            derived.append(Query(para, f"g{i:03d}", "paraphrase", parent=base))
        if swap:
            derived.append(Query(swap, f"s{i:03d}", "swap", parent=base))
    rng.shuffle(bases)
    order = list(bases)
    for q in rng.sample(derived, len(derived)):
        earliest = next(i for i, b in enumerate(order) if b.text == q.parent) + min_gap + 1
        order.insert(rng.randint(min(earliest, len(order)), len(order)), q)
    return order


if __name__ == "__main__":
    wl = build_workload()
    kinds = {k: sum(q.kind == k for q in wl) for k in ("base", "paraphrase", "swap")}
    print(len(wl), kinds)
