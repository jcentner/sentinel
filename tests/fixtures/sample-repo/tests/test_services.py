"""Tests for business logic services — mix of coherent and drifted tests."""

from myapp.models import Order, User
from myapp.services import (
    apply_discount,
    calculate_shipping,
    generate_report,
    process_refund,
    send_notification,
    validate_order,
)


def test_free_shipping_over_50():
    """Test that orders over $50 get free shipping.

    The calculate_shipping function should return 0 for orders
    with a total exceeding $50.
    """
    # DRIFT: function uses $100 threshold, not $50
    order = Order(order_id=1, user_id=1, total_cents=5100)  # $51
    assert calculate_shipping(order) == 0


def test_domestic_shipping_rate():
    """Test standard domestic shipping rate."""
    order = Order(order_id=2, user_id=1, total_cents=1000)
    cost = calculate_shipping(order)
    assert cost == 599


def test_apply_discount_save10():
    """Test 10% discount code."""
    order = Order(order_id=3, user_id=1, total_cents=10000)
    discount = apply_discount(order, "SAVE10")
    assert discount == 1000


def test_apply_discount_invalid_code():
    """Test that invalid discount codes return zero."""
    order = Order(order_id=4, user_id=1, total_cents=10000)
    assert apply_discount(order, "BOGUS") == 0


def test_notification_sends_sms():
    """Test that notification is sent via both email and SMS.

    Default channels should include SMS in addition to email.
    """
    # DRIFT: function defaults to email only, SMS not implemented
    user = User(user_id=1, username="test", email="test@test.com")
    result = send_notification(user, "Hello")
    sms_sent = [s for s in result["sent"] if s["channel"] == "sms"]
    assert len(sms_sent) > 0


def test_notification_email():
    """Test that email notifications include correct recipient."""
    user = User(user_id=1, username="test", email="test@test.com")
    result = send_notification(user, "Hello", channels=["email"])
    assert result["sent"][0]["to"] == "test@test.com"


def test_report_returns_pdf():
    """Test that generate_report returns PDF bytes.

    The returned value should be bytes ready for file writing.
    """
    # DRIFT: function returns a dict, not bytes
    result = generate_report("2024-01-01", "2024-01-31")
    assert isinstance(result, bytes)


def test_validate_order_empty():
    """Test that empty orders are rejected."""
    order = Order(order_id=5, user_id=1)
    result = validate_order(order)
    assert not result["valid"]


def test_validate_order_total_mismatch():
    """Test that mismatched totals are caught."""
    order = Order(order_id=6, user_id=1, total_cents=999)
    order.items = [{"product_id": 1, "quantity": 1, "price_cents": 500}]
    result = validate_order(order)
    assert not result["valid"]


def test_refund_only_pending():
    """Test that only pending/processing orders can be refunded.

    Shipped and delivered orders should raise an error.
    """
    # DRIFT: function refunds any status, no validation
    order = Order(order_id=7, user_id=1, total_cents=5000, status="delivered")
    result = process_refund(order, "customer request")
    assert "error" in result
