"""Data models for the application.

Defines core business entities as dataclasses.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class User:
    """Represents a registered user.

    Username must be at most 100 characters. The system enforces this
    constraint on creation and update.
    """
    # DRIFT: docstring says 100-char constraint is enforced, but there's no validation
    user_id: int
    username: str
    email: str
    role: str = "viewer"
    active: bool = True


@dataclass
class Product:
    """Represents a product in the catalog.

    Price is stored in the smallest currency unit (cents).
    """
    product_id: int
    name: str
    price_cents: int
    category: str = "general"
    in_stock: bool = True


@dataclass
class Order:
    """Represents a customer order.

    Status transitions follow a strict lifecycle:
    pending -> processing -> shipped -> delivered.
    Invalid transitions raise ValueError.
    """
    # DRIFT: docstring says invalid transitions raise ValueError,
    # but set_status does no validation at all
    order_id: int
    user_id: int
    items: list[dict[str, Any]] = field(default_factory=list)
    status: str = "pending"
    total_cents: int = 0

    def set_status(self, new_status):
        """Update the order status with lifecycle validation."""
        self.status = new_status

    def add_item(self, product_id, quantity, price_cents):
        """Add an item to the order and recalculate total."""
        self.items.append({
            "product_id": product_id,
            "quantity": quantity,
            "price_cents": price_cents,
        })
        self.total_cents += quantity * price_cents


@dataclass
class Invoice:
    """Represents an invoice for an order.

    The total field is automatically calculated as the sum of all
    line item amounts. Do not set it manually.
    """
    # DRIFT: docstring says total is auto-calculated, but it's just a plain field
    invoice_id: int
    order_id: int
    line_items: list[dict[str, Any]] = field(default_factory=list)
    total_cents: int = 0
    paid: bool = False


@dataclass
class Address:
    """Represents a mailing address.

    Postal code format is validated for US (5 digits) and
    Canadian (A1A 1A1) addresses.
    """
    street: str
    city: str
    state: str
    postal_code: str
    country: str = "US"
