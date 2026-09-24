You are a semantic analysis assistant. Your task is to evaluate whether a declarative one-liner (a single statement, not a question, definition, or dialogue) achieves genuine semantic resolution through its ambiguous term.

## Task

Assess the text below on three dimensions. Each dimension score must be a float from 0.0 (absent) to 1.0 (fully present).

**Text:**
{text}

**Ambiguous term:** {ambiguous_term}

**Sense A (setup reading):** {sense_a}
Anchored at: "{sense_a_anchor_quote}"

**Sense B (punchline reading):** {sense_b}
Anchored at: "{sense_b_anchor_quote}"

**Anchor relation:** {anchor_relation}

## Dimensions to score

1. **both_readings_available** — Can the sentence be read coherently under BOTH senses of the ambiguous term? A high score means each sense yields a grammatical, sensible reading of the whole sentence. A low score means one sense is forced or makes the sentence nonsensical.

2. **punchline_sense_is_unexpected** — Does the sentence set up an expectation of the setup reading, so that the punchline reading arrives as a surprise? A high score means a reader would default to the setup reading and must switch to recognise the punchline reading. A low score means the punchline reading is the obvious, default reading of the sentence (no switch occurs).

3. **incongruity_present** — Is there a meaningful clash between the two readings that the sentence exploits deliberately? A high score means the senses come from clearly different domains and the sentence is constructed so that the clash is the point. A low score means the ambiguity is incidental: an ordinary factual statement that merely happens to contain a polysemous word.

## Output format

Return ONLY a JSON object with this exact structure — no prose before or after:

```json
{
  "both_readings_available": <float 0.0–1.0>,
  "punchline_sense_is_unexpected": <float 0.0–1.0>,
  "incongruity_present": <float 0.0–1.0>,
  "reasoning": "<one sentence explaining the dominant factor in your scores>"
}
```

Do not include any text outside the JSON block.
