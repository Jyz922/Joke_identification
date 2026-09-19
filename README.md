# DoubleTake: Age-Aware Homograph Humor Detector

DoubleTake analyzes a short English text and a target age to determine whether the text uses homographic ambiguity to create humor. The system explains the relevant meanings, identifies how each meaning is supported by the text, evaluates whether the joke structure resolves correctly, and reports whether the joke is understandable and appropriate for the target age.

The project supports two lexical mechanisms:

- **Homographic wordplay**: one spelling with two distinct meanings, such as `trunk` (an elephant's nose / a storage container) or `guts` (internal organs / courage).
- **Compound-split wordplay**: a word can be resegmented into meaningful parts, such as `autobiography` becoming `auto + biography`.

The project does not classify heterographic homophones, rhymes, or purely nonsensical jokes as homograph humor.

## Inputs and Outputs

### Input

Each request contains:

- `text`: a short joke, riddle, dialogue, one-liner, or ordinary sentence
- `target_age`: the age of the intended reader

Example:

```text
Text: Why don't skeletons fight? Because they have no guts.
Target age: 8
```

### Output

The system returns:

- a classification label
- the text form detected
- the ambiguous word, phrase, or compound split
- two meanings and their supporting text spans
- an explanation of how the meanings create humor
- a comprehension assessment for the target age
- separate content and inference appropriateness assessments
- a confidence score and intermediate diagnostic statuses

Example summary:

```text
Classification: VALID_HOMOGRAPH_JOKE
Genre: QA_RIDDLE
Ambiguous term: guts
Sense A: internal organs
Sense B: courage
Resolution: "no guts" means lacking courage, which explains why the
skeletons do not fight.
Age verdict: FULLY_AGE_APPROPRIATE for age 8
```

## Pipeline Overview

```text
text + target age
        |
        v
L0  Scope declaration
L1  Surface analysis and genre routing
L2  Sense retrieval
L3  Candidate ranking
L4  Sense anchoring
L5  Form-specific semantic resolution
L6  Sense-distinctness check
L7  Comprehension assessment
L8  Two-axis appropriateness assessment
        |
        v
structured explanation and final verdict
```

## L0: Scope Declaration

L0 determines whether the text belongs to the project scope.

Accepted mechanisms:

- homographic ambiguity
- idiomatic expressions containing a homographic term
- approved compound splits or resegmentations

Excluded mechanisms:

- heterographic homophones, such as `knight` / `night`
- rhyming jokes
- jokes based only on absurd situations
- jokes based only on cultural reference, sarcasm, or social context

Recommended output values:

```text
HOMOGRAPH
COMPOUND_SPLIT
OUT_OF_SCOPE_HOMOPHONE
OUT_OF_SCOPE_NONLEXICAL_JOKE
NO_SCOPE_MECHANISM
```

## L1: Surface Analysis and Genre Routing

L1 performs deterministic text analysis:

- tokenization
- lemmatization
- part-of-speech tagging
- dependency parsing
- multiword-expression and idiom scanning
- compound-split detection
- speaker-turn detection
- question, negation, and answer-marker detection

The system then routes the item to the appropriate semantic-resolution branch.

| Genre | Typical signals | Example |
|---|---|---|
| `QA_RIDDLE` | `Why`, `What`, question marks, `Because` | Why don't skeletons fight? Because they have no guts. |
| `DEFINITIONAL_ONELINER` | `X: when...`, `X is...` | Autobiography: when your car starts telling you about its life. |
| `DIALOGUE_MISUNDERSTANDING` | speaker names, quotations, alternating turns | The shingles / aluminum siding dialogue. |
| `DECLARATIVE` | ordinary factual statement | The elephant used its trunk to pick up leaves. |

Genre routing selects the L5 test. It does not itself decide whether a text is funny.

## L2: Sense Retrieval

For each content word, phrase, idiom, or detected compound split, retrieve lexical information from structured resources.

Recommended resources:

- WordNet for sense inventories and glosses
- SemCor or another sense-tagged corpus for sense-frequency estimates
- an age-of-acquisition (AoA) dataset for word-level estimates
- sense-specific AoA data where available
- an idiom or multiword-expression lexicon

Store the following for each sense:

```text
candidate term
lemma
part of speech
sense identifier
definition
example sentence
sense frequency
AoA estimate
source
```

For example:

```text
Term: guts
Sense A: internal organs
Sense B: courage, as in "have guts"
```

## L3: Candidate Ranking

L3 ranks possible ambiguity sites before sending the strongest candidates for semantic analysis.

A useful candidate score combines:

```text
dictionary validity
+ semantic distance between senses
+ evidence of separate contextual triggers
+ separation between setup and answer, or between dialogue turns
+ target-age familiarity
+ frequency plausibility
```

Sense frequency is one feature, not the decision rule. The objective is to rank meanings that are both lexically real and contextually plausible.

## L4: Sense Anchoring

L4 establishes evidence that two meanings are active in the text. This stage can use an LLM with a strict structured-output schema.

For a standard homograph, each meaning must be linked to quoted evidence from the text.

```text
Text: Why do elephants have a trunk?
      Because they don't have pockets to put stuff in.

Sense A: trunk = an elephant's long nose
Anchor A: "elephants"

Sense B: trunk = a storage container
Anchor B: "pockets to put stuff in"
```

For compound-split wordplay, the same character span can support both readings when the morphological parses differ.

```text
Term: autobiography
Parse A: autobiography
Parse B: auto + biography
```

For dialogue, the two anchors may occur in different speakers' utterances or in a speaker's action.

```text
Patient's intended sense: shingles = illness
Responding action: aluminum siding, supporting shingles = roofing material
```

Suggested schema:

```text
sense_a
sense_a_anchor_quote
sense_b
sense_b_anchor_quote
anchor_relation = separate_contexts | resegmentation | speaker_mismatch
anchoring_status = PASS | FAIL
```

If the system can support only one meaning in context, it returns `ONE_SENSE_ONLY`.

## L5: Form-Specific Semantic Resolution

L5 checks whether the two anchored meanings complete the humor structure. The test depends on genre.

### L5-QA: Question-and-Answer Resolution

For riddles and question-answer jokes, evaluate whether the second meaning gives an answer compatible with the question as phrased.

Return separate scores and reasons for:

```text
answer_relevance
polarity_fit
event_direction_fit
causal_fit
agent_fit
tense_aspect_fit
```

Use a weighted resolution score. Polarity and event direction receive the largest weight because they identify the key contrast in minimal pairs.

```text
resolution_score =
  0.45 * polarity_or_direction_fit
+ 0.25 * answer_relevance
+ 0.15 * causal_fit
+ 0.10 * agent_fit
+ 0.05 * tense_aspect_fit
```

Example:

| Text | Inference from "no guts" | Result |
|---|---|---|
| Why don't skeletons fight? Because they have no guts. | Lack of courage makes fighting less likely. | `RESOLUTION_PASS` |
| Why do skeletons fight? Because they have no guts. | Lack of courage makes fighting less likely. | `RESOLUTION_FAIL` |

### L5-OneLiner: Definitional and Single-Line Resolution

For a definition-style one-liner, check whether:

1. Sense A is the conventional reading of the word or phrase.
2. Sense B is a legitimate alternative interpretation or resegmentation.
3. Sense B produces a coherent reading of the same text.
4. The two readings are incongruous in a way that creates the wordplay.

Example:

```text
Autobiography: when your car starts telling you about its life.

Conventional reading: a person's account of their own life
Alternative reading: auto + biography, a car's life story
```

### L5-Dialogue: Speaker-Mismatch Resolution

For dialogue jokes, identify:

1. the meaning intended by one speaker;
2. the different meaning adopted by the responding speaker;
3. the reply or action that is coherent only under the second meaning.

In the shingles example, aluminum siding is coherent only if `shingles` means roofing material, not a viral rash. The meaning mismatch completes the joke.

L5 returns one of:

```text
RESOLUTION_PASS
RESOLUTION_FAIL
INSUFFICIENT_CONTEXT
```

## L6: Sense-Distinctness and Lexical Granularity Check

Lexical resources may list closely related readings as separate senses. L6 confirms that the two selected meanings are meaningfully different for this text.

The test asks:

- Can Sense A and Sense B receive different paraphrases?
- Does the paraphrase for Sense A suppress the interpretation of Sense B?
- Does the paraphrase for Sense B suppress the interpretation of Sense A?
- Do the two interpretations produce materially different readings of the item?

Example:

```text
trunk
Sense A paraphrase: elephant's long nose
Sense B paraphrase: storage chest
Result: SENSES_DISTINCT
```

Possible results:

```text
SENSES_DISTINCT
SENSES_TOO_CLOSE
L6_SKIPPED_NO_PARAPHRASE
```

`L6_SKIPPED_NO_PARAPHRASE` is an explicit status. It lowers confidence but does not automatically reject an item.

An optional ambiguity-ablation field may be collected for analysis:

```text
ambiguity_ablation = SUPPORTED | UNSUPPORTED | SKIPPED
```

This field records whether a controlled single-sense rewrite removes the ambiguity. It is useful evidence, but it is not the primary humor decision.

## L7: Comprehension Assessment

L7 estimates whether a person of the target age can understand the item.

Evaluate separately:

```text
Sense A AoA
Sense B AoA
Idiom or compound-split AoA
Metalinguistic floor
```

The metalinguistic floor represents the ability to understand that:

- one spelling can have multiple meanings;
- speakers may misunderstand a word;
- a word can be resegmented into smaller meaningful units;
- literal and idiomatic meanings can switch.

Possible results:

```text
FULLY_COMPREHENSIBLE
PARTIALLY_COMPREHENSIBLE
SENSE_B_TOO_ADVANCED
WORDPLAY_SKILL_TOO_ADVANCED
AOA_UNKNOWN
```

## L8: Two-Axis Appropriateness Assessment

Appropriateness has two independent dimensions.

### Content Appropriateness

Assess the topic and language of the text itself, including:

- violence
- death
- illness
- body functions
- sexuality
- substances
- profanity
- discrimination
- adult themes

### Inference Appropriateness

Assess the knowledge or reasoning required to reach the alternative meaning. This includes:

- adult knowledge
- political or social symbolism
- financial, legal, medical, or professional knowledge
- overly abstract metaphorical reasoning
- associations outside typical childhood experience

The final age verdict combines L7 and both L8 dimensions:

```text
FULLY_AGE_APPROPRIATE
CONTENT_OK_INFERENCE_TOO_ADVANCED
VOCABULARY_TOO_ADVANCED
CONTENT_NOT_APPROPRIATE
```

## Final Labels

The main classification and the age assessment remain separate.

### Main Classification

```text
VALID_HOMOGRAPH_JOKE
VALID_COMPOUND_SPLIT_JOKE

NO_AMBIGUITY_FOUND
ONE_SENSE_ONLY
ANCHORING_FAIL
RESOLUTION_FAIL
SENSES_TOO_CLOSE

OUT_OF_SCOPE_HOMOPHONE
OUT_OF_SCOPE_NONLEXICAL_JOKE
```

### Age and Appropriateness Labels

```text
FULLY_COMPREHENSIBLE
PARTIALLY_COMPREHENSIBLE
SENSE_B_TOO_ADVANCED
WORDPLAY_SKILL_TOO_ADVANCED
AOA_UNKNOWN

FULLY_AGE_APPROPRIATE
CONTENT_OK_INFERENCE_TOO_ADVANCED
VOCABULARY_TOO_ADVANCED
CONTENT_NOT_APPROPRIATE
```

## Recommended Corpus Format

Use JSON Lines as the canonical corpus format. Keep the system input separate from the gold annotations.

```text
corpus/
  joke_corpus_blind.jsonl
  joke_corpus_gold.jsonl
  annotation_guidelines.md
  results.csv
```

`joke_corpus_blind.jsonl` contains only the data available to the system:

```json
{"id":"J01","text":"Why don't skeletons fight? Because they have no guts.","target_ages":[6,8,10]}
```

`joke_corpus_gold.jsonl` contains the human annotations used for evaluation:

```json
{"id":"J01","gold_label":"VALID_HOMOGRAPH_JOKE","genre":"QA_RIDDLE","ambiguous_term":"guts","sense_a":"internal organs","sense_b":"courage","expected_age_verdict":{"6":"PARTIALLY_COMPREHENSIBLE","8":"FULLY_AGE_APPROPRIATE"}}
```

Recommended corpus composition:

| Group | Count | Purpose |
|---|---:|---|
| Valid homograph or compound-split jokes | 20–25 | Positive examples |
| De-joked rewrites of those items | 20–25 | Closely matched negative controls |
| Ordinary non-joke texts | 10 | Negative examples with realistic vocabulary |
| Total | 50–60 | Assignment corpus |

## Evaluation

Evaluate the project at several levels.

| Task | Metric |
|---|---|
| Joke classification | Precision, recall, F1, confusion matrix |
| Scope handling | Accuracy for homograph vs. homophone exclusions |
| Ambiguity localization | Exact-match accuracy for the ambiguous term |
| Sense anchoring | Human-rated anchor correctness |
| Resolution | Accuracy on Q&A minimal pairs and other genre-specific cases |
| Comprehension | Agreement with human age annotations |
| Appropriateness | Agreement for content and inference dimensions separately |
| Explanations | Human rating for clarity and faithfulness |

The result report should include a breakdown by final status, for example:

```text
VALID_HOMOGRAPH_JOKE: 18
VALID_COMPOUND_SPLIT_JOKE: 3
ONE_SENSE_ONLY: 20
RESOLUTION_FAIL: 4
OUT_OF_SCOPE_HOMOPHONE: 3
SENSE_B_TOO_ADVANCED: 2
```

## End-to-End Example

Input:

```text
Why do elephants have a trunk?
Because they don't have pockets to put stuff in.
Target age: 8
```

Expected analysis:

```text
Scope: HOMOGRAPH
Genre: QA_RIDDLE

Candidate:
trunk

Sense A:
an elephant's long nose
Anchor: "elephants"

Sense B:
a storage container
Anchor: "pockets to put stuff in"

QA resolution:
The answer treats the elephant's trunk as if it were a container for carrying items.
Resolution: PASS

Sense distinctness:
PASS

Comprehension for age 8:
Likely understandable, depending on familiarity with the container sense of trunk.

Content appropriateness:
Appropriate

Inference appropriateness:
Appropriate

Final classification:
VALID_HOMOGRAPH_JOKE
```

Contrast this with:

```text
The elephant used its trunk to pick up leaves.
```

The word `trunk` is lexically ambiguous, but only the elephant-nose sense is supported by the text. The correct result is:

```text
Classification: ONE_SENSE_ONLY
```
