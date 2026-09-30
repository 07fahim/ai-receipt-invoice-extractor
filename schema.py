"""The extraction output: every provider must return this. Missing values are None, never guessed."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

# Bounded, so one request can't make the checks or the suggestion search run for minutes
Money = Annotated[Decimal, Field(max_digits=20, decimal_places=6)]


class Item(BaseModel):
    description: Optional[str] = None
    quantity: Optional[Money] = None
    unit_price: Optional[Money] = None
    amount: Optional[Money] = None  # before the line discount
    discount: Optional[Money] = None  # line discount; positive = money taken off


class Document(BaseModel):
    is_document: Optional[bool] = None  # False: not a receipt/invoice at all (menu, photo, logo); None: unknown
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
    subtotal: Optional[Money] = None
    discount: Optional[Money] = None  # positive number = money taken off
    tax: Optional[Money] = None  # all taxes and duties together (VAT + supplementary duty)
    tax_included: Optional[bool] = None  # True: prices already include the tax ("VAT included"); None: unknown
    service_charge: Optional[Money] = None
    total: Optional[Money] = None
    total_text: Optional[str] = None  # total exactly as printed, e.g. 22.000 (thousands or decimals can be ambiguous)
    items: list[Item] = Field(default=[], max_length=200)
