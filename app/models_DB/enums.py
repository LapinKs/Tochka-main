from sqlalchemy import Enum

order_status_enum = Enum(
    "NEW", "EXECUTED", "PARTIALLY_EXECUTED", "CANCELLED",
    name="order_status"
)

order_direction_enum = Enum(
    "BUY", "SELL",
    name="order_direction"
)

user_role_enum = Enum (
    "ADMIN", "USER",
    name = "user_role"
)