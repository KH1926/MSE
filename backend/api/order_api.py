from __future__ import annotations

from fastapi import APIRouter

try:
    from common import ok
    from contracts.request_models import OrderCreate
    from domain.orders import (
        create_order,
        generate_work_order,
        list_orders,
    )
except ModuleNotFoundError:
    from ..common import ok
    from ..contracts.request_models import OrderCreate
    from ..domain.orders import (
        create_order,
        generate_work_order,
        list_orders,
    )

router = APIRouter(tags=["orders"])


@router.get("/orders")
def get_orders_route() -> dict[str, object]:
    return ok(list_orders())


@router.post("/orders")
def create_order_route(payload: OrderCreate) -> dict[str, object]:
    return ok(create_order(payload))


@router.post("/orders/{order_no}/generate-work-order")
def generate_work_order_route(order_no: str) -> dict[str, object]:
    return ok(generate_work_order(order_no))
