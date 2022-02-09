# robonomics-interface
This is a simple wrapper over https://github.com/polkascan/py-substrate-interface used to facilitate writing code for applications using Robonomics.

Robonomics project: https://robonomics.network/

Robonomics parachain dapp: https://parachain.robonomics.network/
_______
# Installation 
```bash
pip3 install robonomics-interface
```
# Usage
*More info may be found in docstrings in the source code*
```python
import robonomicsinterface as RI
```
## Initialization
```python
interface = RI.RobonomicsInterface()
```
By default, you will only be able to fetch Chainstate info from Frontier parachain and use PubSub pattern.  

You can specify another `node address` (e.g. local), `seed` to sign extrinsics (more on that [later](#extrinsics)) 
and custom `registry types`.

Address of the device may be obtained using `define_address` method. If the interface was initialed with a seed/private key
this method will return `<ss58_addr>` of the device whose seed/private key was passed.

## Simple case: fetch Chainstate
Here, no need to pass any arguments, by
```python
interface = RI.RobonomicsInterface()
```
you will be able to read any Chainstate info from the Frontier parachain:
```python
num_dt = interface.custom_chainstate("DigitalTwin", "Total")
```
you can also specify an argument for the query. Several arguments should be put in a list. Block hash parameter is 
also available via `block_hash` argument if you want to make a query as of a specified block.

There is a dedicated function to obtain **Datalog**:
```python
record = interface.fetch_datalog(<ss58_addr>)
```
This will give you the latest datalog record of the specified account with its timestamp. You may pass an index argument to fetch specific record. If you create an interface with a provided seed, you'll be able to fetch self-datalog calling `fetch_datalog` with no arguments (or just the `index` argument). 

## Extrinsics
**Providing seed** (any raw or mnemonic) while initializing **will let you create and submit extrinsics**:
```python
interface = RI.RobonmicsInterface(seed:str = <seed>)
hash = interface.custom_extrinsic("DigitalTwin", "create")
```
`hash` here is the transaction hash of the succeeded extrinsic. You can also specify arguments for the extrinsic as a dictionary.

There are dedicated functions for recording datalog and sending launch commands:
```python
interface.record_datalog("Hello, Robonomics")
interface.send_launch(<target_addr>, True)
```
Current nonce definition and manual nonce setting is also possible.

## Robonomics Web Services (RWS)
There are as well dedicated methods for convenient usage of RWS.
- Chainstate functions `auctionQueue`, `auction` to examine subscriptions auctions:
```python
interface.rws_auction_queue()
inteface.rws_auction(<auction_index>)
```
- Extrinsincs: `bid`, `set_devices` and, the most important, `call`
```python
interface.rws_bid(<auction_index>, <amount_weiners>)
interface.rws_set_devices([<ss58_addr>, <ss58_addr>])
interface.rws_custom_call(<subscription_owner_addr>,
                           <call_module>,
                           <call_function>,
                           <params_dict>)
```
There are as well dedicated `datalog` and `launch` functions for RWS-based transactions.
```python
interface.rws_record_datalog(<subscription_owner_addr>, <data>)
interface.rws_send_launch(<subscription_owner_addr>, <target_addr>, True)
```

## Subscriptions
There is a subscriptions functional implemented. When initiated, blocks thread and processes new events with a user-passed 
callback function. Pay attention that this callback may only accept one argument - the event data. Up to now, the only supported 
events are `NewRecord`, `NewLaunch`, `Transfer`
```python
from robonomicsinterface import RobonomicsInterface, Subscriber, SubEvent

def callback(data):
    print(data)

interface = RobonomicsInterface()
subscriber = Subscriber(interface, SubEvent.NewLaunch, callback, <ss58_addr>)
```

## IO
This package provides console prototyping tool such as [robonomics io](https://wiki.robonomics.network/docs/en/rio-overview/)
with slight differences:
```bash
$ robonomics_interface read datalog
$ echo "Hello, Robonomics" | robonomics_interface write datalog -s <seed>
$ robonomics_interface read launch
$ echo "ON" | robonomics_interface write launch -s <seed> -r <target_addr>
```
More info may be found with 
```bash
$ robonomics_interface --help
```

## JSON RPC
*WARNING: THIS MODULE IS UNDER CONSTRUCTIONS, USE AT YOUR OWN RISK! TO BE UPDATED SOON.*  
There is a way to implement robonomics pubsub rpc calls:

```python3
interface = RI.RobonomicsInterface()
pubsub = PubSub(interface)
pubsub.peer()
```

This is an evolving package, it may have errors and lack of functionality, fixes are coming.
Feel free to open issues when faced a problem.