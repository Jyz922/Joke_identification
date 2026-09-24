# TASK: Sense Distinctness and Lexical Granularity Check (L6)

You are evaluating lexical ambiguity in a text to verify whether two claimed meanings
of an ambiguous term are genuinely distinct conceptual interpretations or merely fine-grained,
subtle nuances of the same underlying sense.

Lexical resources (such as WordNet) often list closely related nuances as separate synsets/senses.
L6 determines whether the two senses active in the text represent genuinely distinct readings
that can sustain a double-take or pun.

## INPUT
- Text: "{text}"
- Genre: {genre}
- Ambiguous term: "{term}"
- Sense A description: {sense_a}
  Sense A context anchor: "{anchor_a}"
- Sense B description: {sense_b}
  Sense B context anchor: "{anchor_b}"

## DISTINCTNESS CRITERIA
1. **Paraphrasability**:
   Can Sense A and Sense B receive distinct, concrete paraphrases capturing what each reading means?
   Provide `sense_a_paraphrase` and `sense_b_paraphrase`.

2. **Mutual Suppression**:
   Does adopting the interpretation of Sense A suppress or contradict the interpretation of Sense B,
   and vice versa?
   If one interpretation is held, is the other excluded in normal interpretation?

3. **Material Difference**:
   Do the two interpretations produce materially different mental pictures, real-world situations,
   or communicative meanings?
   - Distinct: "trunk" (elephant's proboscis) vs "trunk" (car storage compartment).
   - Too Close: "run" (sprint on foot) vs "run" (jog for exercise) where the text does not rely on any real semantic contrast.

4. **Ambiguity Ablation (Controlled Rewrite)**:
   Does substituting the paraphrase for Sense A in place of the ambiguous term remove the pun/humor?
   - "SUPPORTED": A single-sense rewrite cleanly removes the ambiguity while remaining grammatical.
   - "UNSUPPORTED": The rewrite fails to eliminate the ambiguity or leaves the double-meaning intact.
   - "SKIPPED": No single-word or short phrase substitution is possible.

## DECISION RULES
- "SENSES_DISTINCT": Sense A and Sense B are conceptually distinct, can be paraphrased separately, and mutually suppress each other in this text.
- "SENSES_TOO_CLOSE": The two senses are mere nuances or overlapping facets of the same basic meaning in this text.
- "L6_SKIPPED_NO_PARAPHRASE": The senses cannot be clearly distinguished or formulated into distinct paraphrases.

## OUTPUT FORMAT
Respond with a JSON object strictly matching this schema:
```json
{
  "sense_a_paraphrase": "<short paraphrase for Sense A>",
  "sense_b_paraphrase": "<short paraphrase for Sense B>",
  "suppresses_other": true,
  "materially_different": true,
  "distinctness_status": "SENSES_DISTINCT",
  "ambiguity_ablation": "SUPPORTED",
  "explanation": "<1-2 sentence justification>"
}
```
