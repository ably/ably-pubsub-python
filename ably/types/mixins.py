import base64
import json
import logging

from ably.util.crypto import CipherData
from ably.util.exceptions import AblyException

log = logging.getLogger(__name__)

ENC_VCDIFF = "vcdiff"


class DeltaExtras:
    def __init__(self, extras):
        self.from_id = None
        if extras and 'delta' in extras:
            delta_info = extras['delta']
            if isinstance(delta_info, dict):
                self.from_id = delta_info.get('from')


class DecodingContext:
    def __init__(self, base_payload=None, last_message_id=None, vcdiff_decoder=None):
        self.base_payload = base_payload
        self.last_message_id = last_message_id
        self.vcdiff_decoder = vcdiff_decoder


class EncodeDataMixin:

    def __init__(self, encoding):
        self.encoding = encoding

    @property
    def encoding(self):
        return '/'.join(self._encoding_array).strip('/')

    @encoding.setter
    def encoding(self, encoding):
        if not encoding:
            self._encoding_array = []
        else:
            self._encoding_array = encoding.strip('/').split('/')

    @staticmethod
    def decode(data, encoding='', cipher=None, context=None):
        encoding = encoding.strip('/')
        encoding_list = encoding.split('/')

        last_payload = data

        while encoding_list:
            encoding = encoding_list.pop()
            if not encoding:
                # With messagepack, binary data is sent as bytes, without need
                # to specify the base64 encoding. Here we coerce to bytearray,
                # since that's what is used with the Json transport; though it
                # can be argued that it should be the other way, and use always
                # bytes, never bytearray.
                if type(data) is bytes:
                    data = bytearray(data)
                continue
            if encoding == 'json':
                if isinstance(data, bytes):
                    data = data.decode()
                if isinstance(data, list) or isinstance(data, dict):
                    continue
                data = json.loads(data)
            elif encoding == 'base64':
                data = bytearray(base64.b64decode(data)) if isinstance(data, bytes) \
                    else bytearray(base64.b64decode(data.encode('utf-8')))
                if not encoding_list:
                    last_payload = data
            elif encoding == ENC_VCDIFF:
                if not context or not context.vcdiff_decoder:
                    log.error('Message cannot be decoded as no VCDiff decoder available')
                    raise AblyException('VCDiff decoder not available', 40019, 40019)

                if not context.base_payload:
                    log.error('VCDiff decoding requires base payload')
                    raise AblyException('VCDiff decode failure', 40018, 40018)

                try:
                    # Convert base payload to bytes if it's a string
                    base_data = context.base_payload
                    if isinstance(base_data, str):
                        base_data = base_data.encode('utf-8')
                    else:
                        base_data = bytes(base_data)

                    # Convert delta to bytes if needed
                    delta_data = data
                    if isinstance(delta_data, (bytes, bytearray)):
                        delta_data = bytes(delta_data)
                    else:
                        delta_data = str(delta_data).encode('utf-8')

                    # Decode with VCDiff
                    data = bytearray(context.vcdiff_decoder.decode(delta_data, base_data))
                    last_payload = data

                except Exception as e:
                    log.error(f'VCDiff decode failed: {e}')
                    raise AblyException('VCDiff decode failure', 40018, 40018) from e

            elif encoding.startswith(f'{CipherData.ENCODING_ID}+'):
                if not cipher:
                    log.error('Message cannot be decrypted as the channel is '
                              'not set up for encryption & decryption')
                    encoding_list.append(encoding)
                    break
                data = cipher.decrypt(data)
            elif encoding == 'utf-8' and isinstance(data, (bytes, bytearray)):
                data = data.decode('utf-8')
            elif encoding == 'utf-8':
                pass
            else:
                log.error('Message cannot be decoded. '
                          f"Unsupported encoding type: '{encoding}'")
                encoding_list.append(encoding)
                break

        if context:
            context.base_payload = last_payload
        encoding = '/'.join(encoding_list)
        return {'encoding': encoding, 'data': data}

    @classmethod
    def from_encoded_array(cls, objs, cipher=None, context=None):
        if context is None:
            return [cls.from_encoded(obj, cipher=cipher) for obj in objs]

        # Decoding a message advances the context, and a batch that fails part way through is
        # discarded whole and replayed by the server, so the context is only kept if every
        # message in it decoded. Otherwise the replayed batch would decode against the base
        # payload left behind by its own first messages.
        base_payload, last_message_id = context.base_payload, context.last_message_id
        try:
            return [cls.from_encoded(obj, cipher=cipher, context=context) for obj in objs]
        except Exception:
            context.base_payload, context.last_message_id = base_payload, last_message_id
            raise
