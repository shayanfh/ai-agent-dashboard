from typing import Optional, Any
from pydantic import BaseModel


class ERPNextCustomer(BaseModel):
    name: Optional[str] = None
    customer_name: str
    mobile_no: Optional[str] = None
    customer_type: str = "Individual"
    customer_group: str = "All Customer Groups"
    territory: str = "All Territories"


class ERPNextDocument(BaseModel):
    doctype: str
    data: dict[str, Any]


class ERPNextResponse(BaseModel):
    name: str
    doctype: str
    data: dict[str, Any] = {}
