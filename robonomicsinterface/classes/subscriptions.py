import threading
import typing as tp

from enum import Enum
from functools import partial
from logging import getLogger
from websocket import WebSocketConnectionClosedException

from .account import Account
from .service_functions import ServiceFunctions

logger = getLogger(__name__)


class SubEvent(Enum):
    """
    This is an  ``Enum`` class to hold possible events traced by ``Subscriber`` class. May be extended with
        ``aenum.extend_enum``.

    """

    NewRecord = "NewRecord"
    NewLaunch = "NewLaunch"
    Transfer = "Transfer"
    TopicChanged = "TopicChanged"
    NewDevices = "NewDevices"
    NewLiability = "NewLiability"
    NewReport = "NewReport"


class Subscriber:
    """
    Class intended for use in cases when needed to subscribe on chainstate updates/events.
    """

    def __init__(
        self,
        account: Account,
        subscribed_event: SubEvent,
        subscription_handler: callable,
        pass_event_id: bool = False,
        addr: tp.Optional[tp.Union[tp.List[str], str]] = None,
    ) -> None:
        """
        Initiates an instance for further use and starts a subscription for a selected action.

        :param account: Account dataclass with ``seed``, ``remote_ws`` address and node ``type_registry``.
        :param subscribed_event: Event in substrate chain to be awaited. Choose from SubEvent class.
        :param subscription_handler: Callback function that processes the updates of the storage. This function is meant
            to accept only one parameter by default (the new event description). It will receive
            ``(block_num, event_id)`` as a second parameter if ``pass_event_id`` is set to ``True``.
        :param pass_event_id: The ``subscription_handler`` will receive event ID as a second parameter
            if ``pass_event_id`` is True. Format is ``{block_number}-{event_idx}``.
        :param addr: ss58 type 32 address(-es) of an account(-s) which is(are) meant to be event target. If ``None``,
            will subscribe to all such events never-mind target address(-es).

        """

        if "(" in subscribed_event.value:
            self._subscribed_event: list = (
                subscribed_event.value.replace("(", "").replace(")", "").replace("'", "").split(", ")
            )
        else:
            self._subscribed_event: list = [subscribed_event.value]
        self._subscription_handler: callable = subscription_handler
        self._pass_event_id: bool = pass_event_id
        self._addr: tp.Optional[tp.Set[str]] = self._normalize_addresses(addr)

        self._custom_functions: ServiceFunctions = ServiceFunctions(account)
        self._cancel_flag: bool = False

        self._subscription: threading.Thread = threading.Thread(target=self._subscribe_event)
        self._subscription.start()

    def _subscribe_event(self) -> None:
        """
        Subscribe to events targeted to a certain account (``launch``, ``transfer``). Call ``subscription_handler``
        when updated.

        """

        logger.info(f"Subscribing to event {self._subscribed_event} for target addresses {self._addr}")
        try:
            self._custom_functions.subscribe_block_headers(self._event_callback)
        except WebSocketConnectionClosedException:
            self._subscribe_event()

    def _event_callback(self, index_obj: tp.Any, update_nr: int, subscription_id: int) -> tp.Optional[bool]:
        """
        Function, processing updates in event list storage. On update filters events to a desired account
        and passes the event description to the user-provided ``callback`` method.

        :param index_obj: Updated event list.
        :param update_nr: Update counter. Increments every new update added. Starts with ``0``.
        :param subscription_id: Subscription ID.

        """

        if update_nr == 0:
            return None
        if self._cancel_flag:
            return True

        block_hash = self._event_block_hash(index_obj)
        chain_events: list = self._custom_functions.chainstate_query(
            "System", "Events", block_hash=block_hash
        )
        for event in chain_events:

            if event["event_id"] in self._subscribed_event:
                if self._addr and not self._target_address_in_event(event):
                    continue

                callback = partial(self._subscription_handler, event["attributes"])
                if self._pass_event_id:
                    callback = partial(callback, f"{index_obj['header']['number']}-{event['extrinsic_idx']}")
                callback()

    def _event_block_hash(self, index_obj: tp.Any) -> str:
        header = index_obj["header"]
        block_hash = header.get("hash")
        if block_hash:
            return block_hash

        block_number = header["number"]
        if isinstance(block_number, str) and block_number.startswith("0x"):
            block_number = int(block_number, 16)
        return self._custom_functions.get_block_hash(block_number)

    @staticmethod
    def _normalize_addresses(addr: tp.Optional[tp.Union[tp.List[str], str]]) -> tp.Optional[tp.Set[str]]:
        if addr is None:
            return None
        if isinstance(addr, str):
            return {addr}
        return {str(address) for address in addr}

    @staticmethod
    def _attribute_at(attributes: tp.Any, index: int) -> tp.Optional[tp.Any]:
        if isinstance(attributes, (list, tuple)):
            return attributes[index] if index < len(attributes) else None
        if isinstance(attributes, dict):
            values = list(attributes.values())
            return values[index] if index < len(values) else None
        return None

    @staticmethod
    def _dict_value(mapping: tp.Any, key: str) -> tp.Optional[tp.Any]:
        return mapping.get(key) if isinstance(mapping, dict) else None

    @classmethod
    def _addresses_from_positions(cls, attributes: tp.Any, indexes: tp.Iterable[int]) -> tp.Set[str]:
        addresses = set()
        for index in indexes:
            address = cls._attribute_at(attributes, index)
            if address is not None:
                addresses.add(str(address))
        return addresses

    @classmethod
    def _liability_addresses(cls, attributes: tp.Any) -> tp.Set[str]:
        if isinstance(attributes, dict):
            agreement = cls._dict_value(attributes, "agreement")
            addresses = {
                str(address)
                for address in (
                    cls._dict_value(attributes, "promisee"),
                    cls._dict_value(attributes, "promisor"),
                    cls._dict_value(agreement, "promisee"),
                    cls._dict_value(agreement, "promisor"),
                )
                if address is not None
            }
            if addresses:
                return addresses

        return cls._addresses_from_positions(attributes, (3, 4))

    @classmethod
    def _report_addresses(cls, attributes: tp.Any) -> tp.Set[str]:
        if isinstance(attributes, dict):
            report = cls._dict_value(attributes, "report")
            sender = cls._dict_value(attributes, "sender") or cls._dict_value(report, "sender")
            return {str(sender)} if sender is not None else set()

        report = cls._attribute_at(attributes, 1)
        sender = cls._dict_value(report, "sender")
        return {str(sender)} if sender is not None else set()

    @classmethod
    def _addresses_in_event(cls, event: tp.Dict[str, tp.Any]) -> tp.Set[str]:
        attributes = event["attributes"]
        event_id = event["event_id"]
        if event_id in [SubEvent.NewRecord.value, SubEvent.TopicChanged.value, SubEvent.NewDevices.value]:
            return cls._addresses_from_positions(attributes, (0,))
        if event_id in [SubEvent.NewLaunch.value, SubEvent.Transfer.value]:
            return cls._addresses_from_positions(attributes, (1,))
        if event_id == SubEvent.NewLiability.value:
            return cls._liability_addresses(attributes)
        if event_id == SubEvent.NewReport.value:
            return cls._report_addresses(attributes)
        return set()

    def _target_address_in_event(self, event) -> bool:
        """
        Return whether call callback function or not.

        :param event: Occurred chain event.

        :return: Whether call callback function or not.

        """

        target_addresses = self._normalize_addresses(self._addr)
        if not target_addresses:
            return True
        return bool(self._addresses_in_event(event) & target_addresses)

    def cancel(self) -> None:
        """
        Cancel subscription and join its thread.

        """

        self._cancel_flag = True
