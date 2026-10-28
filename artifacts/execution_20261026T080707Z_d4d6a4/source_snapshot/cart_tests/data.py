"""Explicit exploration baseline; never replace expected prices with live values."""

from dataclasses import dataclass
from decimal import Decimal

BASE_URL = "https://opencart.abstracta.us/index.php?route="
CART_URL = BASE_URL + "checkout/cart"
EMPTY_MESSAGE = "Your shopping cart is empty!"


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    model: str
    unit_price: Decimal
    option_id: str | None = None
    option_value: str | None = None
    option_label: str | None = None

    @property
    def cart_options(self):
        return (f"Select: {self.option_label}",) if self.option_id else ()

    @property
    def url(self):
        return BASE_URL + f"product/product&product_id={self.id}"


PRODUCTS = {
    41: Product(41, "iMac", "Product 14", Decimal("122.00")),
    30: Product(30, "Canon EOS 5D", "Product 3", Decimal("98.00"),
                "input-option226", "15", "Red"),
}
