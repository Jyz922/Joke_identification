You are a semantic analysis assistant. Your task is to evaluate whether a QA-format joke achieves genuine semantic resolution through its ambiguous term.

## Task

Assess the joke below on five dimensions. Each dimension score must be a float from 0.0 (absent) to 1.0 (fully present).

**Joke text:**
{text}

**Ambiguous term:** {ambiguous_term}

**Setup sense (the reading the punchline switches away from):** {other_sense}
Anchored at: "{other_sense_anchor_quote}"

**Punchline sense (the reading the punchline resolves to):** {resolving_sense}
Anchored at: "{resolving_sense_anchor_quote}"

**Anchor relation:** {anchor_relation}

## Dimensions to score

1. **polarity_or_direction** — Does the punchline activate a reading of the ambiguous term that contrasts in polarity or direction with the setup's reading? A high score means the two senses pull in meaningfully opposite directions.

2. **answer_relevance** — Does the punchline answer the question in a way that is semantically coherent via the punchline reading of the ambiguous term? A high score means the punchline reading genuinely resolves the question.

3. **causal** — Is there a clear causal or logical chain from the setup condition to the punchline via the ambiguous term? A high score means the causal link is tight and necessary.

4. **agent** — Is the agent or subject of the setup the same entity as in the punchline, and does this sameness enable the double meaning? A high score means agent identity is required for the joke to work.

5. **tense_aspect** — Are the tense and aspect of the setup and punchline compatible with the dual reading? A high score means tense/aspect alignment strengthens the ambiguity rather than undermining it.

## Output format

Return ONLY a JSON object with this exact structure — no prose before or after:

```json
{
  "polarity_or_direction": <float 0.0–1.0>,
  "answer_relevance": <float 0.0–1.0>,
  "causal": <float 0.0–1.0>,
  "agent": <float 0.0–1.0>,
  "tense_aspect": <float 0.0–1.0>,
  "reasoning": "<one sentence explaining the dominant factor in your scores>"
}
```

Do not include any text outside the JSON block.
