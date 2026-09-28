"""The extraction output: every provider must return this. Missing values are None, never guessed."""
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel


class Item(BaseModel):
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    amount: Optional[Decimal] = None  # before the line discount
    discount: Optional[Decimal] = None  # line discount; positive = money taken off


class Document(BaseModel):
    doc_type: Optional[Literal['invoice', 'receipt']] = None
    vendor: Optional[str] = None
    buyer: Optional[str] = None
    doc_number: Optional[str] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    currency: Optional[str] = None  # ISO 4217, e.g. USD
    subtotal: Optional[Decimal] = None
    discount: Optional[Decimal] = None  # positive number = money taken off
    tax: Optional[Decimal] = None
    service_charge: Optional[Decimal] = None
    total: Optional[Decimal] = None
    items: list[Item] = []
