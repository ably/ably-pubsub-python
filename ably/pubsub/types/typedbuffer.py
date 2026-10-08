# This functionality is depreceated and will be removed
# Message Pack is the replacement for all binary data messages

import json
import struct


class DataType:
    NONE = 0
    TRUE = 1
    FALSE = 2
    INT32 = 3
    INT64 = 4
    DOUBLE = 5
    STRING = 6
    BUFFER = 7
    JSONARRAY = 8
    JSONOBJECT = 9


class Limits:
    INT32_MAX = 2 ** 31
    INT32_MIN = -(2 ** 31 + 1)
    INT64_MAX = 2 ** 63
    INT64_MIN = - (2 ** 63 + 1)


_decoders = {DataType.TRUE: lambda b: True,
             DataType.FALSE: lambda b: False,
             DataType.INT32: lambda b: struct.unpack('>i', b)[0],
             DataType.INT64: lambda b: struct.unpack('>q', b)[0],
             DataType.DOUBLE: lambda b: struct.unpack('>d', b)[0],
             DataType.STRING: lambda b: b.decode('utf-8'),
             DataType.BUFFER: lambda b: b,
             DataType.JSONARRAY: lambda b: json.loads(b.decode('utf-8')),
             DataType.JSONOBJECT: lambda b: json.loads(b.decode('utf-8'))}


class TypedBuffer:
    def __init__(self, buffer, type):
        self.__buffer = buffer
        self.__type = type

    def __eq__(self, other):
        if isinstance(other, TypedBuffer):
            return self.buffer == other.buffer and self.type == other.type
        return NotImplemented

    def __ne__(self, other):
        if isinstance(other, TypedBuffer):
            result = self.__eq__(other)
            if result != NotImplemented:
                return not result
        return NotImplemented

    @staticmethod
    def from_obj(obj):
        if isinstance(obj, TypedBuffer):
            return obj
        elif isinstance(obj, (bytes, bytearray)):
            data_type = DataType.BUFFER
            buffer = obj
        elif isinstance(obj, str):
            data_type = DataType.STRING
            buffer = obj.encode('utf-8')
        elif isinstance(obj, bool):
            data_type = DataType.TRUE if obj else DataType.FALSE
            buffer = None
        elif isinstance(obj, int):
            if Limits.INT32_MIN <= obj <= Limits.INT32_MAX:
                data_type = DataType.INT32
                buffer = struct.pack('>i', obj)
            elif Limits.INT64_MIN <= obj <= Limits.INT64_MAX:
                data_type = DataType.INT64
                buffer = struct.pack('>q', obj)
            else:
                raise ValueError(f'Number too large {obj}')
        elif isinstance(obj, float):
            data_type = DataType.DOUBLE
            buffer = struct.pack('>d', obj)
        elif isinstance(obj, list):
            data_type = DataType.JSONARRAY
            buffer = json.dumps(obj, separators=(',', ':')).encode('utf-8')
        elif isinstance(obj, dict):
            data_type = DataType.JSONOBJECT
            buffer = json.dumps(obj, separators=(',', ':')).encode('utf-8')
        else:
            raise TypeError(f'Unexpected object type {type(obj)}')

        return TypedBuffer(buffer, data_type)

    @property
    def buffer(self):
        return self.__buffer

    @property
    def type(self):
        return self.__type

    def decode(self):
        decoder = _decoders.get(self.type)
        if decoder is not None:
            return decoder(self.buffer)
        raise ValueError(f'Unsupported data type {self.type}')
