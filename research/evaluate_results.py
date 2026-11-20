"""Summarize actual Attendly Research Evaluation CSV exports or labeled trial CSVs."""
import csv
import sys
from collections import defaultdict
from pathlib import Path


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        if (row.get("trial_type") or "identification").strip().lower() == "verification":
            continue
        # Accept the app's export column names and the original worksheet headings.
        expected = (row.get("expected_identity") or row.get("expected_student_id") or "").strip()
        predicted = (row.get("predicted_identity") or row.get("predicted_student_id") or "").strip()
        latency = row.get("processing_ms")
        if latency in (None, ""):
            try: latency = float(row.get("latency_seconds", "")) * 1000
            except (ValueError, TypeError): latency = None
        condition = (row.get("condition") or "unspecified").strip()
        groups[condition].append((expected, predicted, latency))

    output = []
    ratio = lambda numerator, denominator: numerator / denominator if denominator else None
    for condition, trials in sorted(groups.items()):
        known = [r for r in trials if r[0]]
        unknown = [r for r in trials if not r[0]]
        tp = sum(predicted == expected for expected, predicted, _ in known)
        fn = len(known) - tp  # includes rejection and wrong known identity
        fp = sum(bool(predicted) for _, predicted, _ in unknown)
        tn = len(unknown) - fp
        precision, recall = ratio(tp, tp + fp), ratio(tp, tp + fn)
        f1 = ratio(2 * precision * recall, precision + recall) if precision is not None and recall is not None else None
        times = [float(r[2]) for r in trials if r[2] not in (None, "")]
        output.append({
            "condition": condition, "trials": len(trials), "TP": tp, "TN": tn, "FP": fp, "FN": fn,
            "accuracy": ratio(tp + tn, len(trials)), "precision": precision, "recall": recall, "f1": f1,
            "FAR": ratio(fp, fp + tn), "FRR": ratio(fn, fn + tp),
            "average_ms": sum(times) / len(times) if times else None,
            "minimum_ms": min(times) if times else None, "maximum_ms": max(times) if times else None,
        })
    return output


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python research/evaluate_results.py path/to/trials.csv")
    path = Path(sys.argv[1])
    with path.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise SystemExit("No trial data found. The header-only template contains no measurements.")
    for result in summarize(rows):
        print("\t".join(f"{key}={value if value is not None else 'N/A'}" for key, value in result.items()))
    print("Ratios use the documented identification protocol; verification trials require separate genuine/impostor analysis.")


if __name__ == "__main__":
    main()
