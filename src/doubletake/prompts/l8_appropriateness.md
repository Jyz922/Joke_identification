# TASK: Two-Axis Appropriateness Assessment (L8)

You are evaluating the developmental appropriateness of a text for children across specified target ages.
Evaluate two independent axes: Content Appropriateness and Inference Appropriateness.

## INPUT
- Text: "{text}"
- Genre: {genre}
- Ambiguous term: "{term}"
- Sense A: {sense_a}
- Sense B: {sense_b}
- Target ages: {target_ages}
- L7 Comprehension statuses: {l7_comprehension}

## AXIS 1: CONTENT APPROPRIATENESS
Assess the surface topic, language, and literal content of the text itself:
- Violence, death, illness, physical injury
- Body functions or gross-out topics
- Sexuality, nudity, romantic/adult relationships
- Substances (alcohol, tobacco, drugs, intoxicants)
- Profanity, obscenity, vulgarity, slurs
- Discrimination, prejudice, harmful stereotypes
- Dark or mature themes

Evaluate whether the topic and language are safe and appropriate for a child of each target age.

## AXIS 2: INFERENCE APPROPRIATENESS
Assess the background knowledge, reasoning, and world experience required to reach the alternative meaning:
- Adult life experience (workplace politics, marriage/divorce, debt, bureaucracy)
- Political, civic, historical, or social symbolism
- Specialized professional knowledge (finance, legal, advanced medical, corporate)
- Overly abstract metaphorical reasoning
- Experiences or cultural associations outside typical childhood life

Evaluate whether a child of each target age can reasonably be expected to possess the life experience and reasoning required to get the point of the joke.

## DECISION RULES FOR EACH TARGET AGE
Combine Content, Inference, and L7 Comprehension:
1. "CONTENT_NOT_APPROPRIATE": The content or language itself is inappropriate or unsafe for this age.
2. "CONTENT_OK_INFERENCE_TOO_ADVANCED": The content is clean, but the required background knowledge, symbolism, or metalinguistic reasoning is outside childhood experience.
3. "VOCABULARY_TOO_ADVANCED": Content and inference are suitable, but the child has not yet acquired the required vocabulary (L7 comprehension is PARTIALLY_COMPREHENSIBLE, SENSE_B_TOO_ADVANCED, or AOA_UNKNOWN).
4. "FULLY_AGE_APPROPRIATE": Content is safe, inference is accessible, and vocabulary is fully understood (L7 comprehension is FULLY_COMPREHENSIBLE).

## OUTPUT FORMAT
Respond with a JSON object strictly matching this schema:
```json
{
  "content_appropriate": {
    "6": true,
    "8": true
  },
  "inference_appropriate": {
    "6": false,
    "8": true
  },
  "per_age_verdict": {
    "6": "CONTENT_OK_INFERENCE_TOO_ADVANCED",
    "8": "FULLY_AGE_APPROPRIATE"
  },
  "content_issues": [],
  "inference_issues": [],
  "explanation": "<1-2 sentence justification>"
}
```
