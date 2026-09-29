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
    document_count: Optional[int] = None  # separate receipts/invoices in the image; more than 1 goes to review
    vendor: Optional[str] = None  # business name only, so date formats and totals group by vendor
    branch: Optional[str] = None  # store number or location, e.g. "017314"
    buyer: Optional[str] = None
    doc_number: Optional[str] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    issue_date_text: Optional[str] = None  # dates exactly as printed, e.g. 05/11/2021 (day/month order can be ambiguous)
    due_date_text: Optional[str] = None
    currency: Optional[str] = None  # ISO 4217, e.g. USD
    subtotal: Optional[Decimal] = None
    discount: Optional[Decimal] = None  # positive number = money taken off
    tax: Optional[Decimal] = None
    service_charge: Optional[Decimal] = None
    total: Optional[Decimal] = None
    total_text: Optional[str] = None  # total exactly as printed, e.g. 22.000 (thousands or decimals can be ambiguous)
    items: list[Item] = []
