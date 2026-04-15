"""Business logic services.

Higher-level operations that compose models and handlers.
"""


def calculate_shipping(order):
    """Calculate shipping cost for an order.

    Free shipping for orders over $50. Standard rate is $5.99
    for domestic and $15.99 for international.
    """
    # DRIFT: docstring says free over $50, code uses $100 threshold
    total_dollars = order.total_cents / 100
    if total_dollars >= 100:
        return 0
    country = getattr(order, "country", "US")
    if country == "US":
        return 599
    return 1599


def apply_discount(order, discount_code):
    """Apply a discount code to an order.

    Supported codes:
    - SAVE10: 10% off
    - SAVE20: 20% off
    - FLAT5: $5 flat discount

    Returns the discount amount in cents.
    """
    codes = {
        "SAVE10": lambda t: int(t * 0.10),
        "SAVE20": lambda t: int(t * 0.20),
        "FLAT5": lambda _: 500,
    }
    calculator = codes.get(discount_code.upper())
    if calculator is None:
        return 0
    return calculator(order.total_cents)


def send_notification(user, message, channels=None):
    """Send a notification to a user via email and SMS.

    Dispatches the message through all configured channels.
    Defaults to both email and SMS if no channels specified.
    """
    # DRIFT: docstring says email and SMS, code only does email
    if channels is None:
        channels = ["email"]
    sent = []
    for channel in channels:
        if channel == "email":
            sent.append({"channel": "email", "to": user.email, "body": message})
    return {"sent": sent, "failed": []}


def generate_report(start_date, end_date):
    """Generate a summary report for the given date range.

    Returns the report as PDF bytes ready for download or attachment.
    The report includes order counts, revenue totals, and top products.
    """
    # DRIFT: docstring says returns PDF bytes, code returns a dict
    return {
        "start": start_date,
        "end": end_date,
        "orders": 0,
        "revenue_cents": 0,
        "top_products": [],
    }


def validate_order(order):
    """Validate an order before processing.

    Checks that the order has at least one item, all quantities are
    positive, and the total matches the sum of item prices.
    """
    if not order.items:
        return {"valid": False, "error": "Order has no items"}
    for item in order.items:
        if item.get("quantity", 0) <= 0:
            return {"valid": False, "error": f"Invalid quantity for {item.get('product_id')}"}
    expected = sum(i["quantity"] * i["price_cents"] for i in order.items)
    if order.total_cents != expected:
        return {"valid": False, "error": "Total mismatch"}
    return {"valid": True}


def process_refund(order, reason):
    """Process a full refund for an order.

    Updates the order status to 'refunded' and returns the refund
    amount. Only pending and processing orders can be refunded.
    """
    # DRIFT: docstring says only pending/processing can be refunded,
    # code refunds any status
    amount = order.total_cents
    order.set_status("refunded")
    return {"refunded_cents": amount, "reason": reason}
