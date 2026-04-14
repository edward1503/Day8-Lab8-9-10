"""Verify supervisor routing matches expected_route for all 15 test questions."""
import json
from graph import make_initial_state, supervisor_node

with open("data/test_questions.json", encoding="utf-8") as f:
    questions = json.load(f)

pass_count = 0
fail_count = 0

for q in questions:
    state = make_initial_state(q["question"])
    state = supervisor_node(state)

    actual = state["supervisor_route"]
    expected = q["expected_route"]
    ok = "✅" if actual == expected else "❌"

    if actual == expected:
        pass_count += 1
    else:
        fail_count += 1

    print(f"{ok} {q['id']}: expected={expected:<22} actual={actual:<22} | {q['question'][:55]}")
    if actual != expected:
        print(f"   reason: {state['route_reason']}")

print(f"\n{'='*60}")
print(f"Result: {pass_count}/{len(questions)} passed, {fail_count} failed")
