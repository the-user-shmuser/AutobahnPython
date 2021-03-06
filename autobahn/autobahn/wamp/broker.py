###############################################################################
##
##  Copyright (C) 2013-2014 Tavendo GmbH
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

from __future__ import absolute_import

from autobahn import util
from autobahn.wamp import types
from autobahn.wamp import role
from autobahn.wamp import message
from autobahn.wamp.exception import ApplicationError
from autobahn.wamp.interfaces import IBroker

from autobahn.wamp.message import _URI_PAT_STRICT_NON_EMPTY, _URI_PAT_LOOSE_NON_EMPTY



class Broker:
   """
   Basic WAMP broker, implements :class:`autobahn.wamp.interfaces.IBroker`.
   """

   def __init__(self, realm, options = None):
      """
      Constructor.

      :param realm: The realm this broker is working for.
      :type realm: str
      :param options: Router options.
      :type options: Instance of :class:`autobahn.wamp.types.RouterOptions`.
      """
      self.realm = realm
      self._options = options or types.RouterOptions()

      ## map: session -> set(subscription)
      ## needed for removeSession
      self._session_to_subscriptions = {}

      ## map: session_id -> session
      ## needed for exclude/eligible
      self._session_id_to_session = {}

      ## map: topic -> (subscription, set(session))
      ## needed for PUBLISH and SUBSCRIBE
      self._topic_to_sessions = {}

      ## map: subscription -> (topic, set(session))
      ## needed for UNSUBSCRIBE
      self._subscription_to_sessions = {}

      ## check all topic URIs with strict rules
      self._option_uri_strict = self._options.uri_check == types.RouterOptions.URI_CHECK_STRICT

      ## supported features from "WAMP Advanced Profile"
      self._role_features = role.RoleBrokerFeatures(publisher_identification = True, subscriber_blackwhite_listing = True, publisher_exclusion = True)


   def attach(self, session):
      """
      Implements :func:`autobahn.wamp.interfaces.IBroker.attach`
      """
      assert(session not in self._session_to_subscriptions)

      self._session_to_subscriptions[session] = set()
      self._session_id_to_session[session._session_id] = session


   def detach(self, session):
      """
      Implements :func:`autobahn.wamp.interfaces.IBroker.detach`
      """
      assert(session in self._session_to_subscriptions)

      for subscription in self._session_to_subscriptions[session]:
         topic, subscribers = self._subscription_to_sessions[subscription]
         subscribers.discard(session)
         if not subscribers:
            del self._subscription_to_sessions[subscription]
         _, subscribers = self._topic_to_sessions[topic]
         subscribers.discard(session)
         if not subscribers:
            del self._topic_to_sessions[topic]

      del self._session_to_subscriptions[session]
      del self._session_id_to_session[session._session_id]


   def processPublish(self, session, publish):
      """
      Implements :func:`autobahn.wamp.interfaces.IBroker.processPublish`
      """
      assert(session in self._session_to_subscriptions)

      ## check topic URI
      ##
      if (not self._option_uri_strict and not  _URI_PAT_LOOSE_NON_EMPTY.match(publish.topic)) or \
         (    self._option_uri_strict and not _URI_PAT_STRICT_NON_EMPTY.match(publish.topic)):

         if publish.acknowledge:
            reply = message.Error(message.Publish.MESSAGE_TYPE, publish.request, ApplicationError.INVALID_URI, ["publish with invalid topic URI '{}'".format(publish.topic)])
            session._transport.send(reply)

         return

      if publish.topic in self._topic_to_sessions and self._topic_to_sessions[publish.topic]:

         ## initial list of receivers are all subscribers ..
         ##
         subscription, receivers = self._topic_to_sessions[publish.topic]

         ## filter by "eligible" receivers
         ##
         if publish.eligible:
            eligible = []
            for s in publish.eligible:
               if s in self._session_id_to_session:
                  eligible.append(self._session_id_to_session[s])
            if eligible:
               receivers = set(eligible) & receivers

         ## remove "excluded" receivers
         ##
         if publish.exclude:
            exclude = []
            for s in publish.exclude:
               if s in self._session_id_to_session:
                  exclude.append(self._session_id_to_session[s])
            if exclude:
               receivers = receivers - set(exclude)

         ## remove publisher
         ##
         if publish.excludeMe is None or publish.excludeMe:
         #   receivers.discard(session) # bad: this would modify our actual subscriber list
            me_also = False
         else:
            me_also = True

      else:
         subscription, receivers, me_also = None, [], False

      publication = util.id()

      ## send publish acknowledge when requested
      ##
      if publish.acknowledge:
         msg = message.Published(publish.request, publication)
         session._transport.send(msg)

      ## if receivers is non-empty, dispatch event ..
      ##
      if receivers:
         if publish.discloseMe:
            publisher = session._session_id
         else:
            publisher = None
         msg = message.Event(subscription,
                             publication,
                             args = publish.args,
                             kwargs = publish.kwargs,
                             publisher = publisher)
         for receiver in receivers:
            if me_also or receiver != session:
               ## the subscribing session might have been lost in the meantime ..
               if receiver._transport:
                  receiver._transport.send(msg)


   def processSubscribe(self, session, subscribe):
      """
      Implements :func:`autobahn.wamp.interfaces.IBroker.processSubscribe`
      """
      assert(session in self._session_to_subscriptions)

      ## check topic URI
      ##
      if (not self._option_uri_strict and not  _URI_PAT_LOOSE_NON_EMPTY.match(subscribe.topic)) or \
         (    self._option_uri_strict and not _URI_PAT_STRICT_NON_EMPTY.match(subscribe.topic)):

         reply = message.Error(message.Subscribe.MESSAGE_TYPE, subscribe.request, ApplicationError.INVALID_URI, ["subscribe for invalid topic URI '{}'".format(subscribe.topic)])

      else:

         if not subscribe.topic in self._topic_to_sessions:
            subscription = util.id()
            self._topic_to_sessions[subscribe.topic] = (subscription, set())

         subscription, subscribers = self._topic_to_sessions[subscribe.topic]

         if not session in subscribers:
            subscribers.add(session)

         if not subscription in self._subscription_to_sessions:
            self._subscription_to_sessions[subscription] = (subscribe.topic, set())

         _, subscribers = self._subscription_to_sessions[subscription]
         if not session in subscribers:
            subscribers.add(session)

         if not subscription in self._session_to_subscriptions[session]:
            self._session_to_subscriptions[session].add(subscription)

         reply = message.Subscribed(subscribe.request, subscription)

      session._transport.send(reply)


   def processUnsubscribe(self, session, unsubscribe):
      """
      Implements :func:`autobahn.wamp.interfaces.IBroker.processUnsubscribe`
      """
      assert(session in self._session_to_subscriptions)

      if unsubscribe.subscription in self._subscription_to_sessions:

         topic, subscribers = self._subscription_to_sessions[unsubscribe.subscription]

         subscribers.discard(session)

         if not subscribers:
            del self._subscription_to_sessions[unsubscribe.subscription]

         _, subscribers = self._topic_to_sessions[topic]

         subscribers.discard(session)

         if not subscribers:
            del self._topic_to_sessions[topic]

         self._session_to_subscriptions[session].discard(unsubscribe.subscription)

         reply = message.Unsubscribed(unsubscribe.request)

      else:
         reply = message.Error(message.Unsubscribe.MESSAGE_TYPE, unsubscribe.request, ApplicationError.NO_SUCH_SUBSCRIPTION)

      session._transport.send(reply)



IBroker.register(Broker)
