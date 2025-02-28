import hashlib
import json
from pathlib import Path
from typing import TypeVar

from cookit import copy_func_arg_annotations
from cookit.pyd import type_dump_python
from nonebot import logger
from tenacity import RetryCallState, retry, stop_after_attempt, wait_fixed

from ..config import config

N = TypeVar("N", int, float)


def op_retry(log_message: str = "Operation failed", **kwargs):
    def retry_log(x: RetryCallState):
        if not x.outcome:
            return
        if (e := x.outcome.exception()) is None:
            return
        logger.warning(
            f"{log_message}"
            f" (attempt {x.attempt_number} / {config.retry_times})"
            f": {type(e).__name__}: {e}",
        )
        logger.opt(exception=e).debug("Stacktrace")

    return retry(
        **{
            "stop": stop_after_attempt(config.retry_times),
            "wait": wait_fixed(0.5),
            "before_sleep": retry_log,
            "reraise": True,
            **kwargs,
        },
    )


def format_error(e: BaseException):
    return f"{type(e).__name__}: {e}"


def resolve_relative_num(val: str, base: N) -> N:
    base_type = type(base)
    if not val.startswith("^"):
        return base_type(val)
    return base + base_type(val.lstrip("^"))


def calc_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def calc_checksum_from_file(path: Path) -> str:
    return calc_checksum(path.read_bytes())


@copy_func_arg_annotations(type_dump_python)
def dump_readable_model(data: object, **type_dump_kw) -> str:
    return json.dumps(
        type_dump_python(data, **type_dump_kw),
        indent=2,
        ensure_ascii=False,
    )
