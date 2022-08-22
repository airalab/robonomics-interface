import typing as tp
from functools import partial

from enum import Enum
from logging import getLogger
from websocket import WebSocketConnectionClosedException

from .account import Account
from .service_functions import ServiceFunctions

logger = getLogger(__name__)


class SubEvent(Enum):
    NewRecord = "NewRecord"
    NewLaunch = "NewLaunch"
    Transfer = "Transfer"
    TopicChanged = "TopicChanged"
    NewDevices = "NewDevices"
    NewLiability = "NewLiability"
    NewReport = "NewReport"


class Subscriber:
    """
    Class intended for use in cases when needed to subscribe on chainstate updates/events. **Blocks current thread**!
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
        :param subscribed_event: Event in substrate chain to be awaited. Choose from [``NewRecord``, ``NewLaunch``,
            ``Transfer``, ``TopicChanged``, ``NewDevices``]. This parameter should be a ``SubEvent`` class attribute.
            This also requires importing this class.
        :param subscription_handler: Callback function that processes the updates of the storage.
            THIS FUNCTION IS MEANT TO ACCEPT ONLY ONE ARGUMENT (THE NEW EVENT DESCRIPTION TUPLE) by default.
            It will receive event ID as a second parameter if ``pass_event_id`` is True.
        :param pass_event_id: The ``subscription_handler`` will receive event ID as a second parameter
            if ``pass_event_id`` is True. Format is ``{block_number}-{event_idx}``.
        :param addr: ss58 type 32 address(-es) of an account(-s) which is(are) meant to be event target. If ``None``,
            will subscribe to all such events never-mind target address(-es).

        """

        self._custom_functions: ServiceFunctions = ServiceFunctions(account)
        self._event: SubEvent = subscribed_event
        self._callback: callable = subscription_handler
        self._target_address: tp.Optional[tp.Union[tp.List[str], str]] = addr
        self._pass_event_id: bool = pass_event_id

        self._subscribe_event()

    def _subscribe_event(self) -> None:
        """
        Subscribe to events targeted to a certain account (``launch``, ``transfer``). Call ``subscription_handler``
        when updated.

        """

        logger.info(f"Subscribing to event {self._event.value} for target addresses {self._target_address}")
        try:
            self._custom_functions.subscribe_block_headers(self._event_callback)
        except WebSocketConnectionClosedException:
            self._subscribe_event()

    def _event_callback(self, index_obj: tp.Any, update_nr: int, subscription_id: int) -> None:
        """
        Function, processing updates in event list storage. On update filters events to a desired account
        and passes the event description to the user-provided ``callback`` method.

        :param index_obj: Updated event list.
        :param update_nr: Update counter. Increments every new update added. Starts with ``0``.
        :param subscription_id: Subscription ID.

        """

        if update_nr == 0:
            return None

        chain_events: list = self._custom_functions.chainstate_query("System", "Events")
        for events in chain_events:
            if events["event_id"] in self._event.value:
                should_callback: bool = (self._target_address is None) or (
                    events["event"]["attributes"][
                        0
                        if self._event
                        in [
                            SubEvent.NewRecord,
                            SubEvent.TopicChanged,
                            SubEvent.NewDevices,
                        ]
                        else 1
                    ]
                    in self._target_address
                )
                if not should_callback:
                    continue
                callback = partial(self._callback, events["event"]["attributes"])
                if self._pass_event_id:
                    block_num: int = index_obj["header"]["number"]
                    event_id: str = "{}-{}".format(block_num, events["extrinsic_idx"])
                    callback = partial(callback, event_id)
                callback()
