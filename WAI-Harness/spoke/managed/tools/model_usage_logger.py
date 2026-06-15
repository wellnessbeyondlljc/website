#!/usr/bin/env python3
"""
Model Usage Logger for WAI Spokes

Logs model usage events to WAI-Spoke/model-usage/usage.jsonl
Events are later collected at the hub for analysis.

Usage:
    python3 tools/model_usage_logger.py log --provider anthropic --model claude-opus-4-6 \
        --task-type implementation --complexity high --tokens-in 5000 --tokens-out 2000 \
        --cost-estimate 0.21 --duration-ms 30000 --quality-rating 8

    python3 tools/model_usage_logger.py feedback --model claude-opus-4-6 --rating 9 --notes "excellent reasoning"
"""

import json
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

USAGE_DIR = Path("WAI-Spoke/model-usage")
USAGE_FILE = USAGE_DIR / "usage.jsonl"


def ensure_dir():
    USAGE_DIR.mkdir(parents=True, exist_ok=True)


def log_event(event_type, **kwargs):
    """Log a model usage event to the usage file."""
    ensure_dir()

    event = {
        "event": event_type,
        "ts": datetime.now(timezone.utc).isoformat(),
        "spoke_id": "framework",  # Should be configurable per spoke
        **kwargs,
    }

    with open(USAGE_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")

    return event


def log_usage(
    provider,
    model,
    task_type,
    complexity=None,
    tokens_in=None,
    tokens_out=None,
    cost_estimate=None,
    duration_ms=None,
    quality_rating=None,
    rework_required=None,
    session_id=None,
):
    """Log a model usage event."""
    return log_event(
        "model_usage",
        provider=provider,
        model=model,
        task_type=task_type,
        complexity=complexity,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_estimate=cost_estimate,
        duration_ms=duration_ms,
        quality_rating=quality_rating,
        rework_required=rework_required,
        session_id=session_id,
    )


def log_feedback(
    provider,
    model,
    session_id,
    rating,
    notes=None,
    task_type=None,
    rework_required=None,
    rework_reason=None,
):
    """Log quality feedback for a model."""
    return log_event(
        "quality_feedback",
        provider=provider,
        model=model,
        session_id=session_id,
        rating=rating,
        notes=notes,
        task_type=task_type,
        rework_required=rework_required,
        rework_reason=rework_reason,
    )


def log_recommendation_accepted(
    recommendation_id, model_used, task_type=None, quality_outcome=None
):
    """Log when user accepts a model recommendation."""
    return log_event(
        "recommendation_accepted",
        recommendation_id=recommendation_id,
        model_used=model_used,
        task_type=task_type,
        quality_outcome=quality_outcome,
    )


def query_usage(
    start_date=None, end_date=None, provider=None, model=None, task_type=None, limit=100
):
    """Query recent usage events."""
    if not USAGE_FILE.exists():
        return []

    events = []
    with open(USAGE_FILE) as f:
        for line in f:
            try:
                event = json.loads(line)

                if provider and event.get("provider") != provider:
                    continue
                if model and event.get("model") != model:
                    continue
                if task_type and event.get("task_type") != task_type:
                    continue

                events.append(event)
            except json.JSONDecodeError:
                continue

    return events[-limit:]


def stats():
    """Print usage statistics."""
    if not USAGE_FILE.exists():
        print("No usage data recorded yet.")
        return

    from collections import Counter

    providers = Counter()
    models = Counter()
    task_types = Counter()
    total_cost = 0
    total_tokens_in = 0
    total_tokens_out = 0
    ratings = []

    with open(USAGE_FILE) as f:
        for line in f:
            try:
                event = json.loads(line)
                if event.get("event") == "model_usage":
                    providers[event.get("provider")] += 1
                    models[event.get("model")] += 1
                    task_types[event.get("task_type")] += 1
                    total_cost += event.get("cost_estimate", 0)
                    total_tokens_in += event.get("tokens_in", 0)
                    total_tokens_out += event.get("tokens_out", 0)
                elif event.get("event") == "quality_feedback":
                    ratings.append(event.get("rating", 0))
            except json.JSONDecodeError:
                continue

    print(f"\n=== Model Usage Statistics ===")
    print(f"Total events: {providers.total()}")
    print(f"\nBy Provider:")
    for p, c in providers.most_common():
        print(f"  {p}: {c} calls")
    print(f"\nBy Model:")
    for m, c in models.most_common():
        print(f"  {m}: {c} calls")
    print(f"\nBy Task Type:")
    for t, c in task_types.most_common():
        print(f"  {t}: {c} calls")
    print(f"\nTotals:")
    print(f"  Cost: ${total_cost:.2f}")
    print(f"  Tokens In: {total_tokens_in:,}")
    print(f"  Tokens Out: {total_tokens_out:,}")
    if ratings:
        print(
            f"  Avg Quality: {sum(ratings) / len(ratings):.1f}/10 ({len(ratings)} ratings)"
        )


def main():
    parser = argparse.ArgumentParser(description="WAI Model Usage Logger")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    log_parser = subparsers.add_parser("log", help="Log a model usage event")
    log_parser.add_argument("--provider", required=True)
    log_parser.add_argument("--model", required=True)
    log_parser.add_argument("--task-type", required=True)
    log_parser.add_argument("--complexity")
    log_parser.add_argument("--tokens-in", type=int)
    log_parser.add_argument("--tokens-out", type=int)
    log_parser.add_argument("--cost-estimate", type=float)
    log_parser.add_argument("--duration-ms", type=int)
    log_parser.add_argument("--quality-rating", type=int)
    log_parser.add_argument("--rework-required", action="store_true")
    log_parser.add_argument("--session-id")

    fb_parser = subparsers.add_parser("feedback", help="Log quality feedback")
    fb_parser.add_argument("--provider", required=True)
    fb_parser.add_argument("--model", required=True)
    fb_parser.add_argument("--session-id", required=True)
    fb_parser.add_argument("--rating", type=int, required=True)
    fb_parser.add_argument("--notes")
    fb_parser.add_argument("--task-type")
    fb_parser.add_argument("--rework-required", action="store_true")
    fb_parser.add_argument("--rework-reason")

    rec_parser = subparsers.add_parser("accepted", help="Log accepted recommendation")
    rec_parser.add_argument("--recommendation-id", required=True)
    rec_parser.add_argument("--model-used", required=True)
    rec_parser.add_argument("--task-type")
    rec_parser.add_argument("--quality-outcome", type=int)

    subparsers.add_parser("stats", help="Show usage statistics")
    subparsers.add_parser("query", help="Query usage events")

    args = parser.parse_args()

    if args.command == "log":
        event = log_usage(
            provider=args.provider,
            model=args.model,
            task_type=args.task_type,
            complexity=args.complexity,
            tokens_in=args.tokens_in,
            tokens_out=args.tokens_out,
            cost_estimate=args.cost_estimate,
            duration_ms=args.duration_ms,
            quality_rating=args.quality_rating,
            rework_required=args.rework_required,
            session_id=args.session_id,
        )
        print(f"Logged: {event['event']} at {event['ts']}")

    elif args.command == "feedback":
        event = log_feedback(
            provider=args.provider,
            model=args.model,
            session_id=args.session_id,
            rating=args.rating,
            notes=args.notes,
            task_type=args.task_type,
            rework_required=args.rework_required,
            rework_reason=args.rework_reason,
        )
        print(f"Logged feedback: {event['ts']}")

    elif args.command == "accepted":
        event = log_recommendation_accepted(
            recommendation_id=args.recommendation_id,
            model_used=args.model_used,
            task_type=args.task_type,
            quality_outcome=args.quality_outcome,
        )
        print(f"Logged recommendation acceptance: {event['ts']}")

    elif args.command == "stats":
        stats()

    elif args.command == "query":
        events = query_usage(limit=20)
        for e in events:
            print(json.dumps(e))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
