from enum import Enum
from typing import List

from tortoise import fields, models
from tortoise.contrib.postgres.fields import ArrayField

from nexus import Context, Model, Protocol


PROTOCOL_NAME = "cleaning"
PROTOCOL_VERSION = "0.1.0"


class Service(str, Enum):
    FLOOR = "floor"
    WINDOW = "window"
    LAUNDRY = "laundry"
    IRON = "iron"
    BATHROOM = "bathroom"


class Availability(models.Model):
    address = fields.IntField(default=0)
    max_distance = fields.IntField(default=10)
    time_start: fields.DatetimeField()
    time_end: fields.DatetimeField(default=24)
    services: ArrayField(element_type=str)
    min_hourly_price: fields.FloatField(default=0.0)


class ServiceRequest(Model):
    address: int
    time_start: int
    duration: int
    services: List[Service]
    max_price: float


class ServiceResponse(Model):
    accept: bool
    price: float


class ServiceBooking(Model):
    address: str
    time_start: int
    duration: int
    services: List[Service]
    price: float


class BookingResponse(Model):
    success: bool


cleaning_proto = Protocol(name=PROTOCOL_NAME, version=PROTOCOL_VERSION)


def in_service_region(address: int, availability: Availability) -> bool:
    return abs(availability.address - address) <= availability.max_distance


@cleaning_proto.on_message(model=ServiceRequest, replies=ServiceResponse)
async def handle_query_request(ctx: Context, sender: str, msg: ServiceRequest):

    availability = Availability(**ctx.storage.get("availability"))
    markup = float(ctx.storage.get("markup"))

    if (
        set(msg.services) <= set(availability.services)
        and in_service_region(msg.address, availability)
        and availability.time_start <= msg.time_start
        and availability.time_end >= msg.time_start + msg.duration
        and availability.min_hourly_price * msg.duration < msg.max_price
    ):
        accept = True
        price = markup * availability.min_hourly_price * msg.duration
        print(f"I am available! Proposing price: {price}.")
    else:
        accept = False
        price = 0
        print("I am not available. Declining request.")

    await ctx.send(sender, ServiceResponse(accept=accept, price=price))


@cleaning_proto.on_message(model=ServiceBooking, replies=BookingResponse)
async def handle_book_request(ctx: Context, sender: str, msg: ServiceBooking):

    availability = Availability(**ctx.storage.get("availability"))

    success = (
        set(msg.services) <= set(availability.services)
        and availability.time_start <= msg.time_start
        and availability.time_end >= msg.time_start + msg.duration
        and msg.price <= availability.min_hourly_price * msg.duration
    )

    if success:
        availability.time_start = msg.time_start + msg.duration
        ctx.storage.set("availability", availability.dict())
        print(f"Accepted task and updated availability.")

    # send the response
    await ctx.send(sender, BookingResponse(success=success))