import typing as tp

AccountTyping = tp.Dict[str, tp.Union[int, tp.Dict[str, int]]]
AuctionTyping = tp.Dict[str, tp.Union[str, int, tp.Dict[str, tp.Dict[str, tp.Dict[str, int]]]]]
DatalogTyping = tp.Tuple[int, tp.Union[int, str]]
DigitalTwinTyping = tp.List[tp.Tuple[str, str]]
LedgerTyping = tp.Dict[str, tp.Union[int, tp.Dict[str, tp.Dict[str, tp.Dict[str, int]]]]]
LiabilityTyping = tp.Dict[str, tp.Union[tp.Dict[str, tp.Union[str, int]], str]]
ListenersResponse = tp.Dict[str, tp.Union[str, tp.List[str], int]]
QueryParams = tp.Optional[tp.Union[tp.List[tp.Union[str, int]], str, int]]
ReportTyping = tp.Dict[str, tp.Union[int, str, tp.Dict[str, str]]]
RWSParamsTyping = tp.Dict[str, tp.Union[str, tp.Dict[str, tp.Union[str, int, dict, list]]]]
TypeRegistryTyping = tp.Dict[str, tp.Dict[str, tp.Union[str, tp.Any]]]
