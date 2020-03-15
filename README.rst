Restraint
---------

.. image:: https://travis-ci.org/KyleJamesWalker/restraint-py.svg?branch=master
    :target: https://travis-ci.org/KyleJamesWalker/restraint-py

.. image:: https://codecov.io/gh/KyleJamesWalker/restraint-py/branch/master/graph/badge.svg
  :target: https://codecov.io/gh/KyleJamesWalker/restraint-py

Simple Rate Limit Library.

Example setup
^^^^^^^^^^^^^

.. code-block:: python

 from restraint import restrain, Limit, add

 add('example', Limit(second=1, minute=5))

 @restrain('example')
 def hello():
     print(f'Hello World')
