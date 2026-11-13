# pipelines/eval_retrieval.py
"""
Comprehensive Retrieval Evaluation System
- Standard IR metrics (Recall, Precision, MRR, MAP, nDCG)
- Statistical significance testing
- Per-query analysis
- Error analysis
- Comparative evaluation
- Visualization
"""

import os
import argparse
import json
from dataclasses import dataclass, asdict
from collections import defaultdict
from scipy import stats
import math

from mahoun.pipelines._logging import setup_logger

log = setup_logger("eval-retr")


@dataclass
class QueryMetrics:
    """Metrics for a single query"""

    query_id: str
    recall_at_k: float
    precision_at_k: float
    mrr: float
    ap: float  # Average Precision
    ndcg_at_k: float
    num_relevant: int
    num_retrieved: int
    num_relevant_retrieved: int


@dataclass
class AggregateMetrics:
    """Aggregate metrics across all queries"""

    num_queries: int
    recall_at_k: float
    precision_at_k: float
    mrr: float
    map_score: float  # Mean Average Precision
    ndcg_at_k: float

    # Additional stats
    recall_std: float
    precision_std: float
    mrr_std: float

    # Coverage
    queries_with_results: int
    queries_without_results: int
    avg_results_per_query: float


class RetrievalEvaluator:
    """Comprehensive retrieval evaluation"""

    @staticmethod
    def recall_at_k(relevant: List[str], retrieved: List[str], k: int) -> float:
        """Recall@k: fraction of relevant docs retrieved in top-k"""
        if not relevant:
            return 0.0

        retrieved_k = set(retrieved[:k])
        relevant_set = set(relevant)

        hits = len(retrieved_k & relevant_set)
        return hits / len(relevant_set)

    @staticmethod
    def precision_at_k(relevant: List[str], retrieved: List[str], k: int) -> float:
        """Precision@k: fraction of retrieved docs that are relevant"""
        if not retrieved[:k]:
            return 0.0

        retrieved_k = set(retrieved[:k])
        relevant_set = set(relevant)

        hits = len(retrieved_k & relevant_set)
        return hits / len(retrieved_k)

    @staticmethod
    def reciprocal_rank(relevant: List[str], retrieved: List[str]) -> float:
        """Reciprocal Rank: 1/rank of first relevant doc"""
        relevant_set = set(relevant)

        for i, doc_id in enumerate(retrieved, 1):
            if doc_id in relevant_set:
                return 1.0 / i

        return 0.0

    @staticmethod
    def average_precision(relevant: List[str], retrieved: List[str]) -> float:
        """Average Precision: mean of precision at each relevant doc position"""
        if not relevant:
            return 0.0

        relevant_set = set(relevant)
        precisions = []
        num_relevant_seen = 0

        for i, doc_id in enumerate(retrieved, 1):
            if doc_id in relevant_set:
                num_relevant_seen += 1
                precision_at_i = num_relevant_seen / i
                precisions.append(precision_at_i)

        if not precisions:
            return 0.0

        return sum(precisions) / len(relevant_set)

    @staticmethod
    def dcg_at_k(
        relevant: List[str], retrieved: List[str], k: int, relevance_scores: Dict[str, float] = None
    ) -> float:
        """Discounted Cumulative Gain@k"""
        dcg = 0.0
        relevant_set = set(relevant)

        for i, doc_id in enumerate(retrieved[:k], 1):
            if doc_id in relevant_set:
                # Binary relevance or graded relevance
                rel = relevance_scores.get(doc_id, 1.0) if relevance_scores else 1.0
                dcg += rel / math.log2(i + 1)

        return dcg

    @staticmethod
    def ndcg_at_k(
        relevant: List[str], retrieved: List[str], k: int, relevance_scores: Dict[str, float] = None
    ) -> float:
        """Normalized Discounted Cumulative Gain@k"""
        # Actual DCG
        dcg = RetrievalEvaluator.dcg_at_k(relevant, retrieved, k, relevance_scores)

        # Ideal DCG (best possible ranking)
        if relevance_scores:
            # Sort by relevance scores
            ideal_ranking = sorted(
                relevant, key=lambda x: relevance_scores.get(x, 1.0), reverse=True
            )
        else:
            ideal_ranking = relevant

        idcg = RetrievalEvaluator.dcg_at_k(relevant, ideal_ranking, k, relevance_scores)

        if idcg == 0:
            return 0.0

        return dcg / idcg

    @staticmethod
    def evaluate_query(
        query_id: str,
        relevant: List[str],
        retrieved: List[str],
        k: int = 5,
        relevance_scores: Dict[str, float] = None,
    ) -> QueryMetrics:
        """Evaluate a single query"""

        return QueryMetrics(
            query_id=query_id,
            recall_at_k=RetrievalEvaluator.recall_at_k(relevant, retrieved, k),
            precision_at_k=RetrievalEvaluator.precision_at_k(relevant, retrieved, k),
            mrr=RetrievalEvaluator.reciprocal_rank(relevant, retrieved),
            ap=RetrievalEvaluator.average_precision(relevant, retrieved),
            ndcg_at_k=RetrievalEvaluator.ndcg_at_k(relevant, retrieved, k, relevance_scores),
            num_relevant=len(relevant),
            num_retrieved=len(retrieved),
            num_relevant_retrieved=len(set(relevant) & set(retrieved[:k])),
        )

    @staticmethod
    def aggregate_metrics(query_metrics: List[QueryMetrics]) -> AggregateMetrics:
        """Aggregate metrics across queries"""

        if not query_metrics:
            return AggregateMetrics(
                num_queries=0,
                recall_at_k=0,
                precision_at_k=0,
                mrr=0,
                map_score=0,
                ndcg_at_k=0,
                recall_std=0,
                precision_std=0,
                mrr_std=0,
                queries_with_results=0,
                queries_without_results=0,
                avg_results_per_query=0,
            )

        recalls = [m.recall_at_k for m in query_metrics]
        precisions = [m.precision_at_k for m in query_metrics]
        mrrs = [m.mrr for m in query_metrics]
        aps = [m.ap for m in query_metrics]
        ndcgs = [m.ndcg_at_k for m in query_metrics]

        queries_with_results = sum(1 for m in query_metrics if m.num_retrieved > 0)
        queries_without_results = len(query_metrics) - queries_with_results

        return AggregateMetrics(
            num_queries=len(query_metrics),
            recall_at_k=np.mean(recalls),
            precision_at_k=np.mean(precisions),
            mrr=np.mean(mrrs),
            map_score=np.mean(aps),
            ndcg_at_k=np.mean(ndcgs),
            recall_std=np.std(recalls),
            precision_std=np.std(precisions),
            mrr_std=np.std(mrrs),
            queries_with_results=queries_with_results,
            queries_without_results=queries_without_results,
            avg_results_per_query=np.mean([m.num_retrieved for m in query_metrics]),
        )


class StatisticalTester:
    """Statistical significance testing"""

    @staticmethod
    def paired_t_test(
        metrics1: List[QueryMetrics], metrics2: List[QueryMetrics], metric_name: str = "recall_at_k"
    ) -> Tuple[float, float]:
        """
        Paired t-test between two systems
        Returns: (t_statistic, p_value)
        """
        values1 = [getattr(m, metric_name) for m in metrics1]
        values2 = [getattr(m, metric_name) for m in metrics2]

        t_stat, p_value = stats.ttest_rel(values1, values2)
        return t_stat, p_value

    @staticmethod
    def wilcoxon_test(
        metrics1: List[QueryMetrics], metrics2: List[QueryMetrics], metric_name: str = "recall_at_k"
    ) -> Tuple[float, float]:
        """
        Wilcoxon signed-rank test (non-parametric)
        Returns: (statistic, p_value)
        """
        values1 = [getattr(m, metric_name) for m in metrics1]
        values2 = [getattr(m, metric_name) for m in metrics2]

        stat, p_value = stats.wilcoxon(values1, values2)
        return stat, p_value


class ErrorAnalyzer:
    """Analyze retrieval errors"""

    @staticmethod
    def analyze_failures(
        qrels: Dict[str, List[str]], runs: Dict[str, List[str]], k: int = 5
    ) -> Dict:
        """Analyze queries with poor performance"""

        failures = {"zero_recall": [], "low_precision": [], "no_results": []}

        for query_id, relevant in qrels.items():
            retrieved = runs.get(query_id, [])

            if not retrieved:
                failures["no_results"].append(query_id)
                continue

            recall = RetrievalEvaluator.recall_at_k(relevant, retrieved, k)
            precision = RetrievalEvaluator.precision_at_k(relevant, retrieved, k)

            if recall == 0:
                failures["zero_recall"].append(query_id)

            if precision < 0.2:  # Less than 20% precision
                failures["low_precision"].append(query_id)

        return failures

    @staticmethod
    def find_hard_queries(query_metrics: List[QueryMetrics], threshold: float = 0.3) -> List[str]:
        """Find queries with low performance"""

        hard_queries = []
        for m in query_metrics:
            if m.recall_at_k < threshold:
                hard_queries.append(m.query_id)

        return hard_queries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qrels", required=True, help='{"query": ["doc1", "doc2"], ...}')
    ap.add_argument("--runs", required=True, help='{"query": ["doc1", "doc2"], ...}')
    ap.add_argument("--k", type=int, default=5, help="Cutoff for metrics")
    ap.add_argument("--baseline_runs", help="Baseline runs for comparison")
    ap.add_argument("--output", help="Save detailed results to JSON")
    ap.add_argument("--error_analysis", action="store_true", help="Perform error analysis")
    ap.add_argument("--wandb", action="store_true", help="Enable W&B logging")
    args = ap.parse_args()

    # W&B init
    if args.wandb:
        import wandb

        wandb.init(
            project=os.getenv("WANDB_PROJECT", "mahoun"),
            name="eval_retrieval",
            reinit=True,
            config={"k": args.k},
        )

    # Load data
    log.info("Loading qrels and runs...")
    qrels = json.load(open(args.qrels, "r", encoding="utf-8"))
    runs = json.load(open(args.runs, "r", encoding="utf-8"))

    # Evaluate each query
    query_metrics = []
    for query_id, relevant in qrels.items():
        retrieved = runs.get(query_id, [])

        metrics = RetrievalEvaluator.evaluate_query(query_id, relevant, retrieved, k=args.k)
        query_metrics.append(metrics)

    # Aggregate
    agg_metrics = RetrievalEvaluator.aggregate_metrics(query_metrics)

    # Display results
    print("\n" + "=" * 80)
    print("📊 RETRIEVAL EVALUATION RESULTS")
    print("=" * 80)
    print(f"\n📈 Aggregate Metrics (k={args.k}):")
    print(f"   Recall@{args.k}:    {agg_metrics.recall_at_k:.4f} ± {agg_metrics.recall_std:.4f}")
    print(
        f"   Precision@{args.k}: {agg_metrics.precision_at_k:.4f} ± {agg_metrics.precision_std:.4f}"
    )
    print(f"   MRR:          {agg_metrics.mrr:.4f} ± {agg_metrics.mrr_std:.4f}")
    print(f"   MAP:          {agg_metrics.map_score:.4f}")
    print(f"   nDCG@{args.k}:      {agg_metrics.ndcg_at_k:.4f}")

    print(f"\n📋 Coverage:")
    print(f"   Total queries:        {agg_metrics.num_queries}")
    print(f"   With results:         {agg_metrics.queries_with_results}")
    print(f"   Without results:      {agg_metrics.queries_without_results}")
    print(f"   Avg results/query:    {agg_metrics.avg_results_per_query:.1f}")

    # Error analysis
    if args.error_analysis:
        print(f"\n🔍 Error Analysis:")
        failures = ErrorAnalyzer.analyze_failures(qrels, runs, k=args.k)
        print(f"   Zero recall queries:  {len(failures['zero_recall'])}")
        print(f"   Low precision queries: {len(failures['low_precision'])}")
        print(f"   No results queries:   {len(failures['no_results'])}")

        hard_queries = ErrorAnalyzer.find_hard_queries(query_metrics, threshold=0.3)
        print(f"   Hard queries (R<0.3): {len(hard_queries)}")

    # Baseline comparison
    if args.baseline_runs:
        log.info("Comparing with baseline...")
        baseline_runs = json.load(open(args.baseline_runs, "r", encoding="utf-8"))

        baseline_metrics = []
        for query_id, relevant in qrels.items():
            retrieved = baseline_runs.get(query_id, [])
            metrics = RetrievalEvaluator.evaluate_query(query_id, relevant, retrieved, k=args.k)
            baseline_metrics.append(metrics)

        baseline_agg = RetrievalEvaluator.aggregate_metrics(baseline_metrics)

        print(f"\n📊 Comparison with Baseline:")
        print(
            f"   Recall@{args.k}:    {agg_metrics.recall_at_k:.4f} vs {baseline_agg.recall_at_k:.4f} "
            f"({(agg_metrics.recall_at_k - baseline_agg.recall_at_k)*100:+.1f}%)"
        )
        print(
            f"   Precision@{args.k}: {agg_metrics.precision_at_k:.4f} vs {baseline_agg.precision_at_k:.4f} "
            f"({(agg_metrics.precision_at_k - baseline_agg.precision_at_k)*100:+.1f}%)"
        )
        print(
            f"   MRR:          {agg_metrics.mrr:.4f} vs {baseline_agg.mrr:.4f} "
            f"({(agg_metrics.mrr - baseline_agg.mrr)*100:+.1f}%)"
        )

        # Statistical significance
        t_stat, p_value = StatisticalTester.paired_t_test(
            query_metrics, baseline_metrics, "recall_at_k"
        )
        print(f"\n📈 Statistical Significance (Recall@{args.k}):")
        print(f"   t-statistic: {t_stat:.4f}")
        print(f"   p-value:     {p_value:.4f}")
        print(f"   Significant: {'Yes' if p_value < 0.05 else 'No'} (α=0.05)")

    print("=" * 80 + "\n")

    # Save detailed results
    if args.output:
        results = {
            "aggregate_metrics": asdict(agg_metrics),
            "per_query_metrics": [asdict(m) for m in query_metrics],
            "config": {"k": args.k},
        }

        if args.error_analysis:
            results["error_analysis"] = failures
            results["hard_queries"] = hard_queries

        if args.baseline_runs:
            results["baseline_comparison"] = {
                "baseline_metrics": asdict(baseline_agg),
                "t_test": {"t_statistic": float(t_stat), "p_value": float(p_value)},
            }

        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        log.info(f"Detailed results saved to {args.output}")

    # W&B logging
    if args.wandb:
        # Log aggregate metrics
        wandb.log(
            {
                f"recall@{args.k}": agg_metrics.recall_at_k,
                f"precision@{args.k}": agg_metrics.precision_at_k,
                "mrr": agg_metrics.mrr,
                "map": agg_metrics.map_score,
                f"ndcg@{args.k}": agg_metrics.ndcg_at_k,
                "num_queries": agg_metrics.num_queries,
                "queries_with_results": agg_metrics.queries_with_results,
                "avg_results_per_query": agg_metrics.avg_results_per_query,
            }
        )

        # Per-query metrics table
        table = wandb.Table(
            columns=["Query", "Recall", "Precision", "MRR", "AP", "nDCG"],
            data=[
                [m.query_id, m.recall_at_k, m.precision_at_k, m.mrr, m.ap, m.ndcg_at_k]
                for m in query_metrics[:100]
            ],  # Limit to 100
        )
        wandb.log({"per_query_metrics": table})

        # Distribution plots
        wandb.log(
            {
                "recall_distribution": wandb.Histogram([m.recall_at_k for m in query_metrics]),
                "precision_distribution": wandb.Histogram(
                    [m.precision_at_k for m in query_metrics]
                ),
                "mrr_distribution": wandb.Histogram([m.mrr for m in query_metrics]),
            }
        )

        # Baseline comparison
        if args.baseline_runs:
            wandb.log(
                {
                    "baseline_recall_diff": agg_metrics.recall_at_k - baseline_agg.recall_at_k,
                    "baseline_precision_diff": agg_metrics.precision_at_k
                    - baseline_agg.precision_at_k,
                    "baseline_mrr_diff": agg_metrics.mrr - baseline_agg.mrr,
                    "significance_p_value": p_value,
                }
            )

        wandb.finish()


if __name__ == "__main__":
    main()
