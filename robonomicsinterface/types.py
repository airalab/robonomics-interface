import typing as tp

AccountTyping = tp.Dict[str, tp.Union[int, tp.Dict[str, int]]]
DatalogTyping = tp.Tuple[int, tp.Union[int, str]]
LiabilityTyping = tp.Dict[str, tp.Union[tp.Dict[str, tp.Union[str, int]], str]]
ReportTyping = tp.Dict[str, tp.Union[int, str, tp.Dict[str, str]]]
TypeRegistryTyping = tp.Dict[str, tp.Dict[str, tp.Union[str, tp.Any]]]
