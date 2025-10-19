"""
Evaluation script for cart normalization performance.
Runs test scenarios and generates metrics and reports.
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from typing import Dict, List

from cart_engine import CartEvaluator, CartNormalizer
from menu_data import get_menu
from test_scenarios import TestScenario, get_all_scenarios, get_scenarios_by_menu


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EvaluationReport:
    """Stores evaluation results and generates reports."""
    
    def __init__(self):
        self.results: List[Dict] = []
        self.summary: Dict = {}
    
    def add_result(self, scenario: TestScenario, actual_cart, metrics: Dict):
        """Add a result for a scenario."""
        self.results.append({
            "scenario_id": scenario.id,
            "description": scenario.description,
            "menu": scenario.menu,
            "input_text": scenario.input_text,
            "expected": scenario.expected_cart.to_dict(),
            "actual": actual_cart.to_dict(),
            "metrics": metrics
        })
    
    def calculate_summary(self):
        """Calculate summary statistics."""
        total = len(self.results)
        exact_matches = sum(1 for r in self.results if r["metrics"]["exact_match"])
        
        f1_scores = [r["metrics"]["f1"] for r in self.results]
        item_accuracies = [r["metrics"]["item_accuracy"] for r in self.results]
        
        small_menu_results = [r for r in self.results if r["menu"] == "small"]
        large_menu_results = [r for r in self.results if r["menu"] == "large"]
        
        self.summary = {
            "total_scenarios": total,
            "exact_matches": exact_matches,
            "exact_match_rate": exact_matches / total if total > 0 else 0,
            "average_f1": sum(f1_scores) / len(f1_scores) if f1_scores else 0,
            "average_item_accuracy": sum(item_accuracies) / len(item_accuracies) if item_accuracies else 0,
            "small_menu": {
                "total": len(small_menu_results),
                "exact_matches": sum(1 for r in small_menu_results if r["metrics"]["exact_match"]),
                "average_f1": sum(r["metrics"]["f1"] for r in small_menu_results) / len(small_menu_results) if small_menu_results else 0,
            },
            "large_menu": {
                "total": len(large_menu_results),
                "exact_matches": sum(1 for r in large_menu_results if r["metrics"]["exact_match"]),
                "average_f1": sum(r["metrics"]["f1"] for r in large_menu_results) / len(large_menu_results) if large_menu_results else 0,
            }
        }
    
    def to_json(self) -> str:
        """Convert report to JSON."""
        return json.dumps({
            "timestamp": datetime.now().isoformat(),
            "summary": self.summary,
            "results": self.results
        }, indent=2)
    
    def print_summary(self):
        """Print a human-readable summary."""
        print("\n" + "="*80)
        print("EVALUATION SUMMARY")
        print("="*80)
        print(f"\nTotal Scenarios: {self.summary['total_scenarios']}")
        print(f"Exact Matches: {self.summary['exact_matches']} ({self.summary['exact_match_rate']*100:.1f}%)")
        print(f"Average F1 Score: {self.summary['average_f1']:.3f}")
        print(f"Average Item Accuracy: {self.summary['average_item_accuracy']:.3f}")
        
        print("\n" + "-"*80)
        print("SMALL MENU RESULTS")
        print("-"*80)
        print(f"Scenarios: {self.summary['small_menu']['total']}")
        print(f"Exact Matches: {self.summary['small_menu']['exact_matches']} ({self.summary['small_menu']['exact_matches']/self.summary['small_menu']['total']*100:.1f}%)")
        print(f"Average F1: {self.summary['small_menu']['average_f1']:.3f}")
        
        print("\n" + "-"*80)
        print("LARGE MENU RESULTS")
        print("-"*80)
        print(f"Scenarios: {self.summary['large_menu']['total']}")
        print(f"Exact Matches: {self.summary['large_menu']['exact_matches']} ({self.summary['large_menu']['exact_matches']/self.summary['large_menu']['total']*100:.1f}%)")
        print(f"Average F1: {self.summary['large_menu']['average_f1']:.3f}")
        
        print("\n" + "="*80)
    
    def print_failures(self):
        """Print details of failed scenarios."""
        failures = [r for r in self.results if not r["metrics"]["exact_match"]]
        
        if not failures:
            print("\n✅ All scenarios passed!")
            return
        
        print(f"\n❌ Failed Scenarios: {len(failures)}")
        print("="*80)
        
        for result in failures:
            print(f"\nScenario: {result['scenario_id']} ({result['menu']} menu)")
            print(f"Description: {result['description']}")
            print(f"Input: {result['input_text']}")
            print(f"Expected: {json.dumps(result['expected'], indent=2)}")
            print(f"Actual: {json.dumps(result['actual'], indent=2)}")
            print(f"F1 Score: {result['metrics']['f1']:.3f}")
            print(f"Item Accuracy: {result['metrics']['item_accuracy']:.3f}")
            print("-"*80)


def run_evaluation(menu_name: str = None, scenario_ids: List[str] = None, verbose: bool = False):
    """
    Run evaluation on test scenarios.
    
    Args:
        menu_name: "small", "large", or None for all
        scenario_ids: List of specific scenario IDs to run, or None for all
        verbose: Print detailed logs
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Get scenarios
    if menu_name:
        scenarios = get_scenarios_by_menu(menu_name)
    else:
        scenarios = get_all_scenarios()
    
    if scenario_ids:
        scenarios = [s for s in scenarios if s.id in scenario_ids]
    
    logger.info(f"Running {len(scenarios)} scenarios")
    
    report = EvaluationReport()
    
    for scenario in scenarios:
        logger.info(f"\nRunning scenario: {scenario.id}")
        
        # Get menu
        menu = get_menu(scenario.menu)
        
        # Create normalizer
        normalizer = CartNormalizer(menu)
        
        # Parse order
        try:
            actual_cart = normalizer.parse_order(scenario.input_text)
        except Exception as e:
            logger.error(f"Error parsing scenario {scenario.id}: {e}")
            actual_cart = Cart()
        
        # Calculate metrics
        exact_match = CartEvaluator.exact_match(actual_cart, scenario.expected_cart)
        f1_score = CartEvaluator.calculate_f1(actual_cart, scenario.expected_cart)
        item_accuracy = CartEvaluator.calculate_item_accuracy(actual_cart, scenario.expected_cart)
        
        metrics = {
            "exact_match": exact_match,
            "f1": f1_score,
            "item_accuracy": item_accuracy
        }
        
        report.add_result(scenario, actual_cart, metrics)
        
        if exact_match:
            logger.info(f"✅ PASS: {scenario.id}")
        else:
            logger.warning(f"❌ FAIL: {scenario.id} (F1: {f1_score:.3f})")
    
    # Calculate summary
    report.calculate_summary()
    
    # Print results
    report.print_summary()
    report.print_failures()
    
    # Save to file
    output_file = f"evaluation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        f.write(report.to_json())
    
    print(f"\n📄 Full report saved to: {output_file}")
    
    return report


def main():
    parser = argparse.ArgumentParser(description="Evaluate cart normalization performance")
    parser.add_argument("--menu", choices=["small", "large"], help="Run scenarios for specific menu")
    parser.add_argument("--scenarios", nargs="+", help="Run specific scenario IDs")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    parser.add_argument("--output", "-o", help="Output file for JSON report")
    
    args = parser.parse_args()
    
    report = run_evaluation(
        menu_name=args.menu,
        scenario_ids=args.scenarios,
        verbose=args.verbose
    )
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report.to_json())
        print(f"Report saved to: {args.output}")
    
    # Exit with error code if there were failures
    if report.summary['exact_match_rate'] < 1.0:
        sys.exit(1)


if __name__ == "__main__":
    main()



