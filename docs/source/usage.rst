..  _usage:

Usage
=====

Installation
------------

To use robonomics-interface, first install it using pip:

.. code-block:: console

   $ pip3 install robonomics-interface

Examples
--------

Initialization
++++++++++++++

.. code-block:: python

    from robonomicsinterface import Account
    account = Account()

By default, you will only be able to fetch Chainstate info from
`Robonomics Kusama parachain <https://polkadot.js.org/apps/?rpc=wss%3A%2F%2Fkusama.rpc.robonomics.network%2F#/explorer>`_
and use :ref:`PubSub <PubSub>` and :ref:`ReqRes <ReqRes API>` patterns.

You can specify another ``remote_ws`` (e.g. local), ``seed`` to sign extrinsics, custom ``type_registry`` and ``crypto_type``.

.. code-block:: python

    account_local_dev_node = Account(remote_ws="ws://127.0.0.1:9944")

Address of the account may be obtained using ``get_address()`` method if the account was initialed with a seed/private key.
This method will return ss58-address format of the created account address.

Service Functions
+++++++++++++++++

As have been said, when initiating :ref:`account<Initialization>` instance without a seed, you will be able to read any
Chainstate info from the Robonomics Kusama parachain. This is possible by some dedicated below-mentioned classes and a
``ServiceFunctions``'s method ``chainstate_query`` allowing user to execute any query.

.. code-block:: python

    from robonomicsinterface import ServiceFunctions

    service_functions = ServiceFunctions(account)
    num_dt = service_functions.chainstate_query("DigitalTwin", "Total")

You can also specify an argument for the query. Several arguments should be put in a list. Block hash parameter is
also available via ``block_hash`` argument if you want to make a query as of a specified block:

.. code-block:: python

    address = "4CqaroZnr25e43Ypi8Qe5NwbUYXzhxKqrfY5opnRzK4yG1mg"
    index = 8
    block_hash = "0x7bdd8ae3d9a2976a4d2a534071d076a5b8caf24f8f0447587d1cbc901f07892e"
    some_record = service_functions.chainstate_query("Datalog", "DatalogItem", [address, index], block_hash=block_hash)

**Providing seed** (any, raw or mnemonic) while initializing **will let you create and submit extrinsics**:

.. code-block:: python

    account_with_seed = Account(seed="this is a testing seed phrase of specified length which equals twelve")
    service_functions_seed = ServiceFunctions(account_with_seed)
    hash_tr = service_functions_seed.extrinsic("DigitalTwin", "create")

``hash_tr`` here is the transaction hash of the succeeded extrinsic. You can also specify arguments for the extrinsic
as a dictionary and set transaction nonce.

.. code-block:: python

    from robonomicsinterface.utils import dt_encode_topic

    dt_id = 0
    topic_hashed = dt_encode_topic("topic 1")
    source = account_with_seed.get_address()
    nonce = 42
    hash_tr = service_functions_seed.extrinsic("DigitalTwin", "set_source", {"id": dt_id, "topic": topic_hashed, "source": source}, nonce=nonce)


One nay also perform custom rpc calls:

.. code-block:: python

    def result_handler(data):
        print(data)

    service_functions.rpc_request("pubsub_peer", None, result_handler)

There are a lot of dedicated classes for the most frequently used queries, extrinsics and rpc calls. More on that below.

Chain Utils
+++++++++++

This class is dedicated to some utilities to obtain valuable information from the node of the blockchain which is not
module-specific. For example, transaction search or transforming a block hash in a block number and vice versa.

.. code-block:: python

    from robonomicsinterface import ChainUtils

    cu = ChainUtils()
    print(cu.get_block_number("0xef9ca7a02b8ab2df373b1f86f336474947df05455a1076a3c64b034319bd7152"))  # 2875
    print(cu.get_block_hash(2875))  # 0xef9ca7a02b8ab2df373b1f86f336474947df05455a1076a3c64b034319bd7152

Extrinsic search function here is implemented by ``get_extrinsic_in_block`` method. It accepts block hash/number and
extrinsic hash/idx as arguments:

.. code-block:: python

    print(cu.get_extrinsic_in_block(1054910, 4))  # RWS call info.
    print(cu.get_extrinsic_in_block("0x97ff645b2035a0ad62ed5f438ebd5ee91cbfe3d197ba221c6c03c614c6dc1dfe",
                                    "0xbc2180c1773838ccf2f1e79302bec500c3c5ed7da8ea9471f5e40667574eed9f"))  # The same.

Notice on Below-Listed Classes
++++++++++++++++++++++++++++++

It is worth to mention that any query in these classes may accept ``block_hash`` argument and eny extrinsic may accept
``nonce`` argument. Also, if some method implies query, it name starts with ``get_``.

More that, each time one initialize a class, they may pass ``wait_for_inclusion=False`` argument to avoid waiting for
future transactions to be included in block. It saves time, but one may not know if the transaction was not successful
(e.g. :ref:`DigitalTwin.set_source <Digital Twins>`  was submitted by unauthorized account).

One more argument while initializing is ``return_block_num``. If Set to ``True`` ALONG WITH ``wait_for_inclusion``, the
``extrinsic`` function will return a tuple of form ``(<extrinsic_hash>, <block_number-idx>)``.

Common Functions
++++++++++++++++

With Common Functions class one can send some tokens, get account nonce or some information about any other address.

.. code-block:: python

    from robonomicsinterface import CommonFunctions

    common_functions = CommonFunctions(account_with_seed)

    common_functions.get_account_info(account_with_seed.get_address())
    common_functions.get_account_info()  # Will make the same output as the one above
    common_functions.get_account_nonce(account_with_seed.get_address())
    common_functions.transfer_tokens("4CqaroZnr25e43Ypi8Qe5NwbUYXzhxKqrfY5opnRzK4yG1mg", 1000000000)

Datalog
+++++++

With Datalog class one can record or erase datalog and read datalog records of any account.

.. code-block:: python

    from robonomicsinterface import Datalog

    datalog = Datalog(account_with_seed)

    datalog.record("Hello, world")
    datalog.get_index(account_with_seed.get_address())
    datalog.get_item(account_with_seed.get_address())  # If index was not provided here, the latest one will be used
    datalog.erase()

Digital Twins
+++++++++++++

`Digital Twins <https://wiki.robonomics.network/docs/en/digital-twins/>`__ functionality is also supported.

.. code-block:: python

    from robonomicsinterface import DigitalTwin

    dt = DigitalTwin(account_with_seed)

    dt_it, tr_hash = dt.create()
    # Here the topic is automatically encoded
    topic_hashed, source_tr_hash = dt.set_source(dt_id, "topic 1", "4CqaroZnr25e43Ypi8Qe5NwbUYXzhxKqrfY5opnRzK4yG1mg")
    dt.get_info(dt_id)
    dt.get_owner(dt_id)
    dt.get_total()

One may also find topic source by

.. code-block:: python

    dt.get_source(dt_id, "topic 1")
    # >>> "4CqaroZnr25e43Ypi8Qe5NwbUYXzhxKqrfY5opnRzK4yG1mg"

Launch
++++++

With the help of a Launch class one may send launch commands with parameter to any other addresses. The parameter should
be 32 bytes long, but it may also be an IPFS ``Qm...`` hash, which will be converted automatically.

.. code-block:: python

    from robonomicsinterface import Launch

    launch = Launch(account_with_seed)

    launch.launch("4CqaroZnr25e43Ypi8Qe5NwbUYXzhxKqrfY5opnRzK4yG1mg", "QmYA2fn8cMbVWo4v95RwcwJVyQsNtnEwHerfWR8UNtEwoE")

Liabilities
+++++++++++

This package support Robonomics liability functionality. `Here <https://wiki.robonomics.network/docs/en/robonomics-how-it-works/>`__
is a bit about the concept on Ethereum. It's slightly different in Substrate.

With this package one can create liabilities, sign technical parameters messages, report completed liabilities, sign
report messages, fetch information about current and completed liabilities:

.. code-block:: python

    from robonomicsinterface import Liability

    promisee = Account(seed="<seed>")
    promisor = Account(seed="<seed>")

    promisee_liability = Liability(promisee)
    promisor_liability = Liability(promisor)

    task = "QmYA2fn8cMbVWo4v95RwcwJVyQsNtnEwHerfWR8UNtEwoE" # task parsing is on user side
    reward = 10 * 10 ** 9  # 10 XRT

    promisee_task_signature = promisee_liability.sign_liability(task, reward)
    promisor_task_signature = promisor_liability.sign_liability(task, reward)

    index, tr_hash = promisee_liability.create(
        task, reward, promisee.get_address(), promisor.get_address(), promisee_task_signature, promisor_task_signature
    )

    print(index)
    print(promisee_liability.get_agreement(index))

    report = "Qmc5gCcjYypU7y28oCALwfSvxCBskLuPKWpK4qpterKC7z" # report parsing is on user side
    promisor_liability.finalize(index, report) # this one signs report message automatically if no signature provided
    print(promisor_liability.get_report(index))

Robonomics Web Services (RWS)
+++++++++++++++++++++++++++++

There are as well dedicated methods for convenient usage of RWS.
- Chainstate functions to examine subscriptions and subscription auctions:

.. code-block:: python

    from robonomicsinterface import RWS

    rws = RWS(account_with_seed)

    rws.get_auction_queue()
    rws.get_auction_next()
    rws.get_auction(0)
    rws.get_devices("4CqaroZnr25e43Ypi8Qe5NwbUYXzhxKqrfY5opnRzK4yG1mg")
    rws.get_ledger("4CqaroZnr25e43Ypi8Qe5NwbUYXzhxKqrfY5opnRzK4yG1mg")

- Extrinsincs: `bid`, `set_devices`

.. code-block:: python

    rws.bid(0, 10*10**9)
    rws.set_devices([<ss58_addr>, <ss58_addr>])

- The ``call`` method is implemented differently. If you want to use any module/class with RWS subscription, pass
    the subscription owner address when initializing the class.

.. code-block:: python

    datalog_rws = Datalog(account_seed, rws_sub_owner="4CqaroZnr25e43Ypi8Qe5NwbUYXzhxKqrfY5opnRzK4yG1mg")
    datalog_rws.record("Hello, world via RWS")

Subscriptions
+++++++++++++

There is a subscriptions functional implemented. When initiated, processes new events with a user-passed
callback function. Pay attention that this callback may only accept one argument - the event data. Up to now, the supported
events are ``NewRecord``, ``NewLaunch``, ``Transfer``, ``TopicChanged``, ``NewDevices``, ``NewLiability`` and ``NewReport``.

.. code-block:: python

    from robonomicsinterface import Subscriber, SubEvent

    def callback(data):
        print(data)

    account = Account()
    subscriber = Subscriber(account, SubEvent.MultiEvent, subscription_handler=callback)

    <do stuff>

    subscriber.cancel()

One may also pass a list of addresses or one address as a parameter to filter trigger situation. Another option is to set
``pass_event_id`` to get block number and event ID as a second ``callback`` parameter.

There is a way to subscribe to multiple events by using side package ``aenum``.

.. code-block:: python

    from aenum import extend_enum
    extend_enum(SubEvent, "MultiEvent", f"{SubEvent.NewRecord.value, SubEvent.NewLaunch.value}")

    subscriber = Subscriber(acc, SubEvent.MultiEvent, subscription_handler=callback, addr=<ss58_addr>, pass_event_id=True)

IO
++

This package provides console prototyping tool such as `robonomics io <https://wiki.robonomics.network/docs/en/rio-overview/>`__
with slight differences:

.. code-block:: console

    $ robonomics_interface read datalog
    $ echo "Hello, Robonomics" | robonomics_interface write datalog -s <seed>
    $ robonomics_interface read launch
    $ echo "ON" | robonomics_interface write launch -s <seed> -r <target_addr>

More info may be found with

.. code-block:: console

    $ robonomics_interface --help

ReqRes API
++++++++++

There is a functionality for a direct connection to server based on Robonomics node.

.. code-block:: python

    from robonomicsinterface import ReqRes

    reqres = ReqRes(account)

    reqres.p2p_get(<Multiaddr of server>,<GET request>)
    reqres.p2p_ping(<Multiaddr of server>)


Example of usage
~~~~~~~~~~~~~~~~

Download sample server `here <https://github.com/airalab/robonomics/tree/master/protocol/examples/reqres>`__.
Start this server with local ip (Rust (with cargo) installation process described `here <https://www.rust-lang.org/tools/install>`__):

.. code-block:: console

    cargo run "/ip4/127.0.0.1/tcp/61240"

Then, in other terminal write small execute this script:

.. code-block:: python

    from robonomicsinterface import ReqRes, Account

    account = Account(remote_ws="ws://127.0.0.1:9944")  # requires local node
    reqres = ReqRes(account)

    reqres.p2p_get(<Multiaddr of server>,<GET request>)
    print(reqres.p2p_get("/ip4/127.0.0.1/tcp/61240/<PeerId>","GET")) # PeerId - you will see in server logs

This code sample requires local node launched. ``PeerId`` is obtained when launching server.

PubSub
++++++++

There is a way to implement robonomics pubsub rpc calls. Below is a sample example of how to send messages from one
script and listen to them on another one. For this two developer nodes on one machine were launched with:

.. code-block:: bash

    ./robonomics --dev --tmp -l rpc=trace
    ./robonomics --dev --tmp --ws-port 9991 -l rpc=trace

After that a subscriber and publisher scripts were created. Subscriber:

.. code-block:: python

    from robonomicsinterface import Account, PubSub
    import time


    def subscription_handler(obj, update_nr, subscription_id):
        rawdata = obj['params']['result']['data']
        for i in range(len(rawdata)):
            rawdata[i] = chr(rawdata[i])
        data = "".join(rawdata)
        print(data)


    remote_ws = "ws://127.0.0.1:9944"
    account = Account(remote_ws=remote_ws)
    pubsub = PubSub(account)

    print(pubsub.listen("/ip4/127.0.0.1/tcp/44440"))
    time.sleep(2)
    print(pubsub.subscribe("topic_name", result_handler=subscription_handler))


Subscriber:

.. code-block:: python

    from robonomicsinterface import Account, PubSub
    import time


    remote_ws = "ws://127.0.0.1:9991"
    account = Account(remote_ws=remote_ws)
    pubsub = PubSub(account)

    print(pubsub.connect("/ip4/127.0.0.1/tcp/44440"))
    time.sleep(2)

    while True:
        print("publish:", pubsub.publish("topic_name", "message_" + str(time.time())))
        time.sleep(2)

First, launch the subscriber script, then the publisher one. You should see published messages in listener's script
console.


Utils
++++++++

Utils module provides some helpful functions, among which there are IPFS ``Qm...`` hash encoding to 32 bytes length
string and vice-versa. One more is generating an auth tuple for Web3-Auth gateways (more on that
`on Crust Wiki <https://wiki.crust.network/docs/en/buildIPFSWeb3AuthGW>`__).

.. code-block:: python

    from robonomicsinterface.utils import ipfs_qm_hash_to_32_bytes, ipfs_32_bytes_to_qm_hash

    ipfs_hash = "Qmc5gCcjYypU7y28oCALwfSvxCBskLuPKWpK4qpterKC7z"
    bytes_32 = ipfs_qm_hash_to_32_bytes("Qmc5gCcjYypU7y28oCALwfSvxCBskLuPKWpK4qpterKC7z")
    # >>> '0xcc2d976220820d023b7170f520d3490e811ed988ae3d6221474ee97e559b0361'
    ipfs_hash_decoded = ipfs_32_bytes_to_qm_hash("0xcc2d976220820d023b7170f520d3490e811ed988ae3d6221474ee97e559b0361")
    # >>> 'Qmc5gCcjYypU7y28oCALwfSvxCBskLuPKWpK4qpterKC7z'
    auth = web_3_auth(tester_tokens_seed)
