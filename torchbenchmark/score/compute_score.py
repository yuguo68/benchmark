
"""
Compute the benchmark score given a frozen score configuration and current benchmark data.
"""
import argparse
import json
import math
import sys
import os
import yaml
from pathlib import Path
import importlib
import collections
sys.path.append("/data/users/nikithamalgi/benchmark")
from torchbenchmark import list_models
from generate_score_config import generate_bench_cfg
from tabulate import tabulate

TARGET_SCORE_DEFAULT = 1000

def generate_spec():
    """
    Helper function which constructs the spec dictionary by iterating
    over the existing models. This API is used for generating the
    default spec hierarchy configuration.
    return type:
        Returns a dictionary of type collections.defaultdict. Defaultdict
        handles `None` or missing values and hence, no explicit `None` check
        is required.

    Arguments: `None`
    Note: Only those models with `domain` and `task` class attributes are
          used to construct the spec hierarchy.
    """
    spec = {'hierarchy':{'model':collections.defaultdict(dict)}}

    for model in list_models():
        if hasattr(model, 'domain'):
            if model.name == "attention_is_all_you_need_pytorch":
                model.name = "attention_is_all_you_nee..."
            if not spec['hierarchy']['model'][model.domain]:
                spec['hierarchy']['model'][model.domain] = collections.defaultdict(dict)
            if not spec['hierarchy']['model'][model.domain][model.task]:
                spec['hierarchy']['model'][model.domain][model.task] = collections.defaultdict(dict)
            spec['hierarchy']['model'][model.domain][model.task][model.name] = None

    return spec

def compute_score(config, data, fake_data=None):
    target = config['target']
    score = 0.0
    weight_sum = 0.0
    for name in config['benchmarks']:
        cfg = config['benchmarks'][name]
        weight, norm = cfg['weight'], cfg['norm']
        weight_sum += weight
        measured_mean = [b['stats']['mean'] for b in data['benchmarks'] if b['name'] == name]
        assert len(measured_mean) == 1, f"Missing data for {name}, unable to compute score"
        measured_mean = measured_mean[0]
        if fake_data is not None and name in fake_data:
            # used for sanity checks on the sensitivity of the score metric
            measured_mean = fake_data[name]
        benchmark_score = weight * math.log(norm / measured_mean)
        # print(f"{name}: {benchmark_score}")
        score += benchmark_score

    score = target * math.exp(score)
    assert abs(weight_sum - 1.0) < 1e-6, f"Bad configuration, weights don't sum to 1, but {weight_sum}"
    return score

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration",
        help="frozen benchmark configuration generated by generate_score_config.py")
    parser.add_argument("--benchmark_data_file",
        help="pytest-benchmark json file with current benchmark data")
    parser.add_argument("--benchmark_data_dir",
        help="directory containing multiple .json files for each of which to compute a score")
    parser.add_argument('--hack_data', nargs=2, action='append', help="keyword to match benchmark names, and multiplicative factor to adjust their measurement")
    args = parser.parse_args()

    config = None
    if args.configuration is not None:
        with open(args.configuration) as cfg_file:
            config = yaml.full_load(cfg_file)
    else:
        if args.benchmark_data_file is None and args.benchmark_data_dir is None:
            parser.print_help(sys.stderr)
            raise ValueError("Invalid command-line arguments. You must specify a config, a data file, or a data dir.")
        # Generate default spec by iterating over the existing models.
        spec = generate_spec()

    if args.benchmark_data_file is not None:
        with open(args.benchmark_data_file) as data_file:
            data = json.load(data_file)
            if config is None:
                config = generate_bench_cfg(spec, data, TARGET_SCORE_DEFAULT)
        score = compute_score(config, data)
        print(score)
        if args.hack_data:
            fake_data = {}
            for keyword, factor in args.hack_data:
                for b in data['benchmarks']:
                    if keyword.lower() in b['name'].lower():
                        fake_data[b['name']] =  b['stats']['mean'] * float(factor)

            hacked_score = compute_score(config, data, fake_data)
            print(f"Using hacks {args.hack_data}, hacked_score {hacked_score}")

    elif args.benchmark_data_dir is not None:
        scores = [('File', 'Score', 'PyTorch Version')]
        for f in os.listdir(args.benchmark_data_dir):
            path = os.path.join(args.benchmark_data_dir, f)
            if os.path.isfile(path) and os.path.splitext(path)[1] == '.json':
                with open(path) as data_file:
                    data = json.load(data_file)
                    if config is None:
                        config = generate_bench_cfg(spec, data, TARGET_SCORE_DEFAULT)
                    score = compute_score(config, data)
                    scores.append((f, score, data['machine_info']['pytorch_version']))

        print(tabulate(scores, headers='firstrow'))

    # print(f"Benchmark Score: {score} (rounded) {int(round(score))}")
