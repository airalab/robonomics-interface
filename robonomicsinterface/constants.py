REMOTE_WS = "wss://kusama.rpc.robonomics.network"
TYPE_REGISTRY = {
    "types": {
        "Record": "Vec<u8>",
        "<T as frame_system::Config>::AccountId": "AccountId",
        "RingBufferItem": {"type": "struct", "type_mapping": [["timestamp", "Compact<u64>"], ["payload", "Vec<u8>"]]},
        "RingBufferIndex": {"type": "struct", "type_mapping": [["start", "Compact<u64>"], ["end", "Compact<u64>"]]},
    }
}
