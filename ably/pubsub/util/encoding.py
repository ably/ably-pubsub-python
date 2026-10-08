import base64
import json
from typing import Any

from ably.pubsub.util.crypto import CipherData
from ably.pubsub.util.exceptions import AblyException


def encode_data(data: Any, encoding_array: list, binary: bool = False):
    encoding = encoding_array[:]

    if isinstance(data, (dict, list)):
        encoding.append('json')
        data = json.dumps(data)  # json.dumps already returns str
    elif isinstance(data, str) and not binary:
        pass
    elif not binary and isinstance(data, (bytearray, bytes)):
        data = base64.b64encode(data).decode('ascii')
        encoding.append('base64')
    elif isinstance(data, CipherData):
        encoding.append(data.encoding_str)
        if not binary:
            data = base64.b64encode(data.buffer).decode('ascii')
            encoding.append('base64')
        else:
            data = data.buffer
    elif binary and isinstance(data, bytearray):
        data = bytes(data)

    result = { 'data': data }

    if not (isinstance(data, (bytes, str, list, dict, bytearray)) or data is None):
        raise AblyException("Invalid data payload", 400, 40011)

    if encoding:
        result['encoding'] = '/'.join(encoding).strip('/')

    return result
