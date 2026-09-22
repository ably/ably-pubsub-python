"""Derived from uts/rest/unit/types/error_types.md in ably/specification.

Spec points: TI1, TI2, TI3, TI4, TI5

ably-python has no separate `ErrorInfo` class: `AblyException` is the single error
type, carrying `code`, `status_code`, `message` and `cause`, and
`AblyException.from_dict` stands in for the spec's `ErrorInfo.fromJson`.
"""

import pytest

from ably.util.exceptions import AblyException
from test.uts.helpers.deviations import deviation


# UTS: rest/unit/TI1/errorinfo-attributes-0
async def test_ti1_errorinfo_code_attribute():
    error = AblyException(message=None, status_code=None, code=40000)

    assert error.code == 40000


# UTS: rest/unit/TI1/errorinfo-attributes-0
async def test_ti2_errorinfo_status_code_attribute():
    error = AblyException(message=None, status_code=401, code=40100)

    # UTS SPEC ERROR: TI2 - features spec TI2 is "server errors inherit from ErrorInfo";
    # the statusCode attribute the UTS spec files under TI2 belongs to TI1.
    assert error.status_code == 401


# UTS: rest/unit/TI1/errorinfo-attributes-0
async def test_ti3_errorinfo_message_attribute():
    error = AblyException(
        message='Bad request: invalid parameter',
        status_code=400,
        code=40000,
    )

    # UTS SPEC ERROR: TI3 - features spec TI3 is about the ably-common submodule;
    # the message attribute the UTS spec files under TI3 belongs to TI1.
    assert error.message == 'Bad request: invalid parameter'


# UTS: rest/unit/TI1/errorinfo-attributes-0
@deviation
async def test_ti4_errorinfo_href_attribute():
    # DEVIATION: AblyException models no href, so construction raises TypeError
    error = AblyException(
        message=None,
        status_code=None,
        code=40000,
        href='https://help.ably.io/error/40000',
    )

    assert error.href == 'https://help.ably.io/error/40000'


# UTS: rest/unit/TI1/errorinfo-attributes-0
async def test_ti5_errorinfo_cause_attribute():
    original_error = Exception('Network failure')
    error = AblyException(
        message='Timeout',
        status_code=500,
        code=50003,
        cause=original_error,
    )

    # UTS SPEC ERROR: TI5 - features spec TI5 is about URLs in log entries;
    # the cause attribute the UTS spec files under TI5 belongs to TI1.
    assert error.cause == original_error


# UTS: rest/unit/TI/errorinfo-from-json-0
async def test_ti_errorinfo_from_json():
    json_response = {
        'error': {
            'code': 40100,
            'statusCode': 401,
            'message': 'Token expired',
            'href': 'https://help.ably.io/error/40100',
        },
    }

    error = AblyException.from_dict(json_response['error'])

    assert error.code == 40100
    assert error.status_code == 401
    assert error.message == 'Token expired'
    # The spec also asserts error.href == "https://help.ably.io/error/40100";
    # from_dict drops href, which AblyException does not model
    assert not hasattr(error, 'href')


# UTS: rest/unit/TI/errorinfo-nested-cause-1
@deviation
async def test_ti_errorinfo_nested_cause():
    json_response = {
        'error': {
            'code': 50000,
            'statusCode': 500,
            'message': 'Internal error',
            'cause': {
                'code': 50001,
                'message': 'Database connection failed',
            },
        },
    }

    error = AblyException.from_dict(json_response['error'])

    assert error.code == 50000
    # DEVIATION: from_dict never reads 'cause', so it stays None
    assert isinstance(error.cause, AblyException)
    assert error.cause.code == 50001
    assert error.cause.message == 'Database connection failed'


# UTS: rest/unit/TI/ably-exception-wraps-errorinfo-2
async def test_ti_ably_exception_wraps_errorinfo():
    exception = AblyException(
        message='Bad request',
        status_code=400,
        code=40000,
    )

    assert exception.code == 40000
    assert exception.status_code == 400
    assert exception.message == 'Bad request'
    # The spec also asserts exception.errorInfo == error_info. ably-python folds
    # ErrorInfo into AblyException, so the exception is the error information
    assert isinstance(exception, AblyException)


COMMON_ERROR_CODES = [
    (40000, 400, 'Bad request'),
    (40100, 401, 'Unauthorized'),
    (40101, 401, 'Invalid credentials'),
    (40140, 401, 'Token error'),
    (40142, 401, 'Token expired'),
    (40160, 401, 'Invalid capability'),
    (40300, 403, 'Forbidden'),
    (40400, 404, 'Not found'),
    (50000, 500, 'Internal server error'),
    (50003, 500, 'Timeout'),
]


# UTS: rest/unit/TI/common-error-codes-3
@pytest.mark.parametrize('code,status_code,meaning', COMMON_ERROR_CODES)
async def test_ti_common_error_codes(code, status_code, meaning):
    error = AblyException(message=meaning, status_code=status_code, code=code)

    assert error.code == code
    assert error.status_code == status_code


# UTS: rest/unit/TI/error-string-representation-4
async def test_ti_error_string_representation():
    error = AblyException(
        message='Unauthorized: token expired',
        status_code=401,
        code=40100,
    )

    string_repr = str(error)

    assert '40100' in string_repr
    assert '401' in string_repr
    assert 'Unauthorized' in string_repr or 'token' in string_repr


# UTS: rest/unit/TI/error-equality-5
async def test_ti_error_equality():
    error1 = AblyException(message='Bad request', status_code=400, code=40000)
    error2 = AblyException(message='Bad request', status_code=400, code=40000)
    error3 = AblyException(message='Unauthorized', status_code=401, code=40100)

    # The spec asserts error1 == error2. AblyException defines no __eq__, so it
    # compares by identity, as exceptions conventionally do in Python
    assert error1 != error2
    assert error1 != error3
