API reference
=============

Everything here is importable from ``robonomicsinterface``; the names listed in
``__all__`` are the stable API (see the migration guide).

Client
------

.. autoclass:: robonomicsinterface.RobonomicsClient
   :members:

.. autoclass:: robonomicsinterface.RobonomicsSync
   :members:

Pallets
-------

.. automodule:: robonomicsinterface.pallets.datalog
   :members:

.. automodule:: robonomicsinterface.pallets.rws
   :members:

.. automodule:: robonomicsinterface.pallets.system
   :members:

.. autoclass:: robonomicsinterface.pallets.SubmitOptions

Extrinsics
----------

.. automodule:: robonomicsinterface.extrinsic
   :members:

Keys and addresses
------------------

.. automodule:: robonomicsinterface.keys
   :members:

.. automodule:: robonomicsinterface.ss58
   :members:

.. automodule:: robonomicsinterface.bip39
   :members: generate_mnemonic, validate_mnemonic

Report envelope
---------------

.. automodule:: robonomicsinterface.envelope
   :members:

Errors
------

.. automodule:: robonomicsinterface.errors
   :members:
   :show-inheritance:
