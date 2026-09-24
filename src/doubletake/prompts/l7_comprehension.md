# TASK: Comprehension Assessment (L7)

You are evaluating the developmental psycholinguistic comprehension of a text across target ages.
Given the text, ambiguous term, Sense A, and Sense B, estimate the Age of Acquisition (AoA)
and metalinguistic comprehension floor.

## INPUT
- Text: "{text}"
- Genre: {genre}
- Ambiguous term: "{term}"
- Sense A: {sense_a} (Context anchor: "{anchor_a}")
- Sense B: {sense_b} (Context anchor: "{anchor_b}")
- Target ages: {target_ages}

## EVALUATION DIMENSIONS
1. **Sense A AoA (years)**:
   Estimated age when a native English-speaking child learns the basic vocabulary for Sense A.
2. **Sense B AoA (years)**:
   Estimated age when a child learns the vocabulary or figurative/secondary meaning for Sense B.
3. **Compound/Idiom AoA (years)**:
   If a compound split or idiom is involved, the age when the multiword expression or parts are acquired.
4. **Metalinguistic Floor (years)**:
   The developmental age required to appreciate this specific wordplay mechanism:
   - Homographic pun in simple QA riddle: ~6.0
   - Resegmentation / compound split: ~8.0
   - Dialogue misunderstanding / perspective mismatch: ~7.5
   - Definitional oneliner / abstract pun: ~7.0

## DECISION RULES FOR EACH TARGET AGE
- "FULLY_COMPREHENSIBLE": Target age >= Sense A AoA, Sense B AoA, and Metalinguistic floor.
- "PARTIALLY_COMPREHENSIBLE": Target age >= Sense A AoA, but target age < Sense B AoA.
- "SENSE_B_TOO_ADVANCED": Sense A is known, but Sense B is too advanced.
- "WORDPLAY_SKILL_TOO_ADVANCED": Vocabulary is understood, but target age < Metalinguistic floor.
- "AOA_UNKNOWN": The age of acquisition is unknown or unratable.

## OUTPUT FORMAT
Respond with a JSON object strictly matching this schema:
```json
{
  "sense_a_aoa": 5.0,
  "sense_b_aoa": 8.0,
  "compound_split_aoa": null,
  "metalinguistic_floor": 6.0,
  "per_age_comprehension": {
    "6": "PARTIALLY_COMPREHENSIBLE",
    "8": "FULLY_COMPREHENSIBLE"
  },
  "explanation": "<1-2 sentence justification>"
}
```
