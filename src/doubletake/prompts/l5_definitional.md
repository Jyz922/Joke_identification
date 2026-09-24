You are a semantic analysis assistant. Your task is to evaluate whether a definitional one-liner joke achieves genuine semantic resolution through its ambiguous term.

## Task

Assess the joke below on three dimensions. Each dimension score must be a float from 0.0 (absent) to 1.0 (fully present).

**Joke text:**
{text}

**Ambiguous term:** {ambiguous_term}

**Conventional reading (the reading the definition switches away from):** {other_sense}
Anchored at: "{other_sense_anchor_quote}"

**Punchline reading (the compound-split reading the definition resolves to):** {resolving_sense}
Anchored at: "{resolving_sense_anchor_quote}"

**Anchor relation:** {anchor_relation}

## Important note on same-span anchors

If the two readings' anchor quotes are identical, this is expected for compound-split jokes: both readings anchor to the same surface token (the compound word itself). Do NOT penalise same-span anchors when anchor_relation is "resegmentation". Evaluate the semantic contrast between the two readings, not the location of the anchor.

## Dimensions to score

1. **setup_invites_literal** — Does the framing before or around the ambiguous term naturally invite the conventional (non-split) reading first? A high score means the conventional reading is the default expectation.

2. **punchline_exploits_split** — Does the punchline body coherently exploit the compound-split reading of the term? A high score means the split reading is clearly operative in the punchline and semantically coherent.

3. **contrast_strength** — How distinct are the two readings from each other? A high score means the conventional and compound-split readings belong to substantially different semantic domains, maximising the surprise of the reinterpretation.

## Output format

Return ONLY a JSON object with this exact structure — no prose before or after:

```json
{
  "setup_invites_literal": <float 0.0–1.0>,
  "punchline_exploits_split": <float 0.0–1.0>,
  "contrast_strength": <float 0.0–1.0>,
  "reasoning": "<one sentence explaining the dominant factor in your scores>"
}
```

Do not include any text outside the JSON block.
