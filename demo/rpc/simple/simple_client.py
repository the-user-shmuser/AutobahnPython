###############################################################################
##
##  Copyright 2011 Tavendo GmbH
##
##  Licensed under the Apache License, Version 2.0 (the "License");
##  you may not use this file except in compliance with the License.
##  You may obtain a copy of the License at
##
##      http://www.apache.org/licenses/LICENSE-2.0
##
##  Unless required by applicable law or agreed to in writing, software
##  distributed under the License is distributed on an "AS IS" BASIS,
##  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
##  See the License for the specific language governing permissions and
##  limitations under the License.
##
###############################################################################

import sys
from twisted.internet import reactor, defer
from twisted.python import log
from autobahn.autobahn import AutobahnClientFactory, AutobahnClientProtocol


class SimpleClientProtocol(AutobahnClientProtocol):
   """
   Demonstrates simple RCP calls with Autobahn WebSockets and Twisted Deferreds.
   """

   def show(self, result):
      print "SUCCESS:", result

   def alert(self, result):
      print "ERROR:", result

   def onOpen(self):
      # call a function and log result on success
      self.call(23, "square").addCallback(self.show)

      # call a function and call another function on success
      self.call(23, "square").addCallback(self.call, "sqrt").addCallback(self.show)

      # call a function, log on success, show alert on error
      self.call(-1, "sqrt").addCallbacks(self.show, self.alert)

      # call a function with list of numbers as arg
      self.call([1, 2, 3, 4, 5], "sum").addCallback(self.show)

      # call a function with list of numbers as arg and call a lambda created inline function on result
      self.call([1, 2, 3, 4, 5, 6], "sum").addCallback(lambda x: x + 100).addCallback(self.show)

      # call a function that takes a long time, call another function
      # the result of the latter is received first, RPC is really asynchronous
      # moreoever, the connection is closed only after the first, slow function returns.
      #
      self.call([1, 2, 3], "asum").addCallback(self.show).addCallback(self.sendClose)
      self.call([4, 5, 6], "sum").addCallback(self.show)


if __name__ == '__main__':

   log.startLogging(sys.stdout)
   factory = AutobahnClientFactory(debug = False)
   factory.protocol = SimpleClientProtocol
   reactor.connectTCP("localhost", 9000, factory)
   reactor.run()