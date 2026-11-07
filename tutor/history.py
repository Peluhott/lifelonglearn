"""Turns past learning episodes into a hint for select_method. Rows come from PostgresSessions.recent_episodes(), newest
first, and are passed in as graph input so the graph itself never touches the database."""

from collections import Counter
from statistics import mean
from typing import get_args

from tutor.schemas import SelectMethodResult

# starting guesses, kept here so they're easy to tune once there's real data
MIN_SESSIONS = 5       # a method needs this many sessions before it's shown
RECENT_SESSIONS = 20   # only each method's newest sessions count, so old habits fade
MIN_SCORED = 3         # scored sessions a method needs before its scores are compared
MIN_REASON = 3         # a reason tag has to repeat this many times to be shown
EXPLORE_RATE = 0.2     # share of sessions that try something less used

METHODS = get_args(SelectMethodResult.model_fields["chosen_method"].annotation)


def by_method(rows: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["teaching_method"], []).append(row)
    return groups


def in_scope(rows: list[dict], category: str) -> tuple[list[dict], str | None]:
    """The rows to use and what to call them: this subject if it has enough, else all subjects, else nothing."""
    subject_rows = [row for row in rows if row["subject"] == category]
    for scoped, label in ((subject_rows, category), (rows, "all subjects")):
        if any(len(group) >= MIN_SESSIONS for group in by_method(scoped).values()):
            return scoped, label
    return [], None


def recent(rows: list[dict]) -> list[dict]:
    return [row for group in by_method(rows).values() for row in group[:RECENT_SESSIONS]]


def stats(rows: list[dict]) -> str:
    rated = [row["liked"] for row in rows if row["liked"] is not None]
    thumbs = f"{sum(rated) / len(rated):.0%} thumbs up" if rated else "no ratings"
    return f"{len(rows)} sessions, {thumbs}, finished {sum(row['finished'] for row in rows)}"


def score_vs_usual(rows: list[dict]) -> dict[str, float]:
    """Each method's scores against the average for the same test type, since raw scores aren't comparable across types.

    A test type only one method uses is skipped: socratic and worked_faded are their own test types, so comparing them
    to their own average would always come out near zero.
    """
    tests: dict[str, list[dict]] = {}
    for row in rows:
        if row["score"] is not None and row["testing_method"]:
            tests.setdefault(row["testing_method"], []).append(row)

    differences: dict[str, list[float]] = {}
    for scored in tests.values():
        if len({row["teaching_method"] for row in scored}) < 2:
            continue
        usual = mean(row["score"] for row in scored)
        for row in scored:
            differences.setdefault(row["teaching_method"], []).append(row["score"] - usual)
    return {method: mean(diffs) for method, diffs in differences.items() if len(diffs) >= MIN_SCORED}


def method_lines(rows: list[dict]) -> list[str]:
    """One line per method with enough sessions. request_type comes out of the same call this hint goes into, so each
    method is broken down by it for the model to find the row that fits."""
    scores = score_vs_usual(rows)
    lines = []
    for method, group in sorted(by_method(rows).items(), key=lambda item: -len(item[1])):
        if len(group) < MIN_SESSIONS:
            continue
        line = f"- {method}: {stats(group)}"
        if method in scores:
            line += f", scores {scores[method]:+.2f} vs your usual"
        lines.append(line)
        request_types: dict[str, list[dict]] = {}
        for row in group:
            request_types.setdefault(row["request_type"], []).append(row)
        lines += [f"  - {name}: {stats(rows_)}" for name, rows_ in request_types.items() if len(rows_) >= MIN_SESSIONS]
    return lines


def reason_line(rows: list[dict]) -> str | None:
    counts = Counter((row["teaching_method"], row["liked_reason"]) for row in rows if row["liked_reason"])
    repeated = [f"{method}: {reason} ×{count}" for (method, reason), count in counts.most_common() if count >= MIN_REASON]
    return f"Reasons given: {'; '.join(repeated)}" if repeated else None


def least_tried(rows: list[dict]) -> list[str]:
    """The two methods with the fewest sessions, counting methods that haven't been used at all."""
    groups = by_method(rows)
    return sorted(METHODS, key=lambda method: len(groups.get(method, [])))[:2]


def build_hint(rows: list[dict], category: str, explore: bool = False) -> str:
    """The text select_method gets, or "" if there's nothing to say yet."""
    scoped, label = in_scope(rows, category)
    lines = method_lines(recent(scoped))
    if lines:
        lines.insert(0, f"Your history in {label}:")
    reasons = reason_line(recent(scoped or rows))  # tags are a clear signal, so they don't wait for MIN_SESSIONS
    if reasons:
        lines.append(reasons)
    if explore:
        lines.append(f"This session is for trying something less used: {', '.join(least_tried(scoped))}.")
    return "\n".join(lines)
