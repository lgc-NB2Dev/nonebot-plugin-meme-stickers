from nonebot import logger
from tenacity import RetryCallState, retry, stop_after_attempt, wait_fixed

from .config import config


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
