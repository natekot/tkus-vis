import math

import pytest
from demo_data import demo

from tkus_vis.ledger import Snapshot
from tkus_vis.model import PR, build_dataset
from tkus_vis.story import slides_for


def test_the_demo_repository_reconciles_and_fills_the_joined_deck():
    files, prs = demo()
    dataset, problems = build_dataset(
        Snapshot("acme/widgets", "main", "c" * 40, "main", files), "t", prs
    )
    assert problems == []
    [view] = dataset.views
    assert math.fsum(view.buckets.values()) == pytest.approx(view.total, abs=1e-9)
    assert math.fsum(p.usd for p in view.prs) == pytest.approx(view.buckets[PR], abs=1e-9)
    assert [s.slug.split("-", 1)[1] for s in slides_for(dataset, view)] == [
        "headline",
        "cost-per-pr",
        "top-prs",
        "spend-and-prs",
        "spend-by-model",
        "where-spend-sits",
    ]
