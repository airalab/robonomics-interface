import pytest

from robonomicsinterface.classes.pubsub import PubSub
from robonomicsinterface.classes.reqres import ReqRes


def _pubsub(account, service_functions_mock):
    pubsub = PubSub(account)
    pubsub._service_functions = service_functions_mock
    return pubsub


def _reqres(account, service_functions_mock):
    reqres = ReqRes(account)
    reqres._service_functions = service_functions_mock
    return reqres


@pytest.mark.parametrize(
    ("method_name", "args", "rpc_method", "rpc_params"),
    [
        ("connect", ("peer-address",), "pubsub_connect", ["peer-address"]),
        ("listen", ("listen-address",), "pubsub_listen", ["listen-address"]),
        ("get_listeners", (), "pubsub_listeners", None),
        ("get_peer", (), "pubsub_peer", None),
        ("publish", ("topic", "message"), "pubsub_publish", ["topic", "message"]),
        ("subscribe", ("topic",), "pubsub_subscribe", ["topic"]),
        (
            "unsubscribe",
            ("subscription-id",),
            "pubsub_unsubscribe",
            ["subscription-id"],
        ),
    ],
)
def test_pubsub_methods_delegate_to_rpc(
    account, service_functions_mock, method_name, args, rpc_method, rpc_params
):
    pubsub = _pubsub(account, service_functions_mock)
    handler = object()
    service_functions_mock.rpc_request.return_value = {"result": True}

    assert getattr(pubsub, method_name)(*args, result_handler=handler) == {
        "result": True
    }
    service_functions_mock.rpc_request.assert_called_once_with(
        rpc_method, rpc_params, handler
    )


@pytest.mark.parametrize(
    ("method_name", "args", "rpc_method", "rpc_params"),
    [
        ("p2p_get", ("peer-address", "GET"), "p2p_get", ["peer-address", "GET"]),
        ("p2p_ping", ("peer-address",), "p2p_ping", ["peer-address"]),
    ],
)
def test_reqres_methods_delegate_to_rpc(
    account, service_functions_mock, method_name, args, rpc_method, rpc_params
):
    reqres = _reqres(account, service_functions_mock)
    handler = object()
    service_functions_mock.rpc_request.return_value = {"result": True}

    assert getattr(reqres, method_name)(*args, result_handler=handler) == {
        "result": True
    }
    service_functions_mock.rpc_request.assert_called_once_with(
        rpc_method, rpc_params, handler
    )
