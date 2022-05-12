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

You can specify another ``remote_ws`` (e.g. local), ``seed`` to sign extrinsics and custom ``type_registry``.

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
    imdex = 8
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
It is worth to mention that any query in these classes may accept ``block_hash`` argument and eny extrinsic may accept
``nonce`` argument. Also, if some method implies query, it name starts with ``get_``.

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

There is a subscriptions functional implemented. When initiated, blocks thread and processes new events with a user-passed
callback function. Pay attention that this callback may only accept one argument - the event data. Up to now, the only supported
events are ``NewRecord``, ``NewLaunch``, ``Transfer``, ``TopicChanged`` and ``NewDevices``.

.. code-block:: python

    from robonomicsinterface import Subscriber, SubEvent

    def callback(data):
        print(data)

    account = Account()
    subscriber = Subscriber(account, SubEvent.NewRecord, subscription_handler=callback)

One may also pass a list of addresses or one address as a parameter to filter trigger situations.

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
*WARNING: THIS MODULE IS UNDER CONSTRUCTIONS, USE AT YOUR OWN RISK! TO BE UPDATED SOON.*

There is a way to implement robonomics pubsub rpc calls:

.. code-block:: python

    from robonomicsinterface import PubSub

    pubsub = PubSub(account)
    pubsub.peer()

Utils
++++++++

Utils module provides some helpful functions, among which there are IPFS ``Qm...`` hash encoding to 32 bytes length
string and vice-versa.

.. code-block:: python

    from robonomicsinterface.utils import ipfs_qm_hash_to_32_bytes, ipfs_32_bytes_to_qm_hash

    ipfs_hash = "Qmc5gCcjYypU7y28oCALwfSvxCBskLuPKWpK4qpterKC7z"
    bytes_32 = ipfs_qm_hash_to_32_bytes("Qmc5gCcjYypU7y28oCALwfSvxCBskLuPKWpK4qpterKC7z")
    # >>> '0xcc2d976220820d023b7170f520d3490e811ed988ae3d6221474ee97e559b0361'
    ipfs_hash_decoded = ipfs_32_bytes_to_qm_hash("0xcc2d976220820d023b7170f520d3490e811ed988ae3d6221474ee97e559b0361")
    # >>> 'Qmc5gCcjYypU7y28oCALwfSvxCBskLuPKWpK4qpterKC7z'