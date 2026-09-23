from ai_lining.analytics import compute_daily_observation, compute_watched_product, format_kes


def test_format_kes_converts_minor_units() -> None:
    assert format_kes(150000) == "Ksh 1,500"


def _order(hour: str, product_id: str, quantity: float, unit_price: float) -> dict:
    return {
        "created_at": f"2026-01-15T{hour}:00:00",
        "line_items": [
            {"product_id": product_id, "quantity": quantity, "unit_price": unit_price}
        ],
    }


def test_compute_daily_observation_buckets_by_two_hour_window() -> None:
    orders_today = [_order("07", "prod1", 2, 500), _order("08", "prod1", 1, 500)]
    orders_yesterday = [_order("07", "prod1", 1, 500)]

    observation = compute_daily_observation(orders_today, orders_yesterday)

    assert observation.peak_index == 3  # hour 7 falls in the 06:00-08:00 bucket
    assert observation.hourly_sales[3] == 1000
    assert observation.hourly_sales[4] == 500  # hour 8 falls in the 08:00-10:00 bucket
    assert observation.peak_window == "From 06:00 - 08:00"
    assert "better" in observation.performance_note


def test_compute_daily_observation_handles_no_previous_orders() -> None:
    observation = compute_daily_observation([_order("07", "prod1", 1, 500)], [])
    assert observation.performance_percent == "0%"


def test_compute_watched_product_picks_highest_velocity() -> None:
    recent_orders = [
        _order("07", "prod1", 10, 100),
        _order("08", "prod2", 1, 100),
    ]
    stock_by_product = {"prod1": 5, "prod2": 100}
    product_names = {"prod1": "Morning Coffee", "prod2": "Tea"}

    watched_product, alert = compute_watched_product(
        recent_orders, stock_by_product, product_names, velocity_window_days=1, stock_threshold_days=2.0
    )

    assert watched_product.subtitle == "Morning Coffee Sales"
    assert alert is not None
    assert alert.id == "low_stock_prod1"


def test_compute_watched_product_no_alert_when_stock_is_healthy() -> None:
    recent_orders = [_order("07", "prod1", 1, 100)]
    stock_by_product = {"prod1": 1000}
    product_names = {"prod1": "Morning Coffee"}

    _watched_product, alert = compute_watched_product(
        recent_orders, stock_by_product, product_names, velocity_window_days=1, stock_threshold_days=2.0
    )

    assert alert is None
