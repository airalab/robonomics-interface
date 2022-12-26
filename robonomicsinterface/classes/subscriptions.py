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
        self._addr: tp.Optional[tp.Union[tp.List[str], str]] = addr

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

        chain_events: list = self._custom_functions.chainstate_query("System", "Events")
        for event in chain_events:

            if event["event_id"] in self._subscribed_event:
                if self._addr and not self._target_address_in_event(event):
                    continue

                callback = partial(self._subscription_handler, event["attributes"])
                if self._pass_event_id:
                    callback = partial(callback, f"{index_obj['header']['number']}-{event['extrinsic_idx']}")
                callback()

    def _target_address_in_event(self, event) -> bool:
        """
        Return whether call callback function or not.

        :param event: Occurred chain event.

        :return: Whether call callback function or not.

        """

        if isinstance(event["attributes"], dict):
            event["attributes"] = list(event["attributes"].values())

        if event["event_id"] in [SubEvent.NewRecord.value, SubEvent.TopicChanged.value, SubEvent.NewDevices.value]:
            return str(event["attributes"][0]) in self._addr
        else:
            return str(event["attributes"][1]) in self._addr

    def cancel(self) -> None:
        """
        Cancel subscription and join its thread.

        """

        self._cancel_flag = True
