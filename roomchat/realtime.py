"""
Realtime layer: the small part of Django Channels that rooms/consumers.py uses, rebuilt on
redis.asyncio + msgpack.

- RedisChannelLayer / get_channel_layer(): the channel layer (a message bus between sockets).
  Same behaviour as channels_redis' RedisPubSubChannelLayer: Redis pub/sub, no persistence,
  same key names and message format, so old and new processes can talk during a deploy.
- AsyncWebsocketConsumer: the consumer base class, same method names and ASGI behaviour as
  channels.generic.websocket.AsyncWebsocketConsumer.
- database_sync_to_async: runs a blocking DB helper on a worker thread inside its own `db` scope.
- AllowedHostsOriginValidator: refuses sockets opened from pages on other sites.

Words used below:
- A "channel" is one socket's private mailbox name (e.g. 'asgispecific.3f2a...').
- A "group" is a named set of channels (e.g. 'room_ABC123', 'user_7'); sending to a group
  delivers to every channel in it, in every process.
"""

import asyncio
import functools
import logging
import uuid
from importlib import import_module
from urllib.parse import urlparse

import msgpack
from asgiref.sync import sync_to_async
from redis import asyncio as aioredis

from roomchat import settings
from roomchat.middleware import _in_own_db_scope, _is_same_domain

logger = logging.getLogger(__name__)


# --- Channel layer ----------------------------------------------------------------------

class RedisChannelLayer:
    """Channel layer on Redis pub/sub. Messages published while nobody listens are dropped.

    One instance is shared by the whole process, but the real work happens in a _LoopLayer
    per event loop (see _loop_layer for why).
    """

    def __init__(self, hosts=None, prefix='asgi'):
        if not hosts:
            hosts = ['redis://localhost:6379']  # channels_redis' default
        if isinstance(hosts, (str, bytes)):
            raise ValueError('You must pass a list of Redis hosts, even if there is only one.')
        if len(hosts) != 1:
            raise ValueError('RedisChannelLayer supports exactly one Redis host.')
        self.url = hosts[0]
        self.prefix = prefix
        self._layers = {}  # event loop -> _LoopLayer

    def _loop_layer(self):
        """Return the _LoopLayer for the event loop that is running right now.

        Why one per loop: a Redis connection belongs to the loop that opened it and can't be
        used from another one. The server runs one loop per process for every socket, so
        they all share one connection. But notify_friend_request (a sync HTTP view on a worker thread) calls
        async_to_sync(group_send), and asgiref runs that on a brand-new short-lived loop.
        Keying by loop gives that call its own connection, closed when its loop closes.
        """
        loop = asyncio.get_running_loop()
        if loop not in self._layers:
            self._layers[loop] = _LoopLayer(self.url, self.prefix)
            _flush_before_close(self, loop)
        return self._layers[loop]

    async def new_channel(self, prefix='specific.'):
        """Create a new channel name for one socket and start listening on it."""
        return await self._loop_layer().new_channel(prefix)

    async def send(self, channel, message):
        """Send a message to one channel (used by kick to reach a single member)."""
        await self._loop_layer().send(channel, message)

    async def receive(self, channel):
        """Wait for the next message on a channel and return it as a dict."""
        return await self._loop_layer().receive(channel)

    async def delete_channel(self, channel):
        """Stop listening on a channel and drop its queue. Safe to call twice."""
        await self._loop_layer().delete_channel(channel)

    async def group_add(self, group, channel):
        """Add a channel to a group."""
        await self._loop_layer().group_add(group, channel)

    async def group_discard(self, group, channel):
        """Remove a channel from a group (no error if it isn't in it)."""
        await self._loop_layer().group_discard(group, channel)

    async def group_send(self, group, message):
        """Send a message to every channel in a group, in every process."""
        await self._loop_layer().group_send(group, message)

    async def flush(self):
        """Forget every channel and group on this loop and close its Redis connections."""
        await self._loop_layer().flush()


def _flush_before_close(channel_layer, loop):
    """Make `loop.close()` first close that loop's Redis connections (same as channels_redis).

    The short-lived loops that async_to_sync creates are closed straight after the call;
    without this, each one would leave an open Redis connection behind.
    """
    original_close = loop.close

    def close_and_flush():
        """Flush this loop's layer, then do the normal close."""
        loop_layer = channel_layer._layers.pop(loop, None)
        if loop_layer is not None:
            loop.run_until_complete(loop_layer.flush())
        loop.close = original_close
        return original_close()

    loop.close = close_and_flush


class _LoopLayer:
    """Everything one event loop needs: its Redis connections, local queues and groups."""

    def __init__(self, url, prefix):
        self.url = url
        self.prefix = prefix
        self.channels = {}  # channel name -> asyncio.Queue of raw (still-encoded) messages
        self.groups = {}  # Redis group key -> set of local channel names in that group
        self._subscribed_to = set()  # Redis names this loop is subscribed to right now
        # One lock so a publish, subscribe, unsubscribe or shutdown never overlap on the
        # shared connections (e.g. the reader stopping while a new socket subscribes).
        self._lock = asyncio.Lock()
        self._redis = None  # client used for PUBLISH (opened on first use)
        self._pubsub = None  # the one subscription connection shared by every socket
        self._reader = None  # background task reading the subscription connection

    def _group_key(self, group):
        """Redis name for a group, e.g. 'asgi__group__room_ABC123' (same as channels_redis)."""
        return f'{self.prefix}__group__{group}'

    # --- the layer API

    async def new_channel(self, prefix):
        """Make a unique channel name, give it a queue, and subscribe to it."""
        channel = f'{self.prefix}{prefix}{uuid.uuid4().hex}'
        self.channels[channel] = asyncio.Queue()
        await self._subscribe(channel)
        return channel

    async def send(self, channel, message):
        """Publish to one channel."""
        await self._publish(channel, msgpack.packb(message))

    async def receive(self, channel):
        """Wait for the next message for `channel` and decode it."""
        if channel not in self.channels:
            self.channels[channel] = asyncio.Queue()
            await self._subscribe(channel)
        try:
            data = await self.channels[channel].get()
        except asyncio.CancelledError:
            # Being cancelled means the consumer is exiting (same assumption as
            # channels_redis), so clean the channel up before letting the cancel through.
            await self.delete_channel(channel)
            raise
        return msgpack.unpackb(data)

    async def delete_channel(self, channel):
        """Drop the channel's queue and unsubscribe from it. Does nothing if already gone."""
        if self.channels.pop(channel, None) is not None:
            try:
                await self._unsubscribe(channel)
            except Exception:
                logger.exception('Unexpected exception while cleaning up channel:')

    async def group_add(self, group, channel):
        """Add a local channel to a group and make sure this loop listens to the group."""
        if channel not in self.channels:
            raise RuntimeError(
                'You can only call group_add() on channels that exist in-process.\n'
                'Consumers are encouraged to use the common pattern:\n'
                f'   self.channel_layer.group_add({group!r}, self.channel_name)'
            )
        key = self._group_key(group)
        self.groups.setdefault(key, set()).add(channel)
        await self._subscribe(key)

    async def group_discard(self, group, channel):
        """Remove a channel from a group; unsubscribe when no local channel is left in it."""
        key = self._group_key(group)
        members = self.groups.get(key, set())
        if channel not in members:
            return
        members.remove(channel)
        if not members:
            del self.groups[key]
            await self._unsubscribe(key)

    async def group_send(self, group, message):
        """Publish to a group's Redis name; every process listening to it gets a copy."""
        await self._publish(self._group_key(group), msgpack.packb(message))

    async def flush(self):
        """Forget all channels and groups and close both Redis connections."""
        async with self._lock:
            self.channels = {}
            self.groups = {}
            self._subscribed_to = set()
            await self._stop_reader()
            if self._redis is not None:
                await self._redis.aclose(close_connection_pool=True)
                self._redis = None

    # --- Redis plumbing

    def _ensure_redis(self):
        """Open the client (and its connection pool) on first use."""
        if self._redis is None:
            self._redis = aioredis.Redis.from_url(self.url)

    async def _publish(self, name, data):
        """PUBLISH raw bytes to a Redis channel."""
        async with self._lock:
            self._ensure_redis()
            await self._redis.publish(name, data)

    async def _subscribe(self, name):
        """SUBSCRIBE to a Redis name; opens the subscription connection and reader if needed."""
        async with self._lock:
            if name in self._subscribed_to:
                return
            self._ensure_redis()
            if self._pubsub is None:
                self._pubsub = self._redis.pubsub()
            await self._pubsub.subscribe(name)
            self._subscribed_to.add(name)
            if self._reader is None:
                self._reader = asyncio.ensure_future(self._read_forever())

    async def _unsubscribe(self, name):
        """UNSUBSCRIBE from a Redis name; when nothing is left, stop the reader (decision 6)."""
        async with self._lock:
            if name not in self._subscribed_to:
                return
            await self._pubsub.unsubscribe(name)
            self._subscribed_to.remove(name)
            if not self._subscribed_to:
                await self._stop_reader()

    async def _stop_reader(self):
        """Cancel the reader task and close the subscription connection. Caller holds the lock."""
        if self._reader is not None:
            self._reader.cancel()
            try:
                await self._reader
            except asyncio.CancelledError:
                pass
            self._reader = None
        if self._pubsub is not None:
            await self._pubsub.aclose()
            self._pubsub = None

    async def _read_forever(self):
        """Background task: read every message for this loop and hand it to the right queues.

        One task per loop, not per socket: Redis sends everything this loop subscribed to down
        one connection, so a single reader sorts it out. Polling with a 0.1 s timeout (as
        channels_redis does) lets subscribe/unsubscribe use the same connection in between.
        """
        while True:
            try:
                message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
                if message is not None:
                    self._deliver(message)
            except asyncio.CancelledError:
                raise
            except Exception:
                # e.g. Redis restarted: log, wait, and try again (redis-py reconnects and
                # re-subscribes on the next read). Same as channels_redis.
                logger.exception('Unexpected exception in receive task')
                await asyncio.sleep(1)

    def _deliver(self, message):
        """Put one Redis message into the queue of every local socket that should get it.

        The message is still the raw msgpack bytes; each socket decodes its own copy in
        receive(), so one consumer changing its dict can't affect another's. Queues have no
        size limit (rule 7: no backpressure), so put_nowait never blocks the reader.
        """
        name = message['channel']
        if isinstance(name, bytes):
            name = name.decode()
        data = message['data']
        if name in self.channels:
            # A direct send to one socket (kick).
            self.channels[name].put_nowait(data)
        elif name in self.groups:
            # A group send: one copy for every local socket in the group.
            for channel in self.groups[name]:
                if channel in self.channels:
                    self.channels[channel].put_nowait(data)


_channel_layers = {}  # alias -> layer instance, created on first use


def get_channel_layer(alias='default'):
    """Return the layer configured in settings.CHANNEL_LAYERS, or None if there isn't one.

    Like Channels, BACKEND names the class to create (with CONFIG as its arguments), and the
    instance is created once and then reused.
    """
    if alias not in _channel_layers:
        config = settings.CHANNEL_LAYERS.get(alias)
        if config is None:
            return None
        module_path, class_name = config['BACKEND'].rsplit('.', 1)
        backend = getattr(import_module(module_path), class_name)
        _channel_layers[alias] = backend(**config.get('CONFIG', {}))
    return _channel_layers[alias]


# --- DB access from consumers -----------------------------------------------------------

def database_sync_to_async(func):
    """Decorator: run a blocking DB helper on a worker thread, inside its own `db` scope.

    Each call gets a fresh `db` that is closed when the call returns (rule 1), so a socket
    never holds a DB connection while it sits open. thread_sensitive=False lets calls from
    different sockets run on different threads at once (Channels pushed them all through one).
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        call = functools.partial(func, *args, **kwargs)
        return await sync_to_async(_in_own_db_scope, thread_sensitive=False)(call)
    return wrapper


# --- Consumers --------------------------------------------------------------------------

class StopConsumer(Exception):
    """Raised after websocket.disconnect to end the consumer's loop cleanly."""


def get_handler_name(message):
    """Turn a message type into a method name: 'websocket.connect' -> 'websocket_connect'."""
    if 'type' not in message:
        raise ValueError("Incoming message has no 'type' attribute")
    handler_name = message['type'].replace('.', '_')
    if handler_name.startswith('_'):
        raise ValueError('Malformed type in message (leading underscore)')
    return handler_name


class AsyncWebsocketConsumer:
    """Base class for a WebSocket consumer: one instance per open socket.

    Subclasses override connect / receive / disconnect and add one method per layer event
    type. Everything else matches channels.generic.websocket.AsyncWebsocketConsumer, except
    that send() after our own close(), or after the browser has gone, is dropped instead of
    raising.
    """

    channel_layer_alias = 'default'

    def __init__(self, **kwargs):
        """Nothing to set up; state is created in __call__ once the socket arrives."""

    @classmethod
    def as_asgi(cls, **initkwargs):
        """Return an ASGI app that creates one consumer per socket.

        It's an object, not a function like in Channels: Starlette's WebSocketRoute treats a
        plain function as `func(websocket)`, but passes any other callable the raw ASGI
        (scope, receive, send).
        """
        return _ConsumerApp(cls, initkwargs)

    async def __call__(self, scope, receive, send):
        """Serve one socket: get a channel, then handle socket and layer messages until it closes."""
        # Channels' URL router put URL parameters in scope['url_route']; Starlette puts them in
        # scope['path_params']. Copy them over so self.scope['url_route']['kwargs'] works.
        self.scope = dict(scope, url_route={'args': (), 'kwargs': dict(scope.get('path_params', {}))})
        self.channel_layer = get_channel_layer(self.channel_layer_alias)
        self.channel_name = await self.channel_layer.new_channel()
        self.base_send = send

        # The race (same as Channels' await_many_dispatch): keep one pending wait on each of
        # the two inputs, the browser (receive) and the layer (our channel's queue). Whichever
        # finishes first is handled completely, then a new wait for that input is started.
        # Only one message is handled at a time, so handlers never overlap.
        sources = [receive, functools.partial(self.channel_layer.receive, self.channel_name)]
        waits = [asyncio.ensure_future(source()) for source in sources]
        try:
            while True:
                await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
                for i, wait in enumerate(waits):
                    if wait.done():
                        await self.dispatch(wait.result())
                        waits[i] = asyncio.ensure_future(sources[i]())
        except StopConsumer:
            pass
        finally:
            # Cleanup on disconnect (or crash): stop both pending waits, then drop this
            # socket's queue and channel subscription. Groups are not touched here; the
            # consumer's disconnect() leaves them with group_discard, as in Channels.
            for wait in waits:
                wait.cancel()
                try:
                    await wait
                except asyncio.CancelledError:
                    pass
            await self.channel_layer.delete_channel(self.channel_name)

    async def dispatch(self, message):
        """Call the method named after message['type']. A missing method is an error, not a skip."""
        handler = getattr(self, get_handler_name(message), None)
        if handler:
            await handler(message)
        else:
            raise ValueError('No handler for message type %s' % message['type'])

    # --- ASGI events from the browser, routed here by dispatch()

    async def websocket_connect(self, message):
        """The browser opened the socket."""
        await self.connect()

    async def websocket_receive(self, message):
        """The browser sent a frame: pass its text or bytes to receive()."""
        if message.get('text') is not None:
            await self.receive(text_data=message['text'])
        else:
            await self.receive(bytes_data=message['bytes'])

    async def websocket_disconnect(self, message):
        """The socket closed: run disconnect(), then stop the loop."""
        await self.disconnect(message['code'])
        raise StopConsumer()

    # --- methods subclasses override

    async def connect(self):
        """Called when a socket opens. Default: accept it."""
        await self.accept()

    async def receive(self, text_data=None, bytes_data=None):
        """Called with each frame from the browser. Default: ignore it."""

    async def disconnect(self, code):
        """Called when the socket has closed. Default: nothing."""

    # --- sending to the browser

    async def _send_to_browser(self, message):
        """Hand one message to the server, or drop it if the browser has already gone.

        The ASGI spec has the server raise an OSError when the app sends on a socket the
        browser has left (uvicorn raises ClientDisconnected; daphne dropped the send).
        Letting it escape would end the consumer before disconnect() runs and orphan its
        membership row. So treat the socket as closed and drop the message instead: the
        server has already queued websocket.disconnect, which runs disconnect() next.
        """
        try:
            await self.base_send(message)
        except OSError:
            self._closing = True

    async def accept(self, subprotocol=None, headers=None):
        """Accept the socket (finishes the handshake)."""
        message = {'type': 'websocket.accept', 'subprotocol': subprotocol}
        if headers:
            message['headers'] = list(headers)
        await self._send_to_browser(message)

    async def send(self, text_data=None, bytes_data=None, close=False):
        """Send a text or bytes frame to the browser, optionally closing afterwards."""
        if getattr(self, '_closing', False):
            # We already closed this socket. A layer event can still be queued behind the
            # close (e.g. the kick broadcast reaching the kicked user right after user_kicked);
            # uvicorn raises on any send after a close, which would crash the consumer
            # before disconnect() runs. So we drop it ourselves.
            return
        if text_data is not None:
            await self._send_to_browser({'type': 'websocket.send', 'text': text_data})
        elif bytes_data is not None:
            await self._send_to_browser({'type': 'websocket.send', 'bytes': bytes_data})
        else:
            raise ValueError('You must pass one of bytes_data or text_data')
        if close:
            await self.close(close)

    async def close(self, code=None, reason=None):
        """Close the socket from the server side.

        After accept(), the server sends a real close frame carrying `code`, so the browser
        sees e.g. 4005. Before accept() there is no socket yet, so the server can only refuse
        the handshake (HTTP 403), and the browser reports 1006. That's why reject() in
        rooms/consumers.py accepts first and then closes.
        """
        if getattr(self, '_closing', False):
            # Already closed (by us, or the browser left): uvicorn raises on a second close.
            return
        message = {'type': 'websocket.close'}
        if code is not None and code is not True:
            message['code'] = code
        if reason:
            message['reason'] = reason
        await self._send_to_browser(message)
        self._closing = True


class _ConsumerApp:
    """The ASGI app returned by as_asgi(): makes a fresh consumer for every socket."""

    def __init__(self, consumer_class, initkwargs):
        self.consumer_class = consumer_class
        self.consumer_initkwargs = initkwargs

    async def __call__(self, scope, receive, send):
        """Create the consumer and let it serve this socket."""
        consumer = self.consumer_class(**self.consumer_initkwargs)
        return await consumer(scope, receive, send)


# --- Origin check -----------------------------------------------------------------------

class OriginValidator:
    """Lets a socket through only if its Origin header (the site the page came from) is allowed.

    Stops another website from opening a socket to us with the visitor's cookies.
    """

    def __init__(self, application, allowed_origins):
        self.application = application
        self.allowed_origins = allowed_origins

    async def __call__(self, scope, receive, send):
        """Pass allowed sockets on to the app; refuse the rest at the handshake."""
        origin = None
        for name, value in scope.get('headers', []):
            if name == b'origin':
                origin = urlparse(value.decode('latin1'))
        if self.valid_origin(origin):
            return await self.application(scope, receive, send)
        return await _deny(scope, receive, send)

    def valid_origin(self, origin):
        """True if the origin's hostname matches an allowed pattern. No Origin: only with '*'."""
        if '*' in self.allowed_origins:
            return True
        if origin is None or origin.hostname is None:
            return False
        for pattern in self.allowed_origins:
            # '//' + pattern makes urlparse read it as a host: strips a port, and turns
            # '[::1]' into '::1' the way it does for the origin.
            pattern_host = urlparse('//' + pattern).hostname or pattern
            if _is_same_domain(origin.hostname, pattern_host):
                return True
        return False


async def _deny(scope, receive, send):
    """Refuse a socket: close before accepting, so the server answers the handshake with 403."""
    await receive()  # websocket.connect
    await send({'type': 'websocket.close'})


def AllowedHostsOriginValidator(application):
    """OriginValidator using ALLOWED_HOSTS (localhost names when DEBUG and the list is empty)."""
    allowed_hosts = settings.ALLOWED_HOSTS
    if settings.DEBUG and not allowed_hosts:
        allowed_hosts = ['localhost', '127.0.0.1', '[::1]']
    return OriginValidator(application, allowed_hosts)
