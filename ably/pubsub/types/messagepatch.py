"""Message patches (PSRFC-44): encoding them to send, decoding received ones, and applying them.

A patch changes part of a published message: data operations at JSON Pointer paths (``set``,
``append``, ``remove``), header operations, and operations Ably adds on the user claim and
privileged extras. A subscriber receives a ``message.patch`` and applies it to its own copy of the
message with :meth:`Message.apply_patch`, which gives the same result as Ably.

The applier follows ably-pubsub-js's ``messagepatch.ts``, which follows Ably's own implementation:
operations follow their path through decoded JSON values (dicts and lists), copying only the
containers along it, and are spliced into JSON text in a string or binary, so every character an
operation does not change is kept.
"""
import base64
import binascii
import json
from typing import Any, List, Optional

from ably.pubsub.util.exceptions import AblyException

SET = 'set'
APPEND = 'append'
REMOVE = 'remove'

_KNOWN_OPS = (SET, APPEND, REMOVE)
_END_OF_ARRAY = '-'

_REMEDIATION = ('Your copy of the message differs from the version the patch applies to: fetch the latest '
                'version with get_message(serial), and apply later patches to it.')
_UNKNOWN_REMEDIATION = ('The patch uses an operation this SDK does not know: fetch the latest version of the '
                        'message with get_message(serial), or update the SDK.')
_NOT_A_CONTAINER = 'a patch operation with a path requires the message data to be a JSON object or array'
_INVALID_DATA = 'the message data is not valid JSON'


# ---- Encoding a patch to send ----

def _encode_value(value, encoding: str, binary: bool) -> dict:
    # MPD3: a string unchanged, with its encoding (MPD3a); binary per RSL4c1/RSL4d1 (MPD3b); and any other
    # JSON value, including a number, boolean or null, as JSON text with the encoding json (MPD3c).
    if isinstance(value, str):
        return {'data': value, 'encoding': encoding} if encoding else {'data': value}
    if isinstance(value, (bytes, bytearray)):
        if binary:
            return {'data': bytes(value), 'encoding': encoding} if encoding else {'data': bytes(value)}
        return {'data': base64.b64encode(value).decode('ascii'), 'encoding': _join(encoding, 'base64')}
    try:
        text = json.dumps(value, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as e:
        raise AblyException(f'A patch value of type {type(value).__name__} cannot be sent as JSON: {e}',
                            400, 40013) from e
    return {'data': text, 'encoding': 'json'}


def _join(encoding: str, transform: str) -> str:
    return f'{encoding}/{transform}' if encoding else transform


# ---- Received patches ----

class _Absent:
    """The default of ``MessagePatchDataOperation.data``, which tells an operation without a value, such as a
    ``remove``, from one whose value is JSON ``null`` (``data=None``)."""

    def __repr__(self):
        return 'ABSENT'


_ABSENT = _Absent()


class MessagePatchDataOperation:
    """An operation that changes a message's data, or a value inside it (MPD2).

    - ``op``: ``'set'``, ``'append'`` or ``'remove'`` (or, on receipt, one this SDK does not know).
    - ``path``: a JSON Pointer (RFC 6901) to a value inside the data, such as ``'/content/0/text'``; ``None``
      for the whole of the data.
    - ``data``: the value the operation uses. To send, a ``str``, ``bytes``, or any JSON value: a dict, list,
      number, bool or ``None`` (JSON ``null``). Leave it out for an operation without a value, such as a
      ``remove``.
    - ``encoding``: the transforms applied to ``data``. Leave it out to send a raw value.

    On receipt the value is decoded as a message's data is, except that a JSON value is left as its JSON
    text, with the ``encoding`` ``'json'`` (MPD4a), so that it can be spliced into JSON text verbatim and
    parsed by the user into the type it changes. Binary is a ``bytearray``. A received operation can be sent
    again as it is.

    Example::

        MessagePatchDataOperation('append', path='/text', data=' world')
        MessagePatchDataOperation('set', path='/status', data={'done': True})
        MessagePatchDataOperation('remove', path='/draft')
    """

    def __init__(self, op: str, path: Optional[str] = None, data: Any = _ABSENT,
                 encoding: Optional[str] = None):
        self.__op = op
        self.__path = path
        self.__data = data
        self.__encoding = encoding or ''

    @property
    def op(self) -> str:
        return self.__op

    @property
    def path(self) -> Optional[str]:
        return self.__path

    @property
    def data(self) -> Any:
        """The value, or ``None`` if the operation has none."""
        return None if self.__data is _ABSENT else self.__data

    @property
    def has_data(self) -> bool:
        """Whether the operation has a value, which tells a JSON ``null`` from none."""
        return self.__data is not _ABSENT

    @property
    def encoding(self) -> str:
        """The transforms of the value not yet inverted: ``'json'`` for a received JSON value, empty for a
        decoded one or a raw value to send."""
        return self.__encoding

    def as_dict(self, binary: bool = False) -> dict:
        """The operation in its wire form, with its value encoded per MPD3. Values are never encrypted
        (MPD3e)."""
        entry = {'op': self.op}
        if self.path is not None:
            entry['path'] = self.path
        if self.has_data:  # MPD3d: without data, no data or encoding
            entry.update(_encode_value(self.__data, self.encoding, binary))
        return entry

    def __repr__(self):
        return (f'MessagePatchDataOperation(op={self.op!r}, path={self.path!r}, data={self.__data!r}, '
                f'encoding={self.encoding!r})')


class MessagePatchHeaderOperation:
    """An operation that changes a header in a message's ``extras.headers`` (MPH2): ``op``, ``'set'`` or
    ``'remove'``; the header ``key``; and, for ``set``, its new ``value``, a string, number or bool.

    Example: ``MessagePatchHeaderOperation('set', 'status', 'complete')``.
    """

    def __init__(self, op: str, key: str, value: Any = None):
        self.op = op
        self.key = key
        self.value = value

    def as_dict(self) -> dict:
        entry = {'op': self.op, 'key': self.key}
        if self.value is not None:
            entry['value'] = self.value
        return entry


class MessagePatchUserClaimOperation:
    """A received operation on the user claim, set by Ably (MPU2): ``op`` and the claim's new ``value``."""

    def __init__(self, op: str, value: Optional[str] = None):
        self.op = op
        self.value = value

    def as_dict(self) -> dict:
        entry = {'op': self.op}
        if self.value is not None:
            entry['value'] = self.value
        return entry


class MessagePatchPrivilegedOperation:
    """A received operation on the privileged extras, set by Ably (MPP2): ``op``, always ``'remove'``."""

    def __init__(self, op: str = REMOVE):
        self.op = op

    def as_dict(self) -> dict:
        return {'op': self.op}


class MessagePatchExtras:
    """The operations of a patch on the message's extras (MPA2b): ``headers``, applied in order, and the
    ``user_claim`` and ``privileged`` operations, which only Ably sets."""

    def __init__(self, headers: Optional[List[MessagePatchHeaderOperation]] = None,
                 user_claim: Optional[MessagePatchUserClaimOperation] = None,
                 privileged: Optional[MessagePatchPrivilegedOperation] = None):
        self.headers: List[MessagePatchHeaderOperation] = list(headers or [])
        self.user_claim: Optional[MessagePatchUserClaimOperation] = user_claim
        self.privileged: Optional[MessagePatchPrivilegedOperation] = privileged

    def as_dict(self) -> dict:
        result = {}
        if self.headers:
            result['headers'] = [op.as_dict() for op in self.headers]
        if self.user_claim is not None:
            result['userClaim'] = self.user_claim.as_dict()
        if self.privileged is not None:
            result['privileged'] = self.privileged.as_dict()
        return result


class MessagePatches:
    """The changes a ``MESSAGE_PATCH`` makes to a message (MPA2): ``data``, operations on its data applied in
    order, and ``extras``, operations on its extras, or ``None`` if it changes none. Set it as a message's
    ``patches`` to send it with ``patch_message``; a received patch carries one in ``message.patches``, and
    can be sent again as it is.

    Example::

        patches = MessagePatches(
            data=[MessagePatchDataOperation('append', path='/text', data=delta)],
            extras=MessagePatchExtras(headers=[MessagePatchHeaderOperation('set', 'status', 'complete')]),
        )
        await channel.patch_message(Message(serial=serial, patches=patches))
    """

    def __init__(self, data: Optional[List[MessagePatchDataOperation]] = None,
                 extras: Optional[MessagePatchExtras] = None):
        self.data: List[MessagePatchDataOperation] = list(data or [])
        self.extras: Optional[MessagePatchExtras] = extras

    def as_dict(self, binary: bool = False) -> dict:
        """The patch in its wire form, with each operation's value encoded per MPD3."""
        result = {}
        if self.data:
            result['data'] = [op.as_dict(binary) for op in self.data]
        if self.extras is not None:
            result['extras'] = self.extras.as_dict()
        return result

    @staticmethod
    def from_dict(obj) -> Optional['MessagePatches']:
        """Decodes the wire form of a received patch (MPD4)."""
        if not isinstance(obj, dict):
            return None
        return MessagePatches(
            data=[_decode_data_operation(op) for op in obj.get('data') or [] if isinstance(op, dict)],
            extras=_decode_extras(obj.get('extras')),
        )

    def apply_to_data(self, data):
        """Applies the data operations to JSON ``data`` kept outside a message: text (a ``str``), UTF-8
        bytes, or decoded JSON (a dict or list, copied only along each path). The result has the same
        form.

        :raises AblyException: with code 40000 if an operation cannot be applied.
        """
        result, _ = _apply_data(data, '', self.data)
        if _form(result) != _form(data):
            raise AblyException('Unable to apply the patch to the data: an operation without a path changed '
                                'what form the data has. Apply a patch that replaces the whole of the data to '
                                'a message, with Message.apply_patch', 400, 40000)
        if isinstance(data, bytes):
            return bytes(result)
        return result


def _form(data) -> str:
    """Whether data is JSON text, UTF-8 JSON bytes, or decoded JSON."""
    if isinstance(data, str):
        return 'text'
    if isinstance(data, (bytes, bytearray)):
        return 'binary'
    return 'json'


def _decode_extras(obj) -> Optional[MessagePatchExtras]:
    if not isinstance(obj, dict):
        return None
    user_claim = obj.get('userClaim')
    privileged = obj.get('privileged')
    return MessagePatchExtras(
        headers=[MessagePatchHeaderOperation(op.get('op') or '', op.get('key') or '', op.get('value'))
                 for op in obj.get('headers') or [] if isinstance(op, dict)],
        user_claim=MessagePatchUserClaimOperation(user_claim.get('op') or '', user_claim.get('value'))
        if isinstance(user_claim, dict) else None,
        privileged=MessagePatchPrivilegedOperation(privileged.get('op') or '')
        if isinstance(privileged, dict) else None,
    )


def _decode_data_operation(op: dict) -> MessagePatchDataOperation:
    # MPD4: the transforms of the encoding are inverted from the last, as RSL6a inverts a message's, except
    # that a first transform of json is left (MPD4a), and with no decryption or delta decoding (MPD4c). A
    # transform that cannot be inverted is left with every one before it, and the data as it is (RSL6b).
    data = op.get('data')
    if isinstance(data, bytes):
        data = bytearray(data)
    steps = [step for step in (op.get('encoding') or '').split('/') if step]
    while steps:
        step = steps[-1]
        if step == 'json' and len(steps) == 1:
            # MPD4a: JSON text, as a string. A JSON value MessagePack carried as itself is stringified.
            if isinstance(data, (bytes, bytearray)):
                try:
                    data = bytes(data).decode('utf-8')
                except UnicodeDecodeError:
                    pass
            elif isinstance(data, (dict, list)):
                data = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
            break
        try:
            if step == 'base64':
                raw = data if isinstance(data, (bytes, bytearray)) else data.encode('utf-8')
                data = bytearray(base64.b64decode(raw, validate=True))
            elif step == 'utf-8':
                if isinstance(data, (bytes, bytearray)):
                    data = bytes(data).decode('utf-8')
            elif step == 'json':
                text = bytes(data).decode('utf-8') if isinstance(data, (bytes, bytearray)) else data
                if isinstance(text, str):
                    data = json.loads(text)
            else:
                break
        except (binascii.Error, ValueError, TypeError, AttributeError):
            break
        steps.pop()
    return MessagePatchDataOperation(op.get('op') or '', op.get('path'), data if 'data' in op else _ABSENT,
                                     '/'.join(steps))


# ---- Applying ----

class _PatchError(Exception):
    """An operation that cannot be applied; the caller adds which one and why."""


def _fail(message: str):
    raise _PatchError(message)


def _patch_error(message: str, remediation: str) -> AblyException:
    return AblyException(f'{message}. {remediation}', 400, 40000)


def check_patch(serial, patch) -> None:
    """Checks that ``patch``, a received message, is a patch of the message ``serial``."""
    from ably.pubsub.types.message import MessageAction  # message.py imports this module

    if patch.action != MessageAction.MESSAGE_PATCH:
        action = patch.action.name if patch.action is not None else 'unknown'
        raise _patch_error(f'Unable to apply a {action} message as a patch: only a message.patch can be applied',
                           'Apply only messages whose action is MessageAction.MESSAGE_PATCH; replace your copy '
                           'with any other')
    if serial != patch.serial:
        raise _patch_error(f'Unable to apply a patch to message {serial}: the patch is for message {patch.serial}',
                           "Look up your copy of the message with the patch's serial")


def apply_to_message_fields(data, encoding: str, extras, patches: Optional[MessagePatches]):
    """The data, remaining encoding and extras of a message once ``patches`` are applied."""
    if patches is None:
        return data, encoding, extras
    data, encoding = _apply_data(data, encoding, patches.data)
    return data, encoding, _apply_extras(extras, patches)


def _apply_data(data, encoding: str, ops: List[MessagePatchDataOperation]):
    for index, op in enumerate(ops):
        try:
            if op.op not in _KNOWN_OPS:
                _unknown_operation(op)
            if op.path:
                data = _apply_at_path(data, op, op.path)
            elif op.op == SET:
                data, encoding = _set_whole(op)
            else:
                data, encoding = _apply_to_whole(data, encoding, op)
        except _PatchError as e:
            where = _quote(op.path or '')
            raise _patch_error(f'Unable to apply data patch operation {index} ({op.op} at {where}): {e}',
                               _REMEDIATION) from None
    return data, encoding


def _set_whole(op):
    # TM9f2a: a JSON value must be an object or array, and is decoded, as a message.update's data would be;
    # any other value replaces the data with its encoding.
    if op.encoding == 'json':
        value = _json_value(op)
        if not isinstance(value, (dict, list)):
            _fail('a set patch operation without a path requires a JSON value that is an object or array')
        return value, ''
    return op.data, op.encoding


def _apply_to_whole(data, encoding, op):
    value = op.data
    if op.op == APPEND:
        if op.encoding:
            _fail('an append patch operation requires a string or binary value with no encoding')
        # TM9f2b: as with message.append, appending to no data gives the value.
        if data is None and isinstance(value, (str, bytes, bytearray)):
            return value, ''
        # TM9f2c
        if isinstance(data, str) and isinstance(value, str) and not encoding:
            return data + value, ''
        if isinstance(data, (bytes, bytearray)) and isinstance(value, (bytes, bytearray)) and not encoding:
            return bytearray(data) + value, ''
        _fail('an append patch operation without a path requires the message data and the operation data to '
              'both be strings or both be binary')
    # TM9f2d
    _fail('a remove patch operation requires a path')


def _apply_at_path(data, op, path):
    if op.encoding and op.encoding != 'json':
        # MPD4c leaves a value this SDK cannot decode with its encoding: there is no value to apply.
        _fail(f'its value has the encoding {op.encoding}, which this SDK cannot decode')
    if isinstance(data, str):
        return _JsonText.apply(data, op, path)
    if isinstance(data, (bytes, bytearray)):
        try:
            text = bytes(data).decode('utf-8')
        except UnicodeDecodeError:
            _fail(_INVALID_DATA)
        return bytearray(_JsonText.apply(text, op, path).encode('utf-8'))
    if isinstance(data, (dict, list)):
        return _apply_at(data, _parse_path(path), 0, op, path)
    _fail(_NOT_A_CONTAINER)


def _apply_at(container, tokens, index, op, path):
    # Copies each dict and list on the path, and returns the new container.
    token = tokens[index]
    if index < len(tokens) - 1:
        # Every token but the last locates the target.
        if isinstance(container, list):
            i = _parse_index(token)
            if i < 0 or i >= len(container):
                _fail(_path_not_found(path))
            copy = list(container)
            copy[i] = _apply_at(_require_container(container[i], path), tokens, index + 1, op, path)
            return copy
        if isinstance(container, dict):
            if token not in container:
                _fail(_path_not_found(path))
            copy = dict(container)
            copy[token] = _apply_at(_require_container(container[token], path), tokens, index + 1, op, path)
            return copy
        _fail(_parent_not_container(path))
    if isinstance(container, list):
        return _update_list(container, token, op, path)
    if isinstance(container, dict):
        return _update_dict(container, token, op, path)
    _fail(_parent_not_container(path))


def _require_container(value, path):
    if not isinstance(value, (dict, list)):
        _fail(_parent_not_container(path))
    return value


def _update_list(array, token, op, path):
    elements = list(array)
    if token == _END_OF_ARRAY:
        if op.op != SET:
            _fail(_end_of_array_not_set(op, path))
        elements.append(_tree_value(op))
        return elements
    i = _parse_index(token)
    if i < 0 or i >= len(elements):
        _fail(_path_not_found(path))
    if op.op == SET:
        elements[i] = _tree_value(op)
    elif op.op == APPEND:
        elements[i] = _append_string(elements[i], op, path)
    elif op.op == REMOVE:
        del elements[i]
    else:
        _unknown_operation(op)
    return elements


def _update_dict(obj, key, op, path):
    fields = dict(obj)
    if op.op == SET:
        fields[key] = _tree_value(op)
    elif op.op == APPEND:
        if key not in fields:
            _fail(_path_not_found(path))
        fields[key] = _append_string(fields[key], op, path)
    elif op.op == REMOVE:
        if key not in fields:
            _fail(_path_not_found(path))
        del fields[key]
    else:
        _unknown_operation(op)
    return fields


def _append_string(value, op, path):
    if not isinstance(value, str):
        _fail(f'unable to append at path {_quote(path)}: the value there is not a string')
    _require_string_value(op)
    return value + op.data


def _require_string_value(op):
    # TM9f3f
    if not isinstance(op.data, str) or op.encoding:
        _fail('an append patch operation with a path requires data that is a string, with no encoding')


def _tree_value(op):
    # TM9f3h: the value an operation sets, as a decoded JSON value: binary as base64, as JSON holds it.
    if op.encoding == 'json':
        return _json_value(op)
    if isinstance(op.data, (bytes, bytearray)):
        return base64.b64encode(op.data).decode('ascii')
    return op.data


def _json_text_of(op) -> str:
    """The JSON text of an operation whose encoding is json (MPD4a)."""
    data = op.data
    if isinstance(data, (bytes, bytearray)):
        try:
            data = bytes(data).decode('utf-8')
        except UnicodeDecodeError:
            data = None
    if not isinstance(data, str):
        _fail('its JSON value is not JSON text')
    return data


def _json_value(op):
    """The JSON value that an operation whose encoding is json represents."""
    try:
        return json.loads(_json_text_of(op))
    except ValueError:
        _fail('its JSON value is not valid JSON')


def _apply_extras(extras, patches: MessagePatches):
    if patches.extras is None:
        return extras
    result = _apply_headers(extras, patches.extras.headers)
    result = _apply_user_claim(result, patches.extras.user_claim)
    return _apply_privileged(result, patches.extras.privileged)


def _apply_headers(extras, ops):
    if not ops:
        return extras
    headers = dict((extras or {}).get('headers') or {})
    for index, op in enumerate(ops):
        if op.op == SET:
            headers[op.key] = op.value
        elif op.op == REMOVE:
            if op.key not in headers:
                raise _patch_error(f'Unable to apply header patch operation {index} (remove of {_quote(op.key)}): '
                                   'the header does not exist', _REMEDIATION)
            del headers[op.key]
        else:
            raise _patch_error(f'Unable to apply header patch operation {index}: unknown operation '
                               f'{_quote(op.op)}', _UNKNOWN_REMEDIATION)
    result = dict(extras or {})
    result['headers'] = headers
    return result


def _apply_user_claim(extras, op):
    # Unlike a header, removing a claim the message does not have succeeds.
    if op is None:
        return extras
    rest = {k: v for k, v in (extras or {}).items() if k != 'userClaim'}
    if op.op == SET:
        rest['userClaim'] = op.value
        return rest
    if op.op == REMOVE:
        # TM9g4
        return rest or None
    raise _patch_error(f'Unable to apply the user claim patch operation: unknown operation {_quote(op.op)}',
                       _UNKNOWN_REMEDIATION)


def _apply_privileged(extras, op):
    # Removing privileged extras the message does not have succeeds.
    if op is None:
        return extras
    if op.op != REMOVE:
        raise _patch_error('Unable to apply the privileged extras patch operation: unknown operation '
                           f'{_quote(op.op)}', _UNKNOWN_REMEDIATION)
    rest = {k: v for k, v in (extras or {}).items() if k != 'privileged'}
    return rest or None


def _unknown_operation(op):
    _fail(f'unknown message patch operation {_quote(op.op)}')


def _end_of_array_not_set(op, path):
    return f'unable to {op.op} at path {_quote(path)}: "-" can only be used to set a new array element'


def _path_not_found(path):
    return f'path {_quote(path)} does not exist in the message data'


def _parent_not_container(path):
    return f'unable to apply a patch operation at path {_quote(path)}: its parent is not an object or array'


def _parse_path(path: str) -> List[str]:
    """A path's tokens, unescaped (RFC 6901)."""
    invalid = (f'invalid path {_quote(path)}: a patch operation path must be a JSON Pointer, such as '
               '/content/0/text')
    if not path or path[0] != '/':
        _fail(invalid)
    for i, c in enumerate(path):
        if c == '~' and (i + 1 >= len(path) or path[i + 1] not in '01'):
            _fail(invalid)
    return [token.replace('~1', '/').replace('~0', '~') for token in path[1:].split('/')]


def _parse_index(token: str) -> int:
    """An array index token, decimal digits without leading zeros (RFC 6901), or -1 if it is not one."""
    if not token or (len(token) > 1 and token[0] == '0') or any(c not in '0123456789' for c in token):
        return -1
    return int(token)


def _quote(s: str) -> str:
    """A string as JSON, escaped as Ably escapes it: ``"``, ``\\`` and control characters, and no others. Ably
    replaces invalid UTF-8 with U+FFFD, as a lone surrogate becomes here."""
    out = ['"']
    for c in s:
        if c == '"':
            out.append('\\"')
        elif c == '\\':
            out.append('\\\\')
        elif c == '\n':
            out.append('\\n')
        elif c == '\r':
            out.append('\\r')
        elif c == '\t':
            out.append('\\t')
        elif c == '\b':
            out.append('\\b')
        elif c == '\f':
            out.append('\\f')
        elif c < ' ':
            out.append(f'\\u{ord(c):04x}')
        elif '\ud800' <= c <= '\udfff':
            out.append('�')  # a lone surrogate: Python strings hold pairs as one character
        else:
            out.append(c)
    out.append('"')
    return ''.join(out)


class _Loc:
    def __init__(self, open_at):
        self.open = open_at
        self.found = False
        self.start = 0  # the start of the member's key, or of the element
        self.val_start = 0
        self.val_end = 0
        self.prev_end = -1  # the end of the previous value, or -1 if this is the first
        self.next_start = -1  # the start of the next member or element, or -1 if this is the last
        self.last_end = -1  # when not found, the end of the last value, or -1 if the container is empty


class _JsonText:
    """JSON text, edited by splicing. Every character that delimits JSON is ASCII, so indices into a Python
    string locate values as byte offsets do in Ably's implementation."""

    @staticmethod
    def apply(doc: str, op, path: str) -> str:
        if op.op == SET:
            return _JsonText._set(doc, path, _JsonText._json_text(op))
        if op.op == APPEND:
            _require_string_value(op)
            _, loc = _JsonText._locate(doc, path, op.op)
            if not loc.found:
                _fail(_path_not_found(path))
            if doc[loc.val_start] != '"':
                _fail(f'unable to append at path {_quote(path)}: the value there is not a string')
            at = loc.val_end - 1  # just before the closing quote
            return doc[:at] + _quote(op.data)[1:-1] + doc[at:]
        if op.op == REMOVE:
            _, loc = _JsonText._locate(doc, path, op.op)
            if not loc.found:
                _fail(_path_not_found(path))
            if loc.next_start >= 0:
                return doc[:loc.start] + doc[loc.next_start:]
            if loc.prev_end >= 0:
                # The last of several: remove the comma before it.
                return doc[:loc.prev_end] + doc[loc.val_end:]
            return doc[:loc.start] + doc[loc.val_end:]
        _unknown_operation(op)

    @staticmethod
    def _json_text(op) -> str:
        # TM9f5a: the operation's value as JSON text: a JSON value verbatim, once it is known to be valid, a
        # string quoted, binary as base64, and a JSON value MessagePack carried without an encoding as JSON.
        if op.encoding == 'json':
            _json_value(op)
            return _json_text_of(op)
        if isinstance(op.data, str):
            return _quote(op.data)
        if isinstance(op.data, (bytes, bytearray)):
            return _quote(base64.b64encode(op.data).decode('ascii'))
        return json.dumps(op.data, separators=(',', ':'), ensure_ascii=False)

    @staticmethod
    def _set(doc, path, value):
        target, loc = _JsonText._locate(doc, path, SET)
        if loc.found:
            return doc[:loc.val_start] + value + doc[loc.val_end:]
        # A new member or element, after the last one.
        insertion = ',' if loc.last_end >= 0 else ''
        if doc[target] == '{':
            insertion += _quote(_parse_path(path)[-1]) + ':'
        insertion += value
        at = loc.last_end if loc.last_end >= 0 else loc.open
        return doc[:at] + insertion + doc[at:]

    @staticmethod
    def _locate(doc, path, op):
        # The start of the object or array holding the value at path, and the value's location in it.
        start = _JsonText._skip_ws(doc, 0)
        if start >= len(doc) or doc[start] not in '{[':
            _fail(_NOT_A_CONTAINER)
        tokens = _parse_path(path)
        last = tokens[-1]
        target = start
        for token in tokens[:-1]:
            if doc[target] == '{':
                loc = _JsonText._find_member(doc, target, token, full=False)
            elif doc[target] == '[':
                i = _parse_index(token)
                if i < 0:
                    _fail(_path_not_found(path))
                loc = _JsonText._find_element(doc, target, i, full=False)
            else:
                _fail(_path_not_found(path))
            if not loc.found:
                _fail(_path_not_found(path))
            target = loc.val_start
        if doc[target] not in '{[':
            _fail(_parent_not_container(path))
        if doc[target] == '{':
            return target, _JsonText._find_member(doc, target, last, full=True)
        if last == _END_OF_ARRAY:
            if op != SET:
                _fail(f'unable to {op} at path {_quote(path)}: "-" can only be used to set a new array element')
            return target, _JsonText._find_element(doc, target, -1, full=True)
        index = _parse_index(last)
        if index < 0:
            _fail(_path_not_found(path))
        loc = _JsonText._find_element(doc, target, index, full=True)
        if not loc.found:
            _fail(_path_not_found(path))
        return target, loc

    @staticmethod
    def _find_member(doc, start, key, full):
        # Locates the member `key` in the object at doc[start], scanning past its value only if `full`.
        loc = _Loc(start + 1)
        i = start + 1
        while True:
            i = _JsonText._skip_ws(doc, i)
            if i >= len(doc):
                _fail(_INVALID_DATA)
            if doc[i] == '}' and loc.last_end < 0:
                return loc
            if doc[i] != '"':
                _fail(_INVALID_DATA)
            key_start = i
            key_end = _JsonText._skip_string(doc, i)
            match = _JsonText._key_equals(doc[i + 1:key_end - 1], key)
            i = _JsonText._skip_ws(doc, key_end)
            if i >= len(doc) or doc[i] != ':':
                _fail(_INVALID_DATA)
            val_start = _JsonText._skip_ws(doc, i + 1)
            if val_start >= len(doc):
                _fail(_INVALID_DATA)
            if match and not full:
                loc.found = True
                loc.val_start = val_start
                return loc
            val_end = _JsonText._skip_value(doc, val_start)
            i = _JsonText._skip_ws(doc, val_end)
            if i >= len(doc):
                _fail(_INVALID_DATA)
            if match:
                loc.found = True
                loc.start = key_start
                loc.val_start = val_start
                loc.val_end = val_end
                loc.prev_end = loc.last_end
                if doc[i] == ',':
                    loc.next_start = _JsonText._skip_ws(doc, i + 1)
                return loc
            loc.last_end = val_end
            if doc[i] == ',':
                i += 1
            elif doc[i] == '}':
                return loc
            else:
                _fail(_INVALID_DATA)

    @staticmethod
    def _find_element(doc, start, index, full):
        # Locates element `index` of the array at doc[start], scanning past it only if `full`. An index of -1
        # finds none, and so locates the end of the array.
        loc = _Loc(start + 1)
        i = _JsonText._skip_ws(doc, start + 1)
        if i >= len(doc):
            _fail(_INVALID_DATA)
        if doc[i] == ']':
            return loc
        n = 0
        while True:
            val_start = i
            if val_start >= len(doc):
                _fail(_INVALID_DATA)
            if n == index and not full:
                loc.found = True
                loc.val_start = val_start
                return loc
            val_end = _JsonText._skip_value(doc, i)
            i = _JsonText._skip_ws(doc, val_end)
            if i >= len(doc):
                _fail(_INVALID_DATA)
            if n == index:
                loc.found = True
                loc.start = val_start
                loc.val_start = val_start
                loc.val_end = val_end
                loc.prev_end = loc.last_end
                if doc[i] == ',':
                    loc.next_start = _JsonText._skip_ws(doc, i + 1)
                return loc
            loc.last_end = val_end
            if doc[i] == ',':
                i = _JsonText._skip_ws(doc, i + 1)
            elif doc[i] == ']':
                return loc
            else:
                _fail(_INVALID_DATA)
            n += 1

    @staticmethod
    def _key_equals(raw, key):
        # Compares a raw, still escaped, JSON object key with a decoded key.
        if '\\' not in raw:
            return raw == key
        try:
            return json.loads('"' + raw + '"') == key
        except ValueError:
            return False

    @staticmethod
    def _skip_ws(doc, start):
        i = start
        while i < len(doc) and doc[i] in ' \t\n\r':
            i += 1
        return i

    @staticmethod
    def _skip_value(doc, start):
        # The index just past the value at doc[start].
        if start >= len(doc):
            _fail(_INVALID_DATA)
        c = doc[start]
        if c == '"':
            return _JsonText._skip_string(doc, start)
        if c in '{[':
            return _JsonText._skip_container(doc, start)
        # A number, true, false or null.
        j = start
        while j < len(doc) and doc[j] not in ',}] \t\n\r':
            j += 1
        if j == start:
            _fail(_INVALID_DATA)
        return j

    @staticmethod
    def _skip_string(doc, start):
        # The index just past the string at doc[start].
        j = start + 1
        while True:
            q = doc.find('"', j)
            if q < 0:
                _fail(_INVALID_DATA)
            # The quote is escaped if an odd number of backslashes precede it.
            backslashes = 0
            p = q - 1
            while p > start and doc[p] == '\\':
                backslashes += 1
                p -= 1
            if backslashes % 2 == 0:
                return q + 1
            j = q + 1

    @staticmethod
    def _skip_container(doc, start):
        # The index just past the object or array at doc[start].
        depth = 0
        j = start
        while j < len(doc):
            c = doc[j]
            if c == '"':
                j = _JsonText._skip_string(doc, j) - 1
            elif c in '{[':
                depth += 1
            elif c in '}]':
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
        _fail(_INVALID_DATA)
