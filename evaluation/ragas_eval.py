"""
RAGAS evaluation — reference-free metrics only.
No ground truth answers needed.

Metrics:
- faithfulness:       answer is grounded in retrieved context (no hallucination)
- answer_relevancy:   answer actually addresses the question
- context_precision:  retrieved context is relevant to the question

Usage:
    python evaluation/ragas_eval.py
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, LLMContextPrecisionWithoutReference
from agent.graph import app_graph


def run_evaluation(queries_path: str = "evaluation/test_queries.json"):
    with open(queries_path) as f:
        test_cases = json.load(f)

    data = {
        "question":  [],
        "answer":    [],
        "contexts":  [],
        "query_type": [],
    }

    print(f"Running {len(test_cases)} queries...\n")

    for i, case in enumerate(test_cases):
        q = case["question"]
        print(f"[{i+1}/{len(test_cases)}] {q[:60]}...")

        try:
            result = app_graph.invoke({"question": q})
            answer = result.get("final_answer", "")
            contexts = [
                d["text"]
                for sq in result.get("sub_questions", [])
                for d in sq.get("vector_docs", [])
            ]
            # Also include SQL results as context strings
            for sq in result.get("sub_questions", []):
                for r in sq.get("sql_results", []):
                    contexts.append(str(r["data"]))

            data["question"].append(q)
            data["answer"].append(answer)
            data["contexts"].append(contexts if contexts else ["No context retrieved"])
            data["query_type"].append(case.get("type", "unknown"))

        except Exception as e:
            print(f"  ERROR: {e}")
            data["question"].append(q)
            data["answer"].append("")
            data["contexts"].append(["Error"])
            data["query_type"].append(case.get("type", "unknown"))

    print("\nRunning RAGAS evaluation...")
    dataset = Dataset.from_dict({
        "question": data["question"],
        "answer":   data["answer"],
        "contexts": data["contexts"],
    })

    scores = evaluate(dataset, metrics=[faithfulness, answer_relevancy, LLMContextPrecisionWithoutReference])
    print("\n=== Results ===")
    print(scores)

    # Break down by query type
    print("\n=== By query type ===")
    for qtype in ["simple", "multihop", "cross_document"]:
        indices = [i for i, t in enumerate(data["query_type"]) if t == qtype]
        if not indices:
            continue
        subset = Dataset.from_dict({
            "question": [data["question"][i] for i in indices],
            "answer":   [data["answer"][i]   for i in indices],
            "contexts": [data["contexts"][i] for i in indices],
        })
        s = evaluate(subset, metrics=[faithfulness, answer_relevancy, LLMContextPrecisionWithoutReference])
        print(f"\n{qtype} ({len(indices)} queries):")
        print(s)

    return scores


if __name__ == "__main__":
    run_evaluation()
