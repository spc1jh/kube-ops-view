import requests.exceptions
import urllib3.exceptions
from kubernetes.client.exceptions import ApiException

# exceptions which indicate a failed HTTP request (no need to log a stack trace)
HTTP_ERRORS = (
    requests.exceptions.RequestException,
    urllib3.exceptions.HTTPError,
    ApiException,
)


def get_short_error_message(e: Exception):
    """Generate a reasonable short message why the HTTP request failed."""

    if isinstance(e, ApiException):
        # e.g. "401 Unauthorized"
        return "{} {}".format(e.status, e.reason)
    elif isinstance(e, requests.exceptions.RequestException) and e.response is not None:
        # e.g. "401 Unauthorized"
        return "{} {}".format(e.response.status_code, e.response.reason)
    elif isinstance(
        e, (requests.exceptions.ConnectionError, urllib3.exceptions.HTTPError)
    ):
        # e.g. "ConnectionError" or "ConnectTimeout"
        return e.__class__.__name__
    else:
        return str(e)
