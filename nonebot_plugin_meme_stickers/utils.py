from nonebot import logger
from tenacity import RetryCallState, retry, stop_after_attempt, wait_fixed

from .config import config


def retry_log(x: RetryCallState):
    if not x.outcome:
        return
    if (e := x.outcome.exception()) is None:
        return
    logger.opt(exception=e).debug(
        f"Failed to fetch (attempt {x.attempt_number})",
    )


def request_retry(**kwargs):
    return retry(
        stop=stop_after_attempt(config.meme_stickers_retry_times),
        wait=wait_fixed(0.5),
        before_sleep=retry_log,
        **kwargs,
    )
