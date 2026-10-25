import numpy as np

from app.forecasting import model as fm
from app.simulation import demand as dm


def test_quantiles_are_ordered_and_non_negative(world):
    for h, q in world.preds.items():
        assert q.shape == (world.ss.n, 3)
        assert np.all(q >= 0)
        assert np.all(q[:, 0] <= q[:, 1] + 1e-9) and np.all(q[:, 1] <= q[:, 2] + 1e-9)


def test_horizons_are_monotone_in_expectation(world):
    p = {h: q[:, 1].sum() for h, q in world.preds.items()}
    assert p[7] < p[14] < p[30]


def test_features_do_not_use_future_sales(world):
    prep = fm.prepare(world)
    d = world.t0
    a = fm.build_features(world, prep, world.sales, d, 14)
    mutated = world.sales.copy()
    mutated[:, d:] = 999  # tamper with everything on/after the origin
    b = fm.build_features(world, prep, mutated, d, 14)
    assert np.array_equal(a, b)


def test_training_windows_end_before_cutoff(world):
    # a model trained with cutoff T0 must be identical if post-T0 sales are tampered with
    prep = fm.prepare(world)
    s2 = world.sales.copy()
    s2[:, world.t0:] = 0
    m1 = fm.train(world, prep, world.sales, world.t0, "fast")
    m2 = fm.train(world, prep, s2, world.t0, "fast")
    f = fm.build_features(world, prep, world.sales, world.t0, 7)
    assert np.allclose(m1.predict(f, 7), m2.predict(f, 7))


def test_zero_demand_series_is_safe(world):
    prep = fm.prepare(world)
    s = world.sales.copy()
    s[0, :] = 0
    f = fm.build_features(world, prep, s, world.t0, 7)
    q = world.models.predict(f, 7)
    assert np.isfinite(q).all()
    assert q[0, 0] <= q[0, 1] <= q[0, 2]


def test_accuracy_is_reported_honestly(world):
    m = world.metrics
    assert len(m["weeks"]) == (dm.N_DAYS - world.t0) // 7
    assert m["wape"] > 0 and m["mape_mean"] > 0
    assert m["target_met"] == (m["mape_mean"] < 20.0)
    assert m["train_cutoff_idx"] == world.t0 == dm.N_DAYS - dm.TEST_DAYS


def test_safety_stock_is_p90_minus_p50_gap():
    p50, p90 = np.array([10.0]), np.array([16.0])
    assert fm.safety_stock(p50, p90, 7, np.array([7])) == 6.0
    assert fm.safety_stock(p50, p90, 7, np.array([1]))[0] < 6.0
    assert fm.safety_stock(p90, p50, 7, np.array([3]))[0] == 0.0  # never negative


def test_generator_is_reproducible():
    from app.simulation import generator as g
    cfg = g.GeneratorConfig(profile="t", seed=3, n_stores=8, n_skus=8, assortment=0.5, n_promotions=4)
    a, b = g.build(cfg), g.build(cfg)
    assert np.array_equal(a["sales"], b["sales"])
    cfg2 = g.GeneratorConfig(profile="t", seed=4, n_stores=8, n_skus=8, assortment=0.5, n_promotions=4)
    assert not np.array_equal(a["sales"], g.build(cfg2)["sales"])
