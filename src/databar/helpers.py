from functools import lru_cache, wraps
from time import monotonic_ns
from typing import Any, Dict, List, NamedTuple

from requests import HTTPError, Response
from requests.utils import guess_json_utf


def timed_lru_cache(
    _func=None, *, seconds: int = 300, maxsize: int = 128, typed: bool = False
):
    """Extension of functools lru_cache with a timeout

    Parameters:
    seconds (int): Timeout in seconds to clear the WHOLE cache, default = 10 minutes
    maxsize (int): Maximum Size of the Cache
    typed (bool): Same value of different type will be a different entry

    """

    def wrapper_cache(f):
        f = lru_cache(maxsize=maxsize, typed=typed)(f)
        f.delta = seconds * 10**9
        f.expiration = monotonic_ns() + f.delta

        @wraps(f)
        def wrapped_f(*args, **kwargs):
            if monotonic_ns() >= f.expiration:
                f.cache_clear()
                f.expiration = monotonic_ns() + f.delta
            return f(*args, **kwargs)

        wrapped_f.cache_info = f.cache_info  # type: ignore
        wrapped_f.cache_clear = f.cache_clear  # type: ignore
        return wrapped_f

    # To allow decorator to be used without arguments
    if _func is None:
        return wrapper_cache
    else:
        return wrapper_cache(_func)


def raise_for_status(response: Response):
    """Raises :class:`HTTPError`, if one occurred."""
    if 400 <= response.status_code < 600:
        reason = None
        content = response.content
        if content is not None:
            try:
                reason = content.decode(guess_json_utf(content))
            except UnicodeDecodeError:
                pass

        if not reason:
            if isinstance(response.reason, bytes):
                # We attempt to decode utf-8 first because some servers
                # choose to localize their reason strings. If the string
                # isn't utf-8, we fall back to iso-8859-1 for all other
                # encodings. (See PR #3538)
                try:
                    reason = response.reason.decode("utf-8")
                except UnicodeDecodeError:
                    reason = response.reason.decode("iso-8859-1")
            else:
                reason = response.reason

        http_error_msg = "Status code is %s. Got error while requesting: %s" % (
            response.status_code,
            reason,
        )

        raise HTTPError(http_error_msg, response=response)


class PaginatedResponse(NamedTuple):
    """
    Result of request where pagination is used.

    :param page: Requested page number.
    :param has_next_page: Boolean field to determine if there are more data.
    :param data: Result of request. List of api-keys|tables.
    """

    page: int
    has_next_page: bool
    data: List[Dict[str, Any]]
