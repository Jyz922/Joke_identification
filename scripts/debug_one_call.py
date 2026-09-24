"""One raw Gemini call for fixture S1 — dump the ENTIRE response before any
of our parsing touches it.

Purpose: diagnose why every live L5 call returns INSUFFICIENT_CONTEXT.
Reproduces the exact GenerateContentConfig the production path builds
(response_schema=_QALLMResponse, temperature=0, max_output_tokens=512),
then prints finish_reason, usage_metadata (incl. thinking/reasoning tokens),
len(response.text or ""), the verbatim response.text, parts, and any
function calls.

Usage:
    py -3.11 scripts/debug_one_call.py [--max-output-tokens N] [--thinking-budget N]

--max-output-tokens  Override the 512 cap (hypothesis: thinking eats the budget).
--thinking-budget    If set, pass ThinkingConfig(thinking_budget=N); 0 disables
                     thinking on models that support it.

Makes exactly ONE paid API call. Requires GEMINI_API_KEY.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import google.genai as genai
import google.genai.types as gtypes

from doubletake.config import DEFAULT_SETTINGS
from doubletake.enums import Genre
from doubletake.l5_resolution import _QALLMResponse, _render_prompt
from doubletake.schema import L4Result

_FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures" / "l5_anchors.jsonl"


def _s1_fixture() -> dict:
    for line in _FIXTURES.read_text(encoding="utf-8").splitlines():
        if line.strip() and json.loads(line)["id"] == "S1":
            return json.loads(line)
    raise SystemExit("S1 fixture not found")


def _build_prompt(fx: dict) -> str:
    return _render_prompt(
        Genre.QA_RIDDLE, fx["text"], fx["ambiguous_term"], L4Result(**fx["l4_result"])
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-output-tokens", type=int,
                    default=DEFAULT_SETTINGS.L5_MAX_OUTPUT_TOKENS)
    ap.add_argument("--thinking-budget", type=int, default=None)
    args = ap.parse_args()

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY not set")

    fx = _s1_fixture()
    prompt = _build_prompt(fx)
    model = DEFAULT_SETTINGS.L5_MODEL_GEMINI

    cfg_kwargs = dict(
        response_mime_type="application/json",
        response_schema=_QALLMResponse,
        temperature=0.0,
        max_output_tokens=args.max_output_tokens,
    )
    if args.thinking_budget is not None:
        cfg_kwargs["thinking_config"] = gtypes.ThinkingConfig(
            thinking_budget=args.thinking_budget
        )
    config = gtypes.GenerateContentConfig(**cfg_kwargs)

    print(f"=== ONE call: model={model} max_output_tokens={args.max_output_tokens} "
          f"thinking_budget={args.thinking_budget} ===\n")

    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model=model, contents=prompt, config=config
    )

    # --- finish_reason ---
    cand = response.candidates[0] if response.candidates else None
    print("finish_reason:", getattr(cand, "finish_reason", "<no candidate>"))
    print("finish_message:", getattr(cand, "finish_message", None))

    # --- usage_metadata (incl. thinking/reasoning tokens) ---
    um = response.usage_metadata
    print("\nusage_metadata:")
    if um is not None:
        print("  prompt_token_count     :", getattr(um, "prompt_token_count", None))
        print("  candidates_token_count :", getattr(um, "candidates_token_count", None))
        print("  thoughts_token_count   :", getattr(um, "thoughts_token_count", None))
        print("  total_token_count      :", getattr(um, "total_token_count", None))
        print("  (full):", um)
    else:
        print("  <None>")

    # --- response.text length + verbatim ---
    try:
        text = response.text
    except Exception as e:  # .text can raise if there are no text parts
        text = None
        print(f"\nresponse.text raised: {type(e).__name__}: {e}")
    print("\nlen(response.text or ''):", len(text or ""))
    print("response.text verbatim:")
    print(repr(text))

    # --- parts + function calls ---
    print("\nparts:")
    parts = getattr(getattr(cand, "content", None), "parts", None) or []
    for i, p in enumerate(parts):
        print(f"  [{i}] text={getattr(p, 'text', None)!r} "
              f"function_call={getattr(p, 'function_call', None)!r} "
              f"thought={getattr(p, 'thought', None)!r}")
    print("function_calls:", getattr(response, "function_calls", None))

    print("\n=== full response object ===")
    print(response)


if __name__ == "__main__":
    main()
