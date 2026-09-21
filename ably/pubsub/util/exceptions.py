import functools
import logging

import msgpack

log = logging.getLogger(__name__)


class AblyException(Exception):
    def __new__(cls, message, status_code, code, cause=None):
        if cls == AblyException and status_code == 401:
            return AblyAuthException(message, status_code, code, cause)
        return super().__new__(cls, message, status_code, code, cause)

    def __init__(self, message, status_code, code, cause=None):
        super().__init__()
        self.message = message
        self.code = code
        self.status_code = status_code
        self.cause = cause

    def __str__(self):
        str = f'{self.code} {self.status_code} {self.message}'
        if self.cause is not None:
            str += f' (cause: {self.cause})'
        return str

    @property
    def is_server_error(self):
        return 500 <= self.status_code <= 599

    @staticmethod
    def raise_for_response(response):
        if 200 <= response.status_code < 300:
            # Valid response
            return

        try:
            decoded_response = AblyException.decode_error_response(response)
        except Exception:
            log.debug("Response not json or msgpack: %d %s",
                      response.status_code,
                      response.text)
            raise AblyException(message=response.text,
                                status_code=response.status_code,
                                code=response.status_code * 100) from None

        if decoded_response and 'error' in decoded_response:
            error = decoded_response['error']
            try:
                raise AblyException(
                    message=error['message'],
                    status_code=error['statusCode'],
                    code=int(error['code']),
                )
            except KeyError:
                msg = "Unexpected exception decoding server response: %s"
                msg = msg % response.text
                raise AblyException(message=msg, status_code=500, code=50000) from None

        raise AblyException(message="",
                            status_code=response.status_code,
                            code=response.status_code * 100)

    @staticmethod
    def decode_error_response(response):
        content_type = response.headers.get('content-type')
        if isinstance(content_type, str):
            if content_type.startswith('application/x-msgpack'):
                return msgpack.unpackb(response.content)
            elif content_type.startswith('application/json'):
                return response.json()

        raise ValueError("Unsupported content type")

    @staticmethod
    def from_exception(e):
        if isinstance(e, AblyException):
            return e
        exc_type = type(e).__name__
        exc_msg = str(e)
        if exc_msg:
            message = f"{exc_type}: {exc_msg}"
        else:
            message = exc_type
        return AblyException(f"Unexpected exception: {message}", 500, 50000)

    @staticmethod
    def from_dict(value: dict):
        return AblyException(value.get('message'), value.get('statusCode'), value.get('code'))


def catch_all(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            log.exception(e)
            raise AblyException.from_exception(e) from e

    return wrapper


class AblyAuthException(AblyException):
    pass


class IncompatibleClientIdException(AblyException):
    pass
