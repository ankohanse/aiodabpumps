from datetime import datetime
import logging

from dataclasses import dataclass
from enum import StrEnum


_LOGGER = logging.getLogger(__name__)


class DabPumpsUserRole(StrEnum):
    CUSTOMER = "CUSTOMER"
    INSTALLER = "INSTALLER"

class DabPumpsParamType(StrEnum):
    ENUM = "enum"
    MEASURE = "measure"
    LABEL = "label"


@dataclass
class DabPumpsInstall:
    id: str
    name: str
    description: str
    company: str
    address: str
    role: DabPumpsUserRole
    devices: int


@dataclass
class DabPumpsDevice:
    id: str
    serial: str
    name: str
    vendor: str
    product: str
    hw_version: str
    sw_version: str
    mac_address: str
    config_id: str
    install_id: str


@dataclass
class DabPumpsParams:
    key: str
    type: DabPumpsParamType
    unit: str
    weight: float|None
    values: dict[str,str]|None
    min: float|None
    max: float|None
    family: str
    group: str
    view: str
    change: str
    log: str
    report: str


@dataclass
class DabPumpsConfig:
    id: str
    label: str
    description: str
    meta_params: dict[str, DabPumpsParams]


@dataclass
class DabPumpsStatus:
    serial: str
    key: str
    name: str
    code: str
    value: str
    unit: str
    status_ts: datetime|None
    update_ts: datetime|None


