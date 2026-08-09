"""
只跑 RAGAS 评测部分（假设 results.json 已经存在）。
如果没有 results.json 则重新跑 agent。
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
from langchain_openai import OpenAIEmbeddings

RESULTS_PATH = Path("evaluation/results.json")
QUERIES_PATH = Path("evaluation/test_queries.json")


def collect_results():
    from agent.graph import app_graph
    with open(QUERIES_PATH) as f:
        test_cases = json.load(f)

    data = {"question": [], "answer": [], "contexts": [], "query_type": []}
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

    with open(RESULTS_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nSaved to {RESULTS_PATH}")
    return data


def run_ragas(data):
    print("\nRunning RAGAS evaluation...")
    answer_relevancy.embeddings = OpenAIEmbeddings()
    METRICS = [faithfulness, answer_relevancy, LLMContextPrecisionWithoutReference()]

    dataset = Dataset.from_dict({
        "question": data["question"],
        "answer":   data["answer"],
        "contexts": data["contexts"],
    })
    scores = evaluate(dataset, metrics=METRICS)
    print("\n=== Overall Results ===")
    print(scores)

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
        s = evaluate(subset, metrics=METRICS)
        print(f"\n{qtype} ({len(indices)} queries):")
        print(s)

    return scores


if __name__ == "__main__":
    if RESULTS_PATH.exists():
        print(f"Found existing results at {RESULTS_PATH}, skipping agent runs.")
        with open(RESULTS_PATH) as f:
            data = json.load(f)
    else:
        data = collect_results()

    run_ragas(data)
