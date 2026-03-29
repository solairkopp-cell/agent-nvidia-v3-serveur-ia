

websockets Documentation
## Release 9.0
## Aymeric Augustin
## May 01, 2021



## CONTENTS
## 1    Tutorials3
1.1Getting started   .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .3
1.2FAQ .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .11
2    How-to guides19
2.1Cheat sheet  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .19
2.2Deployment    .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .20
2.3Extensions   .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .23
2.4Deploying to Heroku  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .24
## 3    Reference27
3.1API  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .27
## 4    Discussions49
4.1Design   .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .49
4.2Limitations  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .56
4.3Security .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .56
## 5    Project59
5.1Changelog   .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .59
5.2Contributing   .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .69
5.3License  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .70
5.4websockets for enterprise    .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .71
## Python Module Index73
## Index75
i

ii

websockets Documentation, Release 9.0
websocketsis  a  library  for  building  WebSocket  servers  and  clients  in  Python  with  a  focus  on  correctness  and
simplicity.
Built on top ofasyncio, Python’s standard asynchronous I/O framework, it provides an elegant coroutine-based
## API.
Here’s how a client sends and receives messages:
#!/usr/bin/env python
import asyncio
import websockets
async defhello():
uri = "ws://localhost:8765"
async withwebsockets.connect(uri)aswebsocket:
awaitwebsocket.send("Hello world!")
awaitwebsocket.recv()
asyncio.get_event_loop().run_until_complete(hello())
And here’s an echo server:
#!/usr/bin/env python
import asyncio
import websockets
async defecho(websocket, path):
async formessageinwebsocket:
awaitwebsocket.send(message)
start_server = websockets.serve(echo, "localhost", 8765)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
Do you like it? Let’s dive in!
## CONTENTS1

websockets Documentation, Release 9.0
## 2CONTENTS

## CHAPTER
## ONE
## TUTORIALS
If you’re new towebsockets, this is the place to start.
1.1  Getting started
## 1.1.1  Requirements
websocketsrequires Python  3.6.1.
You should use the latest version of Python if possible. If you’re using an older version, be aware that for each minor
version (3.x), only the latest bugfix release (3.x.y) is officially supported.
## 1.1.2  Installation
## Installwebsocketswith:
pip install websockets
1.1.3  Basic example
Here’s a WebSocket server example.
It reads a name from the client, sends a greeting, and closes the connection.
#!/usr/bin/env python
# WS server example
import asyncio
import websockets
async defhello(websocket, path):
name =awaitwebsocket.recv()
print(f"<{name}")
greeting = f"Hello{name}!"
awaitwebsocket.send(greeting)
print(f">{greeting}")
(continues on next page)
## 3

websockets Documentation, Release 9.0
(continued from previous page)
start_server = websockets.serve(hello, "localhost", 8765)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
On the server side,websocketsexecutes the handler coroutinehelloonce for each WebSocket connection.  It
closes the connection when the handler coroutine returns.
Here’s a corresponding WebSocket client example.
#!/usr/bin/env python
# WS client example
import asyncio
import websockets
async defhello():
uri = "ws://localhost:8765"
async withwebsockets.connect(uri)aswebsocket:
name = input("What's your name? ")
awaitwebsocket.send(name)
print(f">{name}")
greeting =awaitwebsocket.recv()
print(f"<{greeting}")
asyncio.get_event_loop().run_until_complete(hello())
Usingconnect()as an asynchronous context manager ensures the connection is closed before exiting thehello
coroutine.
1.1.4  Secure example
Secure WebSocket connections improve confidentiality and also reliability because they reduce the risk of interference
by bad proxies.
The WSS protocol is to WS what HTTPS is to HTTP: the connection is encrypted with Transport Layer Security
(TLS) — which is often referred to as Secure Sockets Layer (SSL). WSS requires TLS certificates like HTTPS.
Here’s how to adapt the server example to provide secure connections. See the documentation of thesslmodule for
configuring the context securely.
#!/usr/bin/env python
# WSS (WS over TLS) server example, with a self-signed certificate
import asyncio
import pathlib
import ssl
import websockets
async defhello(websocket, path):
name =awaitwebsocket.recv()
print(f"<{name}")
(continues on next page)
4Chapter 1.  Tutorials

websockets Documentation, Release 9.0
(continued from previous page)
greeting = f"Hello{name}!"
awaitwebsocket.send(greeting)
print(f">{greeting}")
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
localhost_pem = pathlib.Path(__file__).with_name("localhost.pem")
ssl_context.load_cert_chain(localhost_pem)
start_server = websockets.serve(
hello, "localhost", 8765, ssl=ssl_context
## )
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
Here’s how to adapt the client.
#!/usr/bin/env python
# WSS (WS over TLS) client example, with a self-signed certificate
import asyncio
import pathlib
import ssl
import websockets
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
localhost_pem = pathlib.Path(__file__).with_name("localhost.pem")
ssl_context.load_verify_locations(localhost_pem)
async defhello():
uri = "wss://localhost:8765"
async withwebsockets.connect(
uri, ssl=ssl_context
## )aswebsocket:
name = input("What's your name? ")
awaitwebsocket.send(name)
print(f">{name}")
greeting =awaitwebsocket.recv()
print(f"<{greeting}")
asyncio.get_event_loop().run_until_complete(hello())
This client needs a context because the server uses a self-signed certificate.
A  client  connecting  to  a  secure  WebSocket  server  with  a  valid  certificate  (i.e.   signed  by  a  CA  that  your  Python
installation trusts) can simply passssl=Truetoconnect()instead of building a context.
1.1.  Getting started5

websockets Documentation, Release 9.0
1.1.5  Browser-based example
Here’s an example of how to run a WebSocket server and connect from a browser.
Run this script in a console:
#!/usr/bin/env python
# WS server that sends messages at random intervals
import asyncio
import datetime
import random
import websockets
async deftime(websocket, path):
while True:
now = datetime.datetime.utcnow().isoformat() + "Z"
awaitwebsocket.send(now)
awaitasyncio.sleep(random.random()
## *
## 3)
start_server = websockets.serve(time, "127.0.0.1", 5678)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
Then open this HTML file in a browser.
<!DOCTYPE html>
## <html>
## <head>
<title>WebSocket demo</title>
## </head>
## <body>
## <script>
varws =newWebSocket("ws://127.0.0.1:5678/"),
messages = document.createElement('ul');
ws.onmessage =function(event) {
varmessages = document.getElementsByTagName('ul')[0],
message = document.createElement('li'),
content = document.createTextNode(event.data);
message.appendChild(content);
messages.appendChild(message);
## };
document.body.appendChild(messages);
## </script>
## </body>
## </html>
6Chapter 1.  Tutorials

websockets Documentation, Release 9.0
1.1.6  Synchronization example
A WebSocket server can receive events from clients, process them to update the application state, and synchronize the
resulting state across clients.
Here’s an example where any client can increment or decrement a counter.  Updates are propagated to all connected
clients.
The concurrency model ofasyncioguarantees that updates are serialized.
Run this script in a console:
#!/usr/bin/env python
# WS server example that synchronizes state across clients
import asyncio
import json
import logging
import websockets
logging.basicConfig()
STATE = {"value": 0}
USERS = set()
defstate_event():
returnjson.dumps({"type": "state",
## **
## STATE})
defusers_event():
returnjson.dumps({"type": "users", "count": len(USERS)})
async defnotify_state():
ifUSERS:# asyncio.wait doesn't accept an empty list
message = state_event()
awaitasyncio.wait([user.send(message)foruserinUSERS])
async defnotify_users():
ifUSERS:# asyncio.wait doesn't accept an empty list
message = users_event()
awaitasyncio.wait([user.send(message)foruserinUSERS])
async defregister(websocket):
USERS.add(websocket)
awaitnotify_users()
async defunregister(websocket):
USERS.remove(websocket)
awaitnotify_users()
async defcounter(websocket, path):
(continues on next page)
1.1.  Getting started7

websockets Documentation, Release 9.0
(continued from previous page)
# register(websocket) sends user_event() to websocket
awaitregister(websocket)
try:
awaitwebsocket.send(state_event())
async formessageinwebsocket:
data = json.loads(message)
ifdata["action"] == "minus":
STATE["value"] -= 1
awaitnotify_state()
elifdata["action"] == "plus":
STATE["value"] += 1
awaitnotify_state()
else:
logging.error("unsupported event:%s", data)
finally:
awaitunregister(websocket)
start_server = websockets.serve(counter, "localhost", 6789)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
Then open this HTML file in several browsers.
<!DOCTYPE html>
## <html>
## <head>
<title>WebSocket demo</title>
## <styletype="text/css">
body{
font-family: "Courier New",sans-serif;
text-align:center;
## }
## .buttons{
font-size: 4em;
display:flex;
justify-content:center;
## }
## .button, .value{
line-height: 1;
padding: 2rem;
margin: 2rem;
border:medium solid;
min-height: 1em;
min-width: 1em;
## }
## .button{
cursor:pointer;
user-select:none;
## }
## .minus{
color:red;
## }
## .plus{
color:green;
## }
(continues on next page)
8Chapter 1.  Tutorials

websockets Documentation, Release 9.0
(continued from previous page)
## .value{
min-width: 2em;
## }
## .state{
font-size: 2em;
## }
## </style>
## </head>
## <body>
## <divclass="buttons">
<divclass="minus button">-</div>
## <divclass="value">?</div>
<divclass="plus button">+</div>
## </div>
## <divclass="state">
<spanclass="users">?</span> online
## </div>
## <script>
varminus = document.querySelector('.minus'),
plus = document.querySelector('.plus'),
value = document.querySelector('.value'),
users = document.querySelector('.users'),
websocket =newWebSocket("ws://127.0.0.1:6789/");
minus.onclick =function(event) {
websocket.send(JSON.stringify({action: 'minus'}));
## }
plus.onclick =function(event) {
websocket.send(JSON.stringify({action: 'plus'}));
## }
websocket.onmessage =function(event) {
data = JSON.parse(event.data);
switch(data.type) {
case'state':
value.textContent = data.value;
break;
case'users':
users.textContent = (
data.count.toString() + " user" +
## (data.count == 1 ? "" : "s"));
break;
default:
console.error(
"unsupported event", data);
## }
## };
## </script>
## </body>
## </html>
1.1.  Getting started9

websockets Documentation, Release 9.0
1.1.7  Common patterns
You will usually want to process several messages during the lifetime of a connection.  Therefore you must write a
loop. Here are the basic patterns for building a WebSocket server.
## Consumer
For receiving messages and passing them to aconsumercoroutine:
async defconsumer_handler(websocket, path):
async formessageinwebsocket:
awaitconsumer(message)
In this example,consumerrepresents your business logic for processing messages received on the WebSocket con-
nection.
Iteration terminates when the client disconnects.
## Producer
For getting messages from aproducercoroutine and sending them:
async defproducer_handler(websocket, path):
while True:
message =awaitproducer()
awaitwebsocket.send(message)
In this example,producerrepresents your business logic for generating messages to send on the WebSocket con-
nection.
send()raises aConnectionClosedexception when the client disconnects,  which breaks out of thewhile
## Trueloop.
## Both
You can read and write messages on the same connection by combining the two patterns shown above and running the
two tasks in parallel:
async defhandler(websocket, path):
consumer_task = asyncio.ensure_future(
consumer_handler(websocket, path))
producer_task = asyncio.ensure_future(
producer_handler(websocket, path))
done, pending =awaitasyncio.wait(
[consumer_task, producer_task],
return_when=asyncio.FIRST_COMPLETED,
## )
fortaskinpending:
task.cancel()
10Chapter 1.  Tutorials

websockets Documentation, Release 9.0
## Registration
As shown in the synchronization example above, if you need to maintain a list of currently connected clients, you must
register them when they connect and unregister them when they disconnect.
connected = set()
async defhandler(websocket, path):
## # Register.
connected.add(websocket)
try:
# Broadcast a message to all connected clients.
awaitasyncio.wait([ws.send("Hello!")forwsinconnected])
awaitasyncio.sleep(10)
finally:
## # Unregister.
connected.remove(websocket)
This simplistic example keeps track of connected clients in memory.  This only works as long as you run a single
process. In a practical application, the handler may subscribe to some channels on a message broker, for example.
1.1.8  That’s all!
The design of thewebsocketsAPI was driven by simplicity.
You  don’t  have  to  worry  about  performing  the  opening  or  the  closing  handshake,  answering  pings,  or  any  other
behavior required by the specification.
websocketshandles all this under the hood so you don’t have to.
1.1.9  One more thing. . .
websocketsprovides an interactive client:
$ python -m websockets wss://echo.websocket.org/
## 1.2  FAQ
Note:Many questions asked inwebsockets’ issue tracker are actually aboutasyncio. Python’s documentation
about developing with asyncio is a good complement.
## 1.2.  FAQ11

websockets Documentation, Release 9.0
1.2.1  Server side
Why does the server close the connection after processing one message?
Your connection handler exits after processing one message. Write a loop to process multiple messages.
For example, if your handler looks like this:
async defhandler(websocket, path):
print(websocket.recv())
change it like this:
async defhandler(websocket, path):
async formessageinwebsocket:
print(message)
Don’t feel bad if this happens to you — it’s the most common question in websockets’ issue tracker :-)
Why can only one client connect at a time?
Your connection handler blocks the event loop.  Look for blocking calls.  Any call that may take some time must be
asynchronous.
For example, if you have:
async defhandler(websocket, path):
time.sleep(1)
change it to:
async defhandler(websocket, path):
awaitasyncio.sleep(1)
This is part of learning asyncio. It isn’t specific to websockets.
See also Python’s documentation about running blocking code.
How can I pass additional arguments to the connection handler?
You can bind additional arguments to the connection handler withfunctools.partial():
import asyncio
import functools
import websockets
async defhandler(websocket, path, extra_argument):
## ...
bound_handler = functools.partial(handler, extra_argument='spam')
start_server = websockets.serve(bound_handler, ...)
Another way to achieve this result is to define thehandlercoroutine in a scope where theextra_argument
variable exists instead of injecting it through an argument.
12Chapter 1.  Tutorials

websockets Documentation, Release 9.0
How do I get access HTTP headers, for example cookies?
To access HTTP headers during the WebSocket handshake, you can overrideprocess_request:
async defprocess_request(self, path, request_headers):
cookies = request_header["Cookie"]
Once the connection is established, they’re available inrequest_headers:
async defhandler(websocket, path):
cookies = websocket.request_headers["Cookie"]
How do I get the IP address of the client connecting to my server?
It’s available inremote_address:
async defhandler(websocket, path):
remote_ip = websocket.remote_address[0]
How do I set which IP addresses my server listens to?
Look at thehostargument ofcreate_server().
serve()accepts the same arguments ascreate_server().
How do I close a connection properly?
websockets takes care of closing the connection when the handler exits.
How do I run a HTTP server and WebSocket server on the same port?
This isn’t supported.
Providing a HTTP server is out of scope for websockets. It only aims at providing a WebSocket server.
There’s limited support for returning HTTP responses with theprocess_requesthook. If you need more, pick a
HTTP server and run it separately.
1.2.2  Client side
How do I close a connection properly?
The easiest is to useconnect()as a context manager:
async withconnect(...)aswebsocket:
## ...
## 1.2.  FAQ13

websockets Documentation, Release 9.0
How do I reconnect automatically when the connection drops?
See issue 414.
How do I stop a client that is continuously processing messages?
You can close the connection.
Here’s an example that terminates cleanly when it receives SIGTERM on Unix:
#!/usr/bin/env python
import asyncio
import signal
import websockets
async defclient():
uri = "ws://localhost:8765"
async withwebsockets.connect(uri)aswebsocket:
# Close the connection when receiving SIGTERM.
loop = asyncio.get_event_loop()
loop.add_signal_handler(
signal.SIGTERM, loop.create_task, websocket.close())
# Process messages received on the connection.
async formessageinwebsocket:
## ...
asyncio.get_event_loop().run_until_complete(client())
How do I disable TLS/SSL certificate verification?
Look at thesslargument ofcreate_connection().
connect()accepts the same arguments ascreate_connection().
1.2.3  Both sides
How do I do two things in parallel? How do I integrate with another coroutine?
You must start two tasks, which the event loop will run concurrently. You can achieve this withasyncio.gather()
orasyncio.wait().
This is also part of learning asyncio and not specific to websockets.
Keep track of the tasks and make sure they terminate or you cancel them when the connection terminates.
14Chapter 1.  Tutorials

websockets Documentation, Release 9.0
How do I create channels or topics?
websockets doesn’t have built-in publish / subscribe for these use cases.
Depending on the scale of your service,  a simple in-memory implementation may do the job or you may need an
external publish / subscribe component.
What doesConnectionClosedError:  code = 1006mean?
If you’re seeing this traceback in the logs of a server:
Error in connection handler
Traceback (most recent call last):
## ...
asyncio.streams.IncompleteReadError: 0 bytes read on a total of 2 expected bytes
The above exception was the direct cause of the following exception:
Traceback (most recent call last):
## ...
websockets.exceptions.ConnectionClosedError: code = 1006 (connection closed
˓→abnormally [internal]), no reason
or if a client crashes with this traceback:
Traceback (most recent call last):
## ...
ConnectionResetError: [Errno 54] Connection reset by peer
The above exception was the direct cause of the following exception:
Traceback (most recent call last):
## ...
websockets.exceptions.ConnectionClosedError: code = 1006 (connection closed
˓→abnormally [internal]), no reason
it means that the TCP connection was lost. As a consequence, the WebSocket connection was closed without receiving
a close frame, which is abnormal.
You can catch and handleConnectionClosedto prevent it from being logged.
There are several reasons why long-lived connections may be lost:
-  End-user devices tend to lose network connectivity often and unpredictably because they can move out of wire-
less network coverage, get unplugged from a wired network, enter airplane mode, be put to sleep, etc.
-  HTTP load balancers or proxies that aren’t configured for long-lived connections may terminate connections
after a short amount of time, usually 30 seconds.
If you’re facing a reproducible issue,enable debug logsto see when and how connections are closed.
## 1.2.  FAQ15

websockets Documentation, Release 9.0
How can I pass additional arguments to a custom protocol subclass?
You can bind additional arguments to the protocol factory withfunctools.partial():
import asyncio
import functools
import websockets
class MyServerProtocol(websockets.WebSocketServerProtocol):
def__init__(self, extra_argument,
## *
args,
## **
kwargs):
super().__init__(
## *
args,
## **
kwargs)
# do something with extra_argument
create_protocol = functools.partial(MyServerProtocol, extra_argument='spam')
start_server = websockets.serve(..., create_protocol=create_protocol)
This example was for a server. The same pattern applies on a client.
Why do I get the error:module 'websockets' has no attribute '...'?
Often, this is because you created a script calledwebsockets.pyin your current working directory. Thenimport
websocketsimports this module instead of the websockets library.
Are thereonopen,onmessage,onerror, andonclosecallbacks?
No, there aren’t.
websockets provides high-level, coroutine-based APIs.  Compared to callbacks, coroutines make it easier to manage
control flow in concurrent code.
If you prefer callback-based APIs, you should use another library.
Can I usewebsocketssynchronously, withoutasync/await?
You can convert every asynchronous call to a synchronous call by wrapping it inasyncio.get_event_loop().
run_until_complete(...).
If this turns out to be impractical, you should use another library.
## 1.2.4  Miscellaneous
How do I set a timeout onrecv()?
## Usewait_for():
awaitasyncio.wait_for(websocket.recv(), timeout=10)
This technique works for most APIs, except for asynchronous context managers. See issue 574.
16Chapter 1.  Tutorials

websockets Documentation, Release 9.0
How do I keep idle connections open?
websockets sends pings at 20 seconds intervals to keep the connection open.
In closes the connection if it doesn’t get a pong within 20 seconds.
You can adjust this behavior withping_intervalandping_timeout.
How do I respond to pings?
websockets takes care of responding to pings with pongs.
Is there a Python 2 version?
No, there isn’t.
websockets builds upon asyncio which requires Python 3.
## 1.2.  FAQ17

websockets Documentation, Release 9.0
18Chapter 1.  Tutorials

## CHAPTER
## TWO
## HOW-TO GUIDES
These guides will help you build and deploy awebsocketsapplication.
2.1  Cheat sheet
## 2.1.1  Server
-  Write a coroutine that handles a single connection. It receives a WebSocket protocol instance and the URI path
in argument.
–Callrecv()andsend()to receive and send messages at any time.
–Whenrecv()orsend()raisesConnectionClosed,  clean  up  and  exit.    If  you  started  other
asyncio.Task, terminate them before exiting.
–If you aren’t awaitingrecv(), consider awaitingwait_closed()to detect quickly when the connec-
tion is closed.
–You mayping()orpong()if you wish but it isn’t needed in general.
-  Create a server withserve()which is similar to asyncio’screate_server().  You can also use it as an
asynchronous context manager.
–The server takes care of establishing connections, then lets the handler execute the application logic, and
finally closes the connection after the handler exits normally or with an exception.
–For advanced customization, you may subclassWebSocketServerProtocoland pass either this sub-
class or a factory function as thecreate_protocolargument.
## 2.1.2  Client
-  Create a client withconnect()which is similar to asyncio’screate_connection().  You can also use
it as an asynchronous context manager.
–For advanced customization, you may subclassWebSocketClientProtocoland pass either this sub-
class or a factory function as thecreate_protocolargument.
-  Callrecv()andsend()to receive and send messages at any time.
-  You mayping()orpong()if you wish but it isn’t needed in general.
-  If you aren’t usingconnect()as a context manager, callclose()to terminate the connection.
## 19

websockets Documentation, Release 9.0
## 2.1.3  Debugging
If you don’t understand whatwebsocketsis doing, enable logging:
import logging
logger = logging.getLogger('websockets')
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())
The logs contain:
-  Exceptions in the connection handler at theERRORlevel
-  Exceptions in the opening or closing handshake at theINFOlevel
-  All frames at theDEBUGlevel — this can be very verbose
If  you’re  new  toasyncio,  you  will  certainly  encounter  issues  that  are  related  to  asynchronous  programming  in
general rather than towebsocketsin particular.  Fortunately Python’s official documentation provides advice to
develop with asyncio. Check it out: it’s invaluable!
## 2.2  Deployment
2.2.1  Application server
The author ofwebsocketsisn’t aware of best practices for deploying network services based onasyncio, let
alone application servers.
You can run a script similar to theserver example, inside a supervisor if you deem that useful.
You can also add a wrapper to daemonize the process. Third-party libraries provide solutions for that.
If you can share knowledge on this topic, please file an issue. Thanks!
2.2.2  Graceful shutdown
You may want to close connections gracefully when shutting down the server, perhaps after executing some cleanup
logic. There are two ways to achieve this with the object returned byserve():
-  using it as a asynchronous context manager, or
-  calling itsclose()method, then waiting for itswait_closed()method to complete.
On Unix systems, shutdown is usually triggered by sending a signal.
Here’s a full example for handling SIGTERM on Unix:
#!/usr/bin/env python
import asyncio
import signal
import websockets
async defecho(websocket, path):
async formessageinwebsocket:
awaitwebsocket.send(message)
(continues on next page)
20Chapter 2.  How-to guides

websockets Documentation, Release 9.0
(continued from previous page)
async defecho_server(stop):
async withwebsockets.serve(echo, "localhost", 8765):
awaitstop
loop = asyncio.get_event_loop()
# The stop condition is set when receiving SIGTERM.
stop = loop.create_future()
loop.add_signal_handler(signal.SIGTERM, stop.set_result,None)
# Run the server until the stop condition is met.
loop.run_until_complete(echo_server(stop))
This example is easily adapted to handle other signals.  If you override the default handler for SIGINT, which raises
KeyboardInterrupt, be aware that you won’t be able to interrupt a program with Ctrl-C anymore when it’s stuck
in a loop.
It’s more difficult to achieve the same effect on Windows. Some third-party projects try to help with this problem.
If your server doesn’t run in the main thread, look atcall_soon_threadsafe().
2.2.3  Memory usage
In most cases, memory usage of a WebSocket server is proportional to the number of open connections. When a server
handles thousands of connections, memory usage can become a bottleneck.
Memory usage of a single connection is the sum of:
-  the baseline amount of memorywebsocketsrequires for each connection,
-  the amount of data held in buffers before the application processes it,
-  any additional memory allocated by the application itself.
## Baseline
Compression settings are the main factor affecting the baseline amount of memory used by each connection.
By defaultwebsocketsmaximizes compression rate at the expense of memory usage. If memory usage is an issue,
lowering compression settings can help:
-  Context Takeover is necessary to get good performance for almost all applications. It should remain enabled.
-  Window Bits is a trade-off between memory usage and compression rate. It defaults to 15 and can be lowered.
The default value isn’t optimal for small, repetitive messages which are typical of WebSocket servers.
-  Memory Level is a trade-off between memory usage and compression speed. It defaults to 8 and can be lowered.
A lower memory level can actually increase speed thanks to memory locality, even if the CPU does more work!
See thisexamplefor how to configure compression settings.
Here’s how various compression settings affect memory usage of a single connection on a 64-bit system, as well a
benchmark of compressed size and compression time for a corpus of small JSON documents.
## 2.2.  Deployment21

websockets Documentation, Release 9.0
CompressionWindow BitsMemory LevelMemory usageSize vs. defaultTime vs. default
default158325 KiB+0%+0%
147181 KiB+1.5%-5.3%
136110 KiB+2.8%-7.5%
12573 KiB+4.4%-18.9%
11455 KiB+8.5%-18.8%
disabledN/AN/A22 KiBN/AN/A
Don’t assume this example is representative!  Compressed size and compression time depend heavily on the kind of
messages exchanged by the application!
You can run the same benchmark for your application by creating a list of typical messages and passing it to the
## _benchmarkfunction.
This blog post by Ilya Grigorik provides more details about how compression settings affect memory usage and how
to optimize them.
This experiment by Peter Thorson suggests Window Bits = 11, Memory Level = 4 as a sweet spot for optimizing
memory usage.
## Buffers
Under normal circumstances, buffers are almost always empty.
Under high load, if a server receives more messages than it can process, bufferbloat can result in excessive memory
use.
By defaultwebsocketshas generous limits.  It is strongly recommended to adapt them to your application.  When
you callserve():
-  Setmax_size(default: 1 MiB, UTF-8 encoded) to the maximum size of messages your application generates.
-  Setmax_queue(default: 32) to the maximum number of messages your application expects to receive faster
than it can process them. The queue provides burst tolerance without slowing down the TCP connection.
Furthermore, you can lowerread_limitandwrite_limit(default:  64 KiB) to reduce the size of buffers for
incoming and outgoing data.
The design document providesmore details about buffers.
2.2.4  Port sharing
The WebSocket protocol is an extension of HTTP/1.1. It can be tempting to serve both HTTP and WebSocket on the
same port.
The author ofwebsocketsdoesn’t think that’s a good idea, due to the widely different operational characteristics
of HTTP and WebSocket.
websocketsprovide minimal support for responding to HTTP requests with theprocess_request()hook.
Typical use cases include health checks. Here’s an example:
#!/usr/bin/env python
# WS echo server with HTTP endpoint at /health/
(continues on next page)
22Chapter 2.  How-to guides

websockets Documentation, Release 9.0
(continued from previous page)
import asyncio
import http
import websockets
async defhealth_check(path, request_headers):
ifpath == "/health/":
returnhttp.HTTPStatus.OK, [], b"OK\n"
async defecho(websocket, path):
async formessageinwebsocket:
awaitwebsocket.send(message)
start_server = websockets.serve(
echo, "localhost", 8765, process_request=health_check
## )
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
## 2.3  Extensions
The WebSocket protocol supports extensions.
At the  time of writing,  there’s only  one registered extension  with a  public specification,  WebSocket  Per-Message
Deflate, specified inRFC 7692.
2.3.1  Per-Message Deflate
connect()andserve()enable the Per-Message Deflate extension by default.
If you want to disable it, setcompression=None:
import websockets
websockets.connect(..., compression=None)
websockets.serve(..., compression=None)
You can also configure the Per-Message Deflate extension explicitly if you want to customize compression settings:
import websockets
from websockets.extensions importpermessage_deflate
websockets.connect(
## ...,
extensions=[
permessage_deflate.ClientPerMessageDeflateFactory(
server_max_window_bits=11,
client_max_window_bits=11,
compress_settings={'memLevel': 4},
## ),
## ],
## )
(continues on next page)
## 2.3.  Extensions23

websockets Documentation, Release 9.0
(continued from previous page)
websockets.serve(
## ...,
extensions=[
permessage_deflate.ServerPerMessageDeflateFactory(
server_max_window_bits=11,
client_max_window_bits=11,
compress_settings={'memLevel': 4},
## ),
## ],
## )
The window bits and memory level values chosen in these examples reduce memory usage. You can read more about
optimizing compression settings.
RefertotheAPIdocumentationofClientPerMessageDeflateFactoryand
ServerPerMessageDeflateFactoryfor details.
2.3.2  Writing an extension
During the opening handshake, WebSocket clients and servers negotiate which extensions will be used with which
parameters. Then each frame is processed by extensions before being sent or after being received.
As a consequence, writing an extension requires implementing several classes:
-  Extension Factory: it negotiates parameters and instantiates the extension.
Clients and servers require separate extension factories with distinct APIs.
Extension factories are the public API of an extension.
-  Extension: it decodes incoming frames and encodes outgoing frames.
If the extension is symmetrical, clients and servers can use the same class.
Extensions are initialized by extension factories, so they don’t need to be part of the public API of an extension.
websocketsprovides abstract base classes for extension factories and extensions.  See the API documentation for
details on their methods:
•ClientExtensionFactoryandServerExtensionFactoryfor extension factories,
•Extensionfor extensions.
2.4  Deploying to Heroku
This guide describes how to deploy a websockets server to Heroku.  We’re going to deploy a very simple app.  The
process would be identical for a more realistic app.
24Chapter 2.  How-to guides

websockets Documentation, Release 9.0
2.4.1  Create application
Deploying to Heroku requires a git repository. Let’s initialize one:
$mkdir websockets-echo
$cd websockets-echo
$git init .
Initialized empty Git repository in websockets-echo/.git/
$git commit --allow-empty -m "Initial commit."
[master (root-commit) 1e7947d] Initial commit.
Follow the set-up instructions to install the Heroku CLI and to log in, if you haven’t done that yet.
Then, create a Heroku app — if you follow these instructions step-by-step, you’ll have to pick a different name because
I’m already usingwebsockets-echoon Heroku:
$$ heroku create websockets-echo
Creating  websockets-echo... done
https://websockets-echo.herokuapp.com/ | https://git.heroku.com/websockets-echo.git
Here’s the implementation of the app, an echo server. Save it in a file calledapp.py:
#!/usr/bin/env python
import asyncio
import os
import websockets
async defecho(websocket, path):
async formessageinwebsocket:
awaitwebsocket.send(message)
start_server = websockets.serve(echo, "", int(os.environ["PORT"]))
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
The server relies on the$PORTenvironment variable to tell on which port it will listen, according to Heroku’s con-
ventions.
2.4.2  Configure deployment
In order to build the app, Heroku needs to know that it depends on websockets. Create arequirements.txtfile
containing this line:
websockets
Heroku also needs to know how to run the app. Create aProcfilewith this content:
web: python app.py
Confirm that you created the correct files and commit them to git:
## $ls
Procfile         app.py           requirements.txt
(continues on next page)
2.4.  Deploying to Heroku25

websockets Documentation, Release 9.0
(continued from previous page)
$git add .
$git commit -m "Deploy echo server to Heroku."
[master 8418c62] Deploy echo server to Heroku.
3 files changed, 19 insertions(+)
create mode 100644 Procfile
create mode 100644 app.py
create mode 100644 requirements.txt
## 2.4.3  Deploy
Our app is ready. Let’s deploy it!
$git push heroku master
... lots of output...
remote: -----> Launching...
remote:        Released v3
remote:        https://websockets-echo.herokuapp.com/ deployed to Heroku
remote:
remote: Verifying deploy... done.
To https://git.heroku.com/websockets-echo.git
## *
[new branch]      master -> master
2.4.4  Validate deployment
Of course we’d like to confirm that our application is running as expected!
Since it’s a WebSocket server, we need a WebSocket client, such as the interactive client that comes with websockets.
If you’re currently building a websockets server, perhaps you’re already in a virtualenv where websockets is installed.
If not, you can install it in a new virtualenv as follows:
$python -m venv websockets-client
$. websockets-client/bin/activate
$pip install websockets
Connect the interactive client — using the name of your Heroku app instead ofwebsockets-echo:
$python -m websockets wss://websockets-echo.herokuapp.com/
Connected to wss://websockets-echo.herokuapp.com/.
## >
Great! Our app is running!
In this example, I used a secure connection (wss://).  It worked because Heroku served a valid TLS certificate for
websockets-echo.herokuapp.com. An insecure connection (ws://) would also work.
Once you’re connected,  you can send any message and the server will echo it,  then press Ctrl-D to terminate the
connection:
## > Hello!
## < Hello!
Connection closed: code = 1000 (OK), no reason.
26Chapter 2.  How-to guides

## CHAPTER
## THREE
## REFERENCE
Find all the details you could ask for, and then some.
## 3.1  API
websocketsprovides complete client and server implementations, as shown in thegetting started guide.
The process for opening and closing a WebSocket connection depends on which side you’re implementing.
-  On the client side, connecting to a server withconnectyields a connection object that provides methods for
interacting with the connection. Your code can open a connection, then send or receive messages.
If you useconnectas an asynchronous context manager, then websockets closes the connection on exit.  If
not, then your code is responsible for closing the connection.
-  On the server side,servestarts listening for client connections and yields an server object that supports closing
the server.
Then, when clients connects, the server initializes a connection object and passes it to a handler coroutine, which
is where your code can send or receive messages.  This pattern is called inversion of control.  It’s common in
frameworks implementing servers.
When the handler coroutine terminates, websockets closes the connection. You may also close it in the handler
coroutine if you’d like.
Once the connection is open, the WebSocket protocol is symmetrical, except for low-level details that websockets
manages under the hood. The same methods are available on client connections created withconnectand on server
connections passed to the connection handler in the arguments.
At this point, websockets provides the same API — and uses the same code — for client and server connections. For
convenience, common methods are documented both in the client API and server API.
## 3.1.1  Client
websockets.legacy.clientdefines the WebSocket client APIs.
## 27

websockets Documentation, Release 9.0
Opening a connection
awaitwebsockets.legacy.client.connect(uri,*,create_protocol=None,ping_interval=20,
ping_timeout=20,close_timeout=None,
max_size=1048576,max_queue=32,
read_limit=65536,write_limit=65536,loop=None,
compression='deflate',origin=None,ex-
tensions=None,subprotocols=None,ex-
tra_headers=None,**kwargs)
Connect to the WebSocket server at the givenuri.
Awaitingconnect()yields aWebSocketClientProtocolwhich can then be used to send and receive
messages.
connect()can also be used as a asynchronous context manager:
async withconnect(...)aswebsocket:
## ...
In that case, the connection is closed when exiting the context.
connect()is a wrapper around the event loop’screate_connection()method.  Unknown keyword
arguments are passed tocreate_connection().
For   example,   you   can   set   thesslkeyword   argument   to   aSSLContextto   enforce   some   TLS
settings.When   connecting   to   awss://URI,   if   this   argument   isn’t   provided   explicitly,ssl.
create_default_context()is called to create a context.
You can connect to a different host and port from those found inuriby settinghostandportkeyword
arguments.  This only changes the destination of the TCP connection.  The host name fromuriis still used in
the TLS handshake for secure connections and in theHostHTTP header.
create_protocoldefaults  toWebSocketClientProtocol.   It  may  be  replaced  by  a  wrapper  or  a
subclass to customize the protocol that manages the connection.
The  behavior  ofping_interval,ping_timeout,close_timeout,max_size,max_queue,
read_limit, andwrite_limitis described inWebSocketClientProtocol.
connect()also accepts the following optional arguments:
•compressionis a shortcut to configure compression extensions; by default it enables the “permessage-
deflate” extension; set it toNoneto disable compression.
•originsets the Origin HTTP header.
•extensionsis a list of supported extensions in order of decreasing preference.
•subprotocolsis a list of supported subprotocols in order of decreasing preference.
•extra_headerssets additional HTTP request headers; it can be aHeadersinstance, aMapping, or
an iterable of(name, value)pairs.
## Raises
•InvalidURI– ifuriis invalid
•InvalidHandshake– if the opening handshake fails
awaitwebsockets.legacy.client.unix_connect(path,uri='ws://localhost/',**kwargs)
Similar toconnect(), but for connecting to a Unix socket.
This function calls the event loop’screate_unix_connection()method.
28Chapter 3.  Reference

websockets Documentation, Release 9.0
It is only available on Unix.
It’s mainly useful for debugging servers listening on Unix sockets.
## Parameters
•path(Optional[str]) – file system path to the Unix socket
•uri(str) – WebSocket URI
Return typeConnect
Using a connection
classwebsockets.legacy.client.WebSocketClientProtocol(*,origin=None,ex-
tensions=None,sub-
protocols=None,ex-
tra_headers=None,
## **kwargs)
Protocolsubclass implementing a WebSocket client.
WebSocketClientProtocol:
-  performs the opening handshake to establish the connection;
-  providesrecv()andsend()coroutines for receiving and sending messages;
-  deals with control frames automatically;
-  performs the closing handshake to terminate the connection.
WebSocketClientProtocolsupports asynchronous iteration:
async formessageinwebsocket:
awaitprocess(message)
The iterator yields incoming messages. It exits normally when the connection is closed with the close code 1000
(OK) or 1001 (going away). It raises aConnectionClosedErrorexception when the connection is closed
with any other code.
Once the connection is open, a Ping frame is sent everyping_intervalseconds. This serves as a keepalive.
It  helps  keeping  the  connection  open,  especially  in  the  presence  of  proxies  with  short  timeouts  on  inactive
connections. Setping_intervaltoNoneto disable this behavior.
If  the  corresponding  Pong  frame  isn’t  received  withinping_timeoutseconds,  the  connection  is  consid-
ered unusable and is closed with code 1011.  This ensures that the remote endpoint remains responsive.  Set
ping_timeouttoNoneto disable this behavior.
Theclose_timeoutparameter defines  a maximum  wait time  for completing the  closing handshake  and
terminating the TCP connection. For legacy reasons,close()completes in at most5
## *
close_timeout
seconds.
close_timeoutneeds to be a parameter of the protocol because websockets usually callsclose()implic-
itly upon exit whenconnect()is used as a context manager.
To apply a timeout to any other API, wrap it inwait_for().
Themax_sizeparameter enforces the maximum size for incoming messages in bytes.  The default value is
1 MiB.Nonedisables the limit.  If a message larger than the maximum size is received,recv()will raise
ConnectionClosedErrorand the connection will be closed with code 1009.
Themax_queueparameter sets the maximum length of the queue that holds incoming messages. The default
value is32.Nonedisables the limit.  Messages are added to an in-memory queue when they’re received; then
## 3.1.  API29

websockets Documentation, Release 9.0
recv()pops from that queue. In order to prevent excessive memory consumption when messages are received
faster than they can be processed, the queue must be bounded. If the queue fills up, the protocol stops processing
incoming data untilrecv()is called. In this situation, various receive buffers (at least inasyncioand in the
OS) will fill up, then the TCP receive window will shrink, slowing down transmission to avoid packet loss.
Since Python can use up to 4 bytes of memory to represent a single character, each connection may use up to
## 4
## *
max_size
## *
max_queuebytes of memory to store incoming messages. By default, this is 128 MiB.
You may want to lower the limits, depending on your application’s requirements.
Theread_limitargument sets the high-water limit of the buffer for incoming bytes. The low-water limit is
half the high-water limit. The default value is 64 KiB, half of asyncio’s default (based on the current implemen-
tation ofStreamReader).
Thewrite_limitargument sets the high-water limit of the buffer for outgoing bytes. The low-water limit is
a quarter of the high-water limit.  The default value is 64 KiB, equal to asyncio’s default (based on the current
implementation ofFlowControlMixin).
As soon as the HTTP request and response in the opening handshake are processed:
-  the request path is available in thepathattribute;
-  the    request    and    response    HTTP    headers    are    available    in    therequest_headersand
response_headersattributes, which areHeadersinstances.
If a subprotocol was negotiated, it’s available in thesubprotocolattribute.
Once  the  connection  is  closed,  the  code  is  available  in  theclose_codeattribute  and  the  reason  in
close_reason.
All attributes must be treated as read-only.
local_address
Local address of the connection as a(host, port)tuple.
When the connection isn’t open,local_addressisNone.
Return typeAny
remote_address
Remote address of the connection as a(host, port)tuple.
When the connection isn’t open,remote_addressisNone.
Return typeAny
open
Truewhen the connection is usable.
It may be used to detect disconnections. However, this approach is discouraged per the EAFP principle.
WhenopenisFalse, using the connection raises aConnectionClosedexception.
Return typebool
closed
Trueonce the connection is closed.
Be aware that bothopenandclosedareFalseduring the opening and closing sequences.
Return typebool
path
Path of the HTTP request.
Available once the connection is open.
30Chapter 3.  Reference

websockets Documentation, Release 9.0
request_headers
HTTP request headers as aHeadersinstance.
Available once the connection is open.
response_headers
HTTP response headers as aHeadersinstance.
Available once the connection is open.
subprotocol
Subprotocol, if one was negotiated.
Available once the connection is open.
close_code
WebSocket close code.
Available once the connection is closed.
close_reason
WebSocket close reason.
Available once the connection is closed.
await recv()
Receive the next message.
Return astrfor a text frame andbytesfor a binary frame.
When the end of the message stream is reached,recv()raisesConnectionClosed.  Specifically, it
raisesConnectionClosedOKafter a normal connection closure andConnectionClosedError
after a protocol error or a network failure.
Cancelingrecv()is safe.  There’s no risk of losing the next message.  The next invocation ofrecv()
will return it. This makes it possible to enforce a timeout by wrappingrecv()inwait_for().
## Raises
•ConnectionClosed– when the connection is closed
•RuntimeError– if two coroutines callrecv()concurrently
Return typeUnion[str,bytes]
await send(message)
Send a message.
A  string  (str)  is  sent  as  a  Text  frame.   A  bytestring  or  bytes-like  object  (bytes,bytearray,  or
memoryview) is sent as a Binary frame.
send()also accepts an iterable or an asynchronous iterable of strings, bytestrings, or bytes-like objects.
In that case the message is fragmented.  Each item is treated as a message fragment and sent in its own
frame. All items must be of the same type, or elsesend()will raise aTypeErrorand the connection
will be closed.
send()rejects dict-like objects because this is often an error. If you wish to send the keys of a dict-like
object as fragments, call itskeys()method and pass the result tosend().
Cancelingsend()is discouraged.  Instead, you should close the connection withclose().  Indeed,
there are only two situations wheresend()may yield control to the event loop:
-  The write buffer is full. If you don’t want to wait until enough data is sent, your only alternative is to
close the connection.close()will likely time out then abort the TCP connection.
## 3.1.  API31

websockets Documentation, Release 9.0
2.messageis an asynchronous iterator that yields control.  Stopping in the middle of a fragmented
message will cause a protocol error. Closing the connection has the same effect.
RaisesTypeError– for unsupported inputs
Return typeNone
await ping(data=None)
Send a ping.
Return aFuturethat will be completed when the corresponding pong is received.  You can ignore it if
you don’t intend to wait.
A ping may serve as a keepalive or as a check that the remote endpoint received all messages up to this
point:
pong_waiter =awaitws.ping()
awaitpong_waiter# only if you want to wait for the pong
By default, the ping contains four random bytes. This payload may be overridden with the optionaldata
argument which must be a string (which will be encoded to UTF-8) or a bytes-like object.
Cancelingping()is discouraged.  Ifping()doesn’t return immediately, it means the write buffer is
full. If you don’t want to wait, you should close the connection.
Canceling theFuturereturned byping()has no effect.
Return typeAwaitable[None]
await pong(data=b'')
Send a pong.
An unsolicited pong may serve as a unidirectional heartbeat.
The payload may be set with the optionaldataargument which must be a string (which will be encoded
to UTF-8) or a bytes-like object.
Cancelingpong()is discouraged for the same reason asping().
Return typeNone
await close(code=1000,reason='')
Perform the closing handshake.
close()waits for the other end to complete the handshake and for the TCP connection to terminate. As
a consequence, there’s no need to awaitwait_closed();close()already does it.
close()is idempotent: it doesn’t do anything once the connection is closed.
Wrappingclose()increate_task()is safe, given that errors during connection termination aren’t
particularly useful.
Cancelingclose()is discouraged. If it takes too long, you can set a shorterclose_timeout. If you
don’t want to wait, let the Python process exit, then the OS will close the TCP connection.
## Parameters
•code(int) – WebSocket close code
•reason(str) – WebSocket close reason
Return typeNone
32Chapter 3.  Reference

websockets Documentation, Release 9.0
await wait_closed()
Wait until the connection is closed.
This is identical toclosed, except it can be awaited.
This can make it easier to handle connection termination, regardless of its cause, in tasks that interact with
the WebSocket connection.
Return typeNone
## 3.1.2  Server
websockets.legacy.serverdefines the WebSocket server APIs.
Starting a server
awaitwebsockets.legacy.server.serve(ws_handler,host=None,port=None,*,
create_protocol=None,ping_interval=20,
ping_timeout=20,close_timeout=None,
max_size=1048576,max_queue=32,
read_limit=65536,write_limit=65536,loop=None,
compression='deflate',origins=None,ex-
tensions=None,subprotocols=None,ex-
tra_headers=None,process_request=None,se-
lect_subprotocol=None,**kwargs)
Create, start, and return a WebSocket server onhostandport.
Whenever  a  client  connects,  the  server  accepts  the  connection,  creates  aWebSocketServerProtocol,
performs the opening handshake, and delegates to the connection handler defined byws_handler. Once the
handler completes, either normally or with an exception, the server performs the closing handshake and closes
the connection.
Awaitingserve()yields aWebSocketServer. This instance providesclose()andwait_closed()
methods for terminating the server and cleaning up its resources.
When a server is closed withclose(), it closes all connections with close code 1001 (going away).  Con-
nections handlers, which are running thews_handlercoroutine, will receive aConnectionClosedOK
exception on their current or next interaction with the WebSocket connection.
serve()can also be used as an asynchronous context manager:
stop = asyncio.Future()# set this future to exit the server
async withserve(...):
awaitstop
In this case, the server is shut down when exiting the context.
serve()is   a   wrapper   around   the   event   loop’screate_server()method.It   creates   and
starts  aasyncio.Serverwithcreate_server().Then  it  wraps  theasyncio.Serverin  a
WebSocketServerand returns theWebSocketServer.
ws_handleris the WebSocket handler.   It must be a coroutine accepting two arguments:  the WebSocket
connection, which is an instance ofWebSocketServerProtocol, and the path of the request.
Thehostandportarguments,    as   well   as   unrecognized   keyword   arguments,    are   passed   to
create_server().
For example, you can set thesslkeyword argument to aSSLContextto enable TLS.
## 3.1.  API33

websockets Documentation, Release 9.0
create_protocoldefaults  toWebSocketServerProtocol.   It  may  be  replaced  by  a  wrapper  or  a
subclass to customize the protocol that manages the connection.
The  behavior  ofping_interval,ping_timeout,close_timeout,max_size,max_queue,
read_limit, andwrite_limitis described inWebSocketServerProtocol.
serve()also accepts the following optional arguments:
•compressionis a shortcut to configure compression extensions; by default it enables the “permessage-
deflate” extension; set it toNoneto disable compression.
•originsdefines acceptable Origin HTTP headers; includeNonein the list if the lack of an origin is
acceptable.
•extensionsis a list of supported extensions in order of decreasing preference.
•subprotocolsis a list of supported subprotocols in order of decreasing preference.
•extra_headerssets  additional  HTTP  response  headers  when  the  handshake  succeeds;  it  can  be  a
Headersinstance, aMapping, an iterable of(name, value)pairs, or a callable taking the request
path and headers in arguments and returning one of the above.
•process_requestallows intercepting the HTTP request; it must be a coroutine taking the request path
and headers in argument; seeprocess_request()for details.
•select_subprotocolallows  customizing  the  logic  for  selecting  a  subprotocol;   it  must  be  a
callable  taking  the  subprotocols  offered  by  the  client  and  available  on  the  server  in  argument;  see
select_subprotocol()for details.
Since there’s no useful way to propagate exceptions triggered in handlers, they’re sent to the"websockets.
server"logger instead. Debugging is much easier if you configure logging to print them:
import logging
logger = logging.getLogger("websockets.server")
logger.setLevel(logging.ERROR)
logger.addHandler(logging.StreamHandler())
awaitwebsockets.legacy.server.unix_serve(ws_handler,path=None,**kwargs)
Similar toserve(), but for listening on Unix sockets.
This function calls the event loop’screate_unix_server()method.
It is only available on Unix.
It’s useful for deploying a server behind a reverse proxy such as nginx.
Parameterspath(Optional[str]) – file system path to the Unix socket
Return typeServe
Stopping a server
classwebsockets.legacy.server.WebSocketServer(loop)
WebSocket server returned byserve().
This class provides the same interface asAbstractServer, namely theclose()andwait_closed()
methods.
It keeps track of WebSocket connections in order to close them properly when shutting down.
Instances of this class store a reference to theServerobject returned bycreate_server()rather than
inherit fromServerin part becausecreate_server()doesn’t support passing a customServerclass.
34Chapter 3.  Reference

websockets Documentation, Release 9.0
sockets
List ofsocketobjects the server is listening to.
Noneif the server is closed.
Return typeOptional[List[socket]]
close()
Close the server.
This method:
-  closes the underlyingServer;
-  rejects new WebSocket connections with an HTTP 503 (service unavailable) error; this happens when
the server accepted the TCP connection but didn’t complete the WebSocket opening handshake prior
to closing;
-  closes open WebSocket connections with close code 1001 (going away).
close()is idempotent.
Return typeNone
await wait_closed()
Wait until the server is closed.
Whenwait_closed()returns, all TCP connections are closed and all connection handlers have re-
turned.
Return typeNone
Using a connection
classwebsockets.legacy.server.WebSocketServerProtocol(ws_handler,ws_server,
*,origins=None,ex-
tensions=None,sub-
protocols=None,ex-
tra_headers=None,pro-
cess_request=None,se-
lect_subprotocol=None,
## **kwargs)
Protocolsubclass implementing a WebSocket server.
WebSocketServerProtocol:
-  performs the opening handshake to establish the connection;
-  providesrecv()andsend()coroutines for receiving and sending messages;
-  deals with control frames automatically;
-  performs the closing handshake to terminate the connection.
You may customize the opening handshake by subclassingWebSocketServerand overriding:
•process_request()to intercept the client request before any processing and, if appropriate, to abort
the WebSocket request and return a HTTP response instead;
•select_subprotocol()to select a subprotocol, if the client and the server have multiple subproto-
cols in common and the default logic for choosing one isn’t suitable (this is rarely needed).
WebSocketServerProtocolsupports asynchronous iteration:
## 3.1.  API35

websockets Documentation, Release 9.0
async formessageinwebsocket:
awaitprocess(message)
The iterator yields incoming messages. It exits normally when the connection is closed with the close code 1000
(OK) or 1001 (going away). It raises aConnectionClosedErrorexception when the connection is closed
with any other code.
Once the connection is open, a Ping frame is sent everyping_intervalseconds. This serves as a keepalive.
It  helps  keeping  the  connection  open,  especially  in  the  presence  of  proxies  with  short  timeouts  on  inactive
connections. Setping_intervaltoNoneto disable this behavior.
If  the  corresponding  Pong  frame  isn’t  received  withinping_timeoutseconds,  the  connection  is  consid-
ered unusable and is closed with code 1011.  This ensures that the remote endpoint remains responsive.  Set
ping_timeouttoNoneto disable this behavior.
Theclose_timeoutparameter defines  a maximum  wait time  for completing the  closing handshake  and
terminating the TCP connection. For legacy reasons,close()completes in at most4
## *
close_timeout
seconds.
close_timeoutneeds to be a parameter of the protocol because websockets usually callsclose()implic-
itly when the connection handler terminates.
To apply a timeout to any other API, wrap it inwait_for().
Themax_sizeparameter enforces the maximum size for incoming messages in bytes.  The default value is
1 MiB.Nonedisables the limit.  If a message larger than the maximum size is received,recv()will raise
ConnectionClosedErrorand the connection will be closed with code 1009.
Themax_queueparameter sets the maximum length of the queue that holds incoming messages. The default
value is32.Nonedisables the limit.  Messages are added to an in-memory queue when they’re received; then
recv()pops from that queue. In order to prevent excessive memory consumption when messages are received
faster than they can be processed, the queue must be bounded. If the queue fills up, the protocol stops processing
incoming data untilrecv()is called. In this situation, various receive buffers (at least inasyncioand in the
OS) will fill up, then the TCP receive window will shrink, slowing down transmission to avoid packet loss.
Since Python can use up to 4 bytes of memory to represent a single character, each connection may use up to
## 4
## *
max_size
## *
max_queuebytes of memory to store incoming messages. By default, this is 128 MiB.
You may want to lower the limits, depending on your application’s requirements.
Theread_limitargument sets the high-water limit of the buffer for incoming bytes. The low-water limit is
half the high-water limit. The default value is 64 KiB, half of asyncio’s default (based on the current implemen-
tation ofStreamReader).
Thewrite_limitargument sets the high-water limit of the buffer for outgoing bytes. The low-water limit is
a quarter of the high-water limit.  The default value is 64 KiB, equal to asyncio’s default (based on the current
implementation ofFlowControlMixin).
As soon as the HTTP request and response in the opening handshake are processed:
-  the request path is available in thepathattribute;
-  the    request    and    response    HTTP    headers    are    available    in    therequest_headersand
response_headersattributes, which areHeadersinstances.
If a subprotocol was negotiated, it’s available in thesubprotocolattribute.
Once  the  connection  is  closed,  the  code  is  available  in  theclose_codeattribute  and  the  reason  in
close_reason.
All attributes must be treated as read-only.
36Chapter 3.  Reference

websockets Documentation, Release 9.0
local_address
Local address of the connection as a(host, port)tuple.
When the connection isn’t open,local_addressisNone.
Return typeAny
remote_address
Remote address of the connection as a(host, port)tuple.
When the connection isn’t open,remote_addressisNone.
Return typeAny
open
Truewhen the connection is usable.
It may be used to detect disconnections. However, this approach is discouraged per the EAFP principle.
WhenopenisFalse, using the connection raises aConnectionClosedexception.
Return typebool
closed
Trueonce the connection is closed.
Be aware that bothopenandclosedareFalseduring the opening and closing sequences.
Return typebool
path
Path of the HTTP request.
Available once the connection is open.
request_headers
HTTP request headers as aHeadersinstance.
Available once the connection is open.
response_headers
HTTP response headers as aHeadersinstance.
Available once the connection is open.
subprotocol
Subprotocol, if one was negotiated.
Available once the connection is open.
close_code
WebSocket close code.
Available once the connection is closed.
close_reason
WebSocket close reason.
Available once the connection is closed.
await process_request(path,request_headers)
Intercept the HTTP request and return an HTTP response if appropriate.
Ifprocess_requestreturnsNone, the WebSocket handshake continues. If it returns 3-uple contain-
ing a status code, response headers and a response body, that HTTP response is sent and the connection is
closed. In that case:
## 3.1.  API37

websockets Documentation, Release 9.0
-  The HTTP status must be aHTTPStatus.
-  HTTP headers must be aHeadersinstance, aMapping, or an iterable of(name, value)pairs.
-  The HTTP response body must bebytes. It may be empty.
This coroutine may be overridden in aWebSocketServerProtocolsubclass, for example:
-  to return a HTTP 200 OK response on a given path; then a load balancer can use this path for a health
check;
-  to authenticate the request and return a HTTP 401 Unauthorized or a HTTP 403 Forbidden when
authentication fails.
Instead of subclassing, it is possible to override this method by passing aprocess_requestargument
to theserve()function or theWebSocketServerProtocolconstructor. This is equivalent, except
process_requestwon’t have access to the protocol instance, so it can’t store information for later
use.
process_requestis expected to complete quickly. If it may run for a long time, then it should await
wait_closed()and  exit  ifwait_closed()completes,  or  else  it  could  prevent  the  server  from
shutting down.
## Parameters
•path(str) – request path, including optional query string
•request_headers(Headers) – request headers
Return typeOptional[Tuple[HTTPStatus,Union[Headers,Mapping[str,str],
Iterable[Tuple[str,str]]],bytes]]
select_subprotocol(client_subprotocols,server_subprotocols)
Pick a subprotocol among those offered by the client.
If several subprotocols are supported by the client and the server, the default implementation selects the
preferred subprotocols by giving equal value to the priorities of the client and the server.
If no subprotocol is supported by the client and the server, it proceeds without a subprotocol.
This is unlikely to be the most useful implementation in practice, as many servers providing a subprotocol
will require that the client uses that subprotocol. Such rules can be implemented in a subclass.
Instead of subclassing, it is possible to override this method by passing aselect_subprotocolargu-
ment to theserve()function or theWebSocketServerProtocolconstructor.
## Parameters
•client_subprotocols(Sequence[NewType()(Subprotocol,str)]) – list of
subprotocols offered by the client
•server_subprotocols(Sequence[NewType()(Subprotocol,str)]) – list of
subprotocols available on the server
Return typeOptional[NewType()(Subprotocol,str)]
await recv()
Receive the next message.
Return astrfor a text frame andbytesfor a binary frame.
When the end of the message stream is reached,recv()raisesConnectionClosed.  Specifically, it
raisesConnectionClosedOKafter a normal connection closure andConnectionClosedError
after a protocol error or a network failure.
38Chapter 3.  Reference

websockets Documentation, Release 9.0
Cancelingrecv()is safe.  There’s no risk of losing the next message.  The next invocation ofrecv()
will return it. This makes it possible to enforce a timeout by wrappingrecv()inwait_for().
## Raises
•ConnectionClosed– when the connection is closed
•RuntimeError– if two coroutines callrecv()concurrently
Return typeUnion[str,bytes]
await send(message)
Send a message.
A  string  (str)  is  sent  as  a  Text  frame.   A  bytestring  or  bytes-like  object  (bytes,bytearray,  or
memoryview) is sent as a Binary frame.
send()also accepts an iterable or an asynchronous iterable of strings, bytestrings, or bytes-like objects.
In that case the message is fragmented.  Each item is treated as a message fragment and sent in its own
frame. All items must be of the same type, or elsesend()will raise aTypeErrorand the connection
will be closed.
send()rejects dict-like objects because this is often an error. If you wish to send the keys of a dict-like
object as fragments, call itskeys()method and pass the result tosend().
Cancelingsend()is discouraged.  Instead, you should close the connection withclose().  Indeed,
there are only two situations wheresend()may yield control to the event loop:
-  The write buffer is full. If you don’t want to wait until enough data is sent, your only alternative is to
close the connection.close()will likely time out then abort the TCP connection.
2.messageis an asynchronous iterator that yields control.  Stopping in the middle of a fragmented
message will cause a protocol error. Closing the connection has the same effect.
RaisesTypeError– for unsupported inputs
Return typeNone
await ping(data=None)
Send a ping.
Return aFuturethat will be completed when the corresponding pong is received.  You can ignore it if
you don’t intend to wait.
A ping may serve as a keepalive or as a check that the remote endpoint received all messages up to this
point:
pong_waiter =awaitws.ping()
awaitpong_waiter# only if you want to wait for the pong
By default, the ping contains four random bytes. This payload may be overridden with the optionaldata
argument which must be a string (which will be encoded to UTF-8) or a bytes-like object.
Cancelingping()is discouraged.  Ifping()doesn’t return immediately, it means the write buffer is
full. If you don’t want to wait, you should close the connection.
Canceling theFuturereturned byping()has no effect.
Return typeAwaitable[None]
await pong(data=b'')
Send a pong.
An unsolicited pong may serve as a unidirectional heartbeat.
## 3.1.  API39

websockets Documentation, Release 9.0
The payload may be set with the optionaldataargument which must be a string (which will be encoded
to UTF-8) or a bytes-like object.
Cancelingpong()is discouraged for the same reason asping().
Return typeNone
await close(code=1000,reason='')
Perform the closing handshake.
close()waits for the other end to complete the handshake and for the TCP connection to terminate. As
a consequence, there’s no need to awaitwait_closed();close()already does it.
close()is idempotent: it doesn’t do anything once the connection is closed.
Wrappingclose()increate_task()is safe, given that errors during connection termination aren’t
particularly useful.
Cancelingclose()is discouraged. If it takes too long, you can set a shorterclose_timeout. If you
don’t want to wait, let the Python process exit, then the OS will close the TCP connection.
## Parameters
•code(int) – WebSocket close code
•reason(str) – WebSocket close reason
Return typeNone
await wait_closed()
Wait until the connection is closed.
This is identical toclosed, except it can be awaited.
This can make it easier to handle connection termination, regardless of its cause, in tasks that interact with
the WebSocket connection.
Return typeNone
Basic authentication
websockets.legacy.authprovides HTTP Basic Authentication according toRFC 7235andRFC 7617.
websockets.legacy.auth.basic_auth_protocol_factory(realm,credentials=None,
check_credentials=None,cre-
ate_protocol=None)
Protocol factory that enforces HTTP Basic Auth.
basic_auth_protocol_factoryis designed to integrate withserve()like this:
websockets.serve(
## ...,
create_protocol=websockets.basic_auth_protocol_factory(
realm="my dev server",
credentials=("hello", "iloveyou"),
## )
## )
realmindicates the scope of protection.   It should contain only ASCII characters because the encoding of
non-ASCII characters is undefined. Refer to section 2.2 ofRFC 7235for details.
credentialsdefines hard coded authorized credentials.  It can be a(username, password)pair or a
list of such pairs.
40Chapter 3.  Reference

websockets Documentation, Release 9.0
check_credentialsdefines a coroutine that checks whether credentials are authorized.   This coroutine
receivesusernameandpasswordarguments and returns abool.
One ofcredentialsorcheck_credentialsmust be provided but not both.
## Bydefault,basic_auth_protocol_factorycreatesafactoryforbuilding
BasicAuthWebSocketServerProtocolinstances.Youcanoverridethiswiththe
create_protocolparameter.
## Parameters
•realm(str) – scope of protection
•credentials(Union[Tuple[str,str],Iterable[Tuple[str,str]],None]) –
hard coded credentials
•check_credentials(Optional[Callable[[str,str],Awaitable[bool]]]) –
coroutine that verifies credentials
RaisesTypeError– if the credentials argument has the wrong type
Return typeCallable[[Any],BasicAuthWebSocketServerProtocol]
classwebsockets.legacy.auth.BasicAuthWebSocketServerProtocol(*args,realm,
check_credentials,
## **kwargs)
WebSocket server protocol that enforces HTTP Basic Auth.
await process_request(path,request_headers)
Check HTTP Basic Auth and return a HTTP 401 or 403 response if needed.
Return typeOptional[Tuple[HTTPStatus,Union[Headers,Mapping[str,str],
Iterable[Tuple[str,str]]],bytes]]
username
Username of the authenticated user.
## 3.1.3  Extensions
Per-Message Deflate
websockets.extensions.permessage_deflateimplements the Compression Extensions for WebSocket
as specified inRFC 7692.
classwebsockets.extensions.permessage_deflate.ClientPerMessageDeflateFactory(server_no_context_takeover=False,
client_no_context_takeover=False,
server_max_window_bits=None,
client_max_window_bits=None,
com-
press_settings=None)
Client-side extension factory for the Per-Message Deflate extension.
Parameters behave as described in section 7.1 of RFC 7692. Set them toTrueto include them in the negotiation
offer without a value or to an integer value to include them with this value.
## Parameters
•server_no_context_takeover(bool) – defaults toFalse
•client_no_context_takeover(bool) – defaults toFalse
•server_max_window_bits(Optional[int]) – optional, defaults toNone
## 3.1.  API41

websockets Documentation, Release 9.0
•client_max_window_bits(Union[int,bool,None])  –  optional,  defaults  to
## None
•compress_settings(Optional[Dict[str,Any]]) – optional, keyword arguments
forzlib.compressobj(), excludingwbits
classwebsockets.extensions.permessage_deflate.ServerPerMessageDeflateFactory(server_no_context_takeover=False,
client_no_context_takeover=False,
server_max_window_bits=None,
client_max_window_bits=None,
com-
press_settings=None)
Server-side extension factory for the Per-Message Deflate extension.
Parameters behave as described in section 7.1 of RFC 7692. Set them toTrueto include them in the negotiation
offer without a value or to an integer value to include them with this value.
## Parameters
•server_no_context_takeover(bool) – defaults toFalse
•client_no_context_takeover(bool) – defaults toFalse
•server_max_window_bits(Optional[int]) – optional, defaults toNone
•client_max_window_bits(Optional[int]) – optional, defaults toNone
•compress_settings(Optional[Dict[str,Any]]) – optional, keyword arguments
forzlib.compressobj(), excludingwbits
Abstract classes
websockets.extensions.basedefines abstract classes for implementing extensions.
See section 9 of RFC 6455.
classwebsockets.extensions.base.Extension
Abstract class for extensions.
decode(frame,*,max_size=None)
Decode an incoming frame.
## Parameters
•frame(Frame) – incoming frame
•max_size(Optional[int]) – maximum payload size in bytes
Return typeFrame
encode(frame)
Encode an outgoing frame.
Parametersframe(Frame) – outgoing frame
Return typeFrame
name
Extension identifier.
Return typeNewType()(ExtensionName,str)
classwebsockets.extensions.base.ClientExtensionFactory
Abstract class for client-side extension factories.
42Chapter 3.  Reference

websockets Documentation, Release 9.0
get_request_params()
Build request parameters.
Return a list of(name, value)pairs.
Return typeList[Tuple[str,Optional[str]]]
name
Extension identifier.
Return typeNewType()(ExtensionName,str)
process_response_params(params,accepted_extensions)
Process response parameters received from the server.
## Parameters
•params(Sequence[Tuple[str,Optional[str]]])  –  list  of(name, value)
pairs.
•accepted_extensions(Sequence[Extension]) – list of previously accepted ex-
tensions.
RaisesNegotiationError– if parameters aren’t acceptable
Return typeExtension
classwebsockets.extensions.base.ServerExtensionFactory
Abstract class for server-side extension factories.
name
Extension identifier.
Return typeNewType()(ExtensionName,str)
process_request_params(params,accepted_extensions)
Process request parameters received from the client.
To accept the offer, return a 2-uple containing:
-  response parameters: a list of(name, value)pairs
-  an extension: an instance of a subclass ofExtension
## Parameters
•params(Sequence[Tuple[str,Optional[str]]])  –  list  of(name, value)
pairs.
•accepted_extensions(Sequence[Extension]) – list of previously accepted ex-
tensions.
RaisesNegotiationError– to reject the offer, if parameters aren’t acceptable
Return typeTuple[List[Tuple[str,Optional[str]]],Extension]
## 3.1.  API43

websockets Documentation, Release 9.0
## 3.1.4  Utilities
Data structures
websockets.datastructuresdefines a class for manipulating HTTP headers.
classwebsockets.datastructures.Headers(*args,**kwargs)
Efficient data structure for manipulating HTTP headers.
Alistof(name, values)is inefficient for lookups.
Adictdoesn’t suffice because header names are case-insensitive and multiple occurrences of headers with the
same name are possible.
Headersstores HTTP headers in a hybrid data structure to provide efficient insertions and lookups while
preserving the original data.
In order to account for multiple values with minimal hassle,Headersfollows this logic:
•When getting a header withheaders[name]:
–if there’s no value,KeyErroris raised;
–if there’s exactly one value, it’s returned;
–if there’s more than one value,MultipleValuesErroris raised.
-  When setting a header withheaders[name] = value, the value is appended to the list of values for
that header.
-  When  deleting  a  header  withdel headers[name],  all  values  for  that  header  are  removed  (this  is
slow).
Other methods for manipulating headers are consistent with this logic.
As long as no header occurs multiple times,Headersbehaves likedict,  except keys are lower-cased to
provide case-insensitivity.
Two methods support manipulating multiple values explicitly:
•get_all()returns a list of all values for a header;
•raw_items()returns an iterator of(name, values)pairs.
clear()
Remove all headers.
Return typeNone
get_all(key)
Return the (possibly empty) list of all values for a header.
Parameterskey(str) – header name
Return typeList[str]
raw_items()
Return an iterator of all values as(name, value)pairs.
Return typeIterator[Tuple[str,str]]
exceptionwebsockets.datastructures.MultipleValuesError
Exception raised whenHeadershas more than one value for a key.
44Chapter 3.  Reference

websockets Documentation, Release 9.0
## Exceptions
websockets.exceptionsdefines the following exception hierarchy:
•WebSocketException
–ConnectionClosed
## *
ConnectionClosedError
## *
ConnectionClosedOK
–InvalidHandshake
## *
SecurityError
## *
InvalidMessage
## *
InvalidHeader
·InvalidHeaderFormat
·InvalidHeaderValue
·InvalidOrigin
·InvalidUpgrade
## *
InvalidStatusCode
## *
NegotiationError
·DuplicateParameter
·InvalidParameterName
·InvalidParameterValue
## *
AbortHandshake
## *
RedirectHandshake
–InvalidState
–InvalidURI
–PayloadTooBig
–ProtocolError
exceptionwebsockets.exceptions.AbortHandshake(status,headers,body=b'')
Raised to abort the handshake on purpose and return a HTTP response.
This exception is an implementation detail.
The public API isprocess_request().
exceptionwebsockets.exceptions.ConnectionClosed(code,reason)
Raised when trying to interact with a closed connection.
Provides the connection close code and reason in itscodeandreasonattributes respectively.
exceptionwebsockets.exceptions.ConnectionClosedError(code,reason)
LikeConnectionClosed, when the connection terminated with an error.
This means the close code is different from 1000 (OK) and 1001 (going away).
## 3.1.  API45

websockets Documentation, Release 9.0
exceptionwebsockets.exceptions.ConnectionClosedOK(code,reason)
LikeConnectionClosed, when the connection terminated properly.
This means the close code is 1000 (OK) or 1001 (going away).
exceptionwebsockets.exceptions.DuplicateParameter(name)
Raised when a parameter name is repeated in an extension header.
exceptionwebsockets.exceptions.InvalidHandshake
Raised during the handshake when the WebSocket connection fails.
exceptionwebsockets.exceptions.InvalidHeader(name,value=None)
Raised when a HTTP header doesn’t have a valid format or value.
exceptionwebsockets.exceptions.InvalidHeaderFormat(name,error,header,pos)
Raised when a HTTP header cannot be parsed.
The format of the header doesn’t match the grammar for that header.
exceptionwebsockets.exceptions.InvalidHeaderValue(name,value=None)
Raised when a HTTP header has a wrong value.
The format of the header is correct but a value isn’t acceptable.
exceptionwebsockets.exceptions.InvalidMessage
Raised when a handshake request or response is malformed.
exceptionwebsockets.exceptions.InvalidOrigin(origin)
Raised when the Origin header in a request isn’t allowed.
exceptionwebsockets.exceptions.InvalidParameterName(name)
Raised when a parameter name in an extension header is invalid.
exceptionwebsockets.exceptions.InvalidParameterValue(name,value)
Raised when a parameter value in an extension header is invalid.
exceptionwebsockets.exceptions.InvalidState
Raised when an operation is forbidden in the current state.
This exception is an implementation detail.
It should never be raised in normal circumstances.
exceptionwebsockets.exceptions.InvalidStatusCode(status_code)
Raised when a handshake response status code is invalid.
The integer status code is available in thestatus_codeattribute.
exceptionwebsockets.exceptions.InvalidURI(uri)
Raised when connecting to an URI that isn’t a valid WebSocket URI.
exceptionwebsockets.exceptions.InvalidUpgrade(name,value=None)
Raised when the Upgrade or Connection header isn’t correct.
exceptionwebsockets.exceptions.NegotiationError
Raised when negotiating an extension fails.
exceptionwebsockets.exceptions.PayloadTooBig
Raised when receiving a frame with a payload exceeding the maximum size.
exceptionwebsockets.exceptions.ProtocolError
Raised when a frame breaks the protocol.
exceptionwebsockets.exceptions.RedirectHandshake(uri)
Raised when a handshake gets redirected.
46Chapter 3.  Reference

websockets Documentation, Release 9.0
This exception is an implementation detail.
exceptionwebsockets.exceptions.SecurityError
Raised when a handshake request or response breaks a security rule.
Security limits are hard coded.
exceptionwebsockets.exceptions.WebSocketException
Base class for all exceptions defined bywebsockets.
websockets.exceptions.WebSocketProtocolError
alias ofwebsockets.exceptions.ProtocolError
## Types
websockets.typing.Origin(x)
Value of a Origin header
websockets.typing.Subprotocol(x)
Subprotocol value in a Sec-WebSocket-Protocol header
All public APIs can be imported from thewebsocketspackage, unless noted otherwise.  Anything that isn’t listed
in this API documentation is a private API, with no guarantees of behavior or backwards-compatibility.
## 3.1.  API47

websockets Documentation, Release 9.0
48Chapter 3.  Reference

## CHAPTER
## FOUR
## DISCUSSIONS
Get a deeper understanding of howwebsocketsis built and why.
## 4.1  Design
This document describes the design ofwebsockets. It assumes familiarity with the specification of the WebSocket
protocol inRFC 6455.
It’s primarily intended at maintainers. It may also be useful for users who wish to understand what happens under the
hood.
Warning:Internals described in this document may change at any time.
Backwards compatibility is only guaranteed for public APIs.
## 4.1.1  Lifecycle
## State
WebSocket connections go through a trivial state machine:
•CONNECTING: initial state,
•OPEN: when the opening handshake is complete,
•CLOSING: when the closing handshake is started,
•CLOSED: when the TCP connection is closed.
Transitions happen in the following places:
•CONNECTING -> OPEN: inconnection_open()which runs when theopening handshakecompletes
and the WebSocket connection is established — not to be confused withconnection_made()which runs
when the TCP connection is established;
•OPEN -> CLOSING: inwrite_frame()immediately before sending a close frame; since receiving a close
frame triggers sending a close frame, this does the right thing regardless of which side started theclosing hand-
shake; also infail_connection()which duplicates a few lines of code fromwrite_close_frame()
andwrite_frame();
## •
## *
-> CLOSED: inconnection_lost()which is always called exactly once when the TCP connection is
closed.
## 49

websockets Documentation, Release 9.0
## Coroutines
The following diagram shows which coroutines are running at each stage of the connection lifecycle on the client side.
The lifecycle is identical on the server side, except inversion of control makes the equivalent ofconnect()implicit.
Coroutines shown in green are called by the application.  Multiple coroutines may interact with the WebSocket con-
nection concurrently.
Coroutines shown in gray manage the connection.  When the opening handshake succeeds,connection_open()
starts two tasks:
•transfer_data_taskrunstransfer_data()which  handles  incoming  data  and  letsrecv()con-
sume  it.It  may  be  canceled  to  terminate  the  connection.It  never  exits  with  an  exception  other  than
CancelledError. Seedata transferbelow.
•keepalive_ping_taskrunskeepalive_ping()which sends Ping frames at regular intervals and en-
sures that corresponding Pong frames are received. It is canceled when the connection terminates. It never exits
with an exception other thanCancelledError.
•close_connection_taskrunsclose_connection()which waits for the data transfer to terminate,
then takes care of closing the TCP connection.  It must not be canceled.  It never exits with an exception.  See
connection terminationbelow.
Besides,fail_connection()starts the sameclose_connection_taskwhen the opening handshake fails,
in order to close the TCP connection.
Splitting the responsibilities between two tasks makes it easier to guarantee thatwebsocketscan terminate connec-
tions:
-  within a fixed timeout,
-  without leaking pending tasks,
-  without leaking open TCP connections,
regardless of whether the connection terminates normally or abnormally.
transfer_data_taskcompletes when no more data will be received on the connection.  Under normal circum-
stances, it exits after exchanging close frames.
close_connection_taskcompletes when the TCP connection is closed.
4.1.2  Opening handshake
websocketsperforms  the  opening  handshake  when  establishing  a  WebSocket  connection.   On  the  client  side,
connect()executes it before returning the protocol to the caller.  On the server side,  it’s executed before pass-
ing the protocol to thews_handlercoroutine handling the connection.
While the opening handshake is asymmetrical — the client sends an HTTP Upgrade request and the server replies with
an HTTP Switching Protocols response —websocketsaims at keeping the implementation of both sides consistent
with one another.
On the client side,handshake():
-  builds a HTTP request based on theuriand parameters passed toconnect();
-  writes the HTTP request to the network;
-  reads a HTTP response from the network;
50Chapter 4.  Discussions

websockets Documentation, Release 9.0
-  checks the HTTP response, validatesextensionsandsubprotocol, and configures the protocol accord-
ingly;
-  moves to theOPENstate.
On the server side,handshake():
-  reads a HTTP request from the network;
-  callsprocess_request()which may abort the WebSocket handshake and return a HTTP response instead;
this hook only makes sense on the server side;
-  checks the HTTP request, negotiatesextensionsandsubprotocol, and configures the protocol accord-
ingly;
-  builds a HTTP response based on the above and parameters passed toserve();
-  writes the HTTP response to the network;
-  moves to theOPENstate;
-  returns thepathpart of theuri.
The most significant asymmetry between the two sides of the opening handshake lies in the negotiation of exten-
sions and, to a lesser extent, of the subprotocol.  The server knows everything about both sides and decides what the
parameters should be for the connection. The client merely applies them.
If anything goes wrong during the opening handshake,websocketsfails the connection.
4.1.3  Data transfer
## Symmetry
Once the opening handshake has completed, the WebSocket protocol enters the data transfer phase. This part is almost
symmetrical. There are only two differences between a server and a client:
-  client-to-server masking: the client masks outgoing frames; the server unmasks incoming frames;
-  closing the TCP connection: the server closes the connection immediately; the client waits for the server to do
it.
These differences are so minor that all the logic for data framing, for sending and receiving data and for closing the
connection is implemented in the same class,WebSocketCommonProtocol.
Theis_clientattribute  tells  which  side  a  protocol  instance  is  managing.    This  attribute  is  defined  on  the
WebSocketServerProtocolandWebSocketClientProtocolclasses.
Data flow
The following diagram shows how data flows between an application built on top ofwebsocketsand a remote
endpoint. It applies regardless of which side is the server or the client.
Public methods are shown in green, private methods in yellow, and buffers in orange.  Methods related to connection
termination are omitted; connection termination is discussed in another section below.
## 4.1.  Design51

websockets Documentation, Release 9.0
Receiving data
The left side of the diagram shows howwebsocketsreceives data.
Incoming data is written to aStreamReaderin order to implement flow control and provide backpressure on the
TCP connection.
transfer_data_task, which is started when the WebSocket connection is established, processes this data.
When it receives data frames, it reassembles fragments and puts the resulting messages in themessagesqueue.
When it encounters a control frame:
-  if it’s a close frame, it starts the closing handshake;
-  if it’s a ping frame, it answers with a pong frame;
-  if it’s a pong frame, it acknowledges the corresponding ping (unless it’s an unsolicited pong).
Running  this  process  in  a  task  guarantees  that  control  frames  are  processed  promptly.Without  such  a  task,
websocketswould depend on the application to drive the connection by having exactly one coroutine awaiting
recv()at any time. While this happens naturally in many use cases, it cannot be relied upon.
Thenrecv()fetches the next message from themessagesqueue, with some complexity added for handling back-
pressure and termination correctly.
Sending data
The right side of the diagram shows howwebsocketssends data.
send()writes one or several data frames containing the message. While sending a fragmented message, concurrent
calls tosend()are put on hold until all fragments are sent. This makes concurrent calls safe.
ping()writes a ping frame and yields aFuturewhich will be completed when a matching pong frame is received.
pong()writes a pong frame.
close()writes a close frame and waits for the TCP connection to terminate.
Outgoing data is written to aStreamWriterin order to implement flow control and provide backpressure from the
TCP connection.
Closing handshake
When the other side of the connection initiates the closing handshake,read_message()receives a close frame
while  in  theOPENstate.It  moves  to  theCLOSINGstate,  sends  a  close  frame,  and  returnsNone,  causing
transfer_data_taskto terminate.
When this side of the connection initiates the closing handshake withclose(), it moves to theCLOSINGstate and
sends a close frame. When the other side sends a close frame,read_message()receives it in theCLOSINGstate
and returnsNone, also causingtransfer_data_taskto terminate.
If the other side doesn’t send a close frame within the connection’s close timeout,websocketsfails the connection.
The closing handshake can take up to2
## *
close_timeout:  oneclose_timeoutto write a close frame and
oneclose_timeoutto receive a close frame.
Thenwebsocketsterminates the TCP connection.
52Chapter 4.  Discussions

websockets Documentation, Release 9.0
4.1.4  Connection termination
close_connection_task,  which is started when the WebSocket connection is established,  is responsible for
eventually closing the TCP connection.
Firstclose_connection_taskwaits fortransfer_data_taskto terminate, which may happen as a result
of:
-  a successful closing handshake: as explained above, this exits the infinite loop intransfer_data_task;
-  a timeout while waiting for the closing handshake to complete: this cancelstransfer_data_task;
-  a protocol error, including connection errors:  depending on the exception,transfer_data_taskfails the
connectionwith a suitable code and exits.
close_connection_taskis   separate   fromtransfer_data_taskto   make   it   easier   to   implement
the   timeout   on   the   closing   handshake.Cancelingtransfer_data_taskcreates   no   risk   of   canceling
close_connection_taskand failing to close the TCP connection, thus leaking resources.
Thenclose_connection_taskcancelskeepalive_ping. This task has no protocol compliance responsibil-
ities. Terminating it to avoid leaking it is the only concern.
Terminating   the   TCP   connection   can   take   up   to2
## *
close_timeouton   the   server   side   and3
## *
close_timeouton the client side.  Clients start by waiting for the server to close the connection, hence the extra
close_timeout.  Then both sides go through the following steps until the TCP connection is lost:  half-closing
the connection (only for non-TLS connections), closing the connection, aborting the connection.  At this point the
connection drops regardless of what happens on the network.
4.1.5  Connection failure
If the opening handshake doesn’t complete successfully,websocketsfails the connection by closing the TCP con-
nection.
## Oncetheopeninghandshakehascompleted,websocketsfailstheconnectionbycanceling
transfer_data_taskand sending a close frame if appropriate.
transfer_data_taskexits, unblockingclose_connection_task, which closes the TCP connection.
4.1.6  Server shutdown
WebSocketServercloses asynchronously likeasyncio.Server. The shutdown happen in two steps:
-  Stop listening and accepting new connections;
-  Close established connections with close code 1001 (going away) or, if the opening handshake is still in progress,
with HTTP status code 503 (Service Unavailable).
The first call toclosestarts a task that performs this sequence.  Further calls are ignored.  This is the easiest way to
makecloseandwait_closedidempotent.
## 4.1.  Design53

websockets Documentation, Release 9.0
## 4.1.7  Cancellation
User code
websocketsprovides a WebSocket application server.  It manages connections and passes them to user-provided
connection handlers. This is aninversion of controlscenario: library code calls user code.
If a connection drops, the corresponding handler should terminate.  If the server shuts down, all connection handlers
must terminate. Canceling connection handlers would terminate them.
However, using cancellation for this purpose would require all connection handlers to handle it properly. For example,
if a connection handler starts some tasks, it should catchCancelledError, terminate or cancel these tasks, and
then re-raise the exception.
Cancellation is tricky inasyncioapplications, especially when it interacts with finalization logic.  In the example
above,  what  if  a  handler  gets  interrupted  withCancelledErrorwhile  it’s  finalizing  the  tasks  it  started,  after
detecting that the connection dropped?
websocketsconsiders that cancellation may only be triggered by the caller of a coroutine when it doesn’t care
about the results of that coroutine anymore.  (Source:  Guido van Rossum).  Since connection handlers run arbitrary
user code,websocketshas no way of deciding whether that code is still doing something worth caring about.
For  these  reasons,websocketsnever  cancels  connection  handlers.   Instead  it  expects  them  to  detect  when  the
connection is closed, execute finalization logic if needed, and exit.
Conversely, cancellation isn’t a concern for WebSocket clients because they don’t involve inversion of control.
## Library
Mostpublic APIsofwebsocketsare coroutines.  They may be canceled, for example if the user starts a task that
calls these coroutines and cancels the task later.websocketsmust handle this situation.
Cancellation during the opening handshake is handled like any other exception: the TCP connection is closed and the
exception is re-raised. This can only happen on the client side. On the server side, the opening handshake is managed
bywebsocketsand nothing results in a cancellation.
OncetheWebSocketconnectionisestablished,internaltaskstransfer_data_taskand
close_connection_taskmustn’t  get  accidentally  canceled  if  a  coroutine  that  awaits  them  is  canceled.
In other words, they must be shielded from cancellation.
recv()waits for the next message in the queue or fortransfer_data_taskto terminate, whichever comes
first.  It relies onwait()for waiting on two futures in parallel.  As a consequence, even though it’s waiting on a
Futuresignaling the next message and ontransfer_data_task, it doesn’t propagate cancellation to them.
ensure_open()is called bysend(),ping(), andpong().  When the connection state isCLOSING, it waits
fortransfer_data_taskbut shields it to prevent cancellation.
close()waits  for  the  data  transfer  task  to  terminate  withwait_for().If  it’s  canceled  or  if  the  time-
out  elapses,transfer_data_taskis  canceled,  which  is  correct  at  this  point.close()then  waits  for
close_connection_taskbut shields it to prevent cancellation.
close()andfail_connection()are the only places wheretransfer_data_taskmay be canceled.
close_connnection_taskstarts by waiting fortransfer_data_task.  It catchesCancelledErrorto
prevent a cancellation oftransfer_data_taskfrom propagating toclose_connnection_task.
54Chapter 4.  Discussions

websockets Documentation, Release 9.0
## 4.1.8  Backpressure
Note:This section discusses backpressure from the perspective of a server but the concept applies to clients symmet-
rically.
With a naive implementation, if a server receives inputs faster than it can process them, or if it generates outputs faster
than it can send them, data accumulates in buffers, eventually causing the server to run out of memory and crash.
The solution to this problem is backpressure. Any part of the server that receives inputs faster than it can process them
and send the outputs must propagate that information back to the previous part in the chain.
websocketsis designed to make it easy to get backpressure right.
For incoming data,websocketsbuilds uponStreamReaderwhich propagates backpressure to its own buffer
and to the TCP stream. Frames are parsed from the input stream and added to a bounded queue. If the queue fills up,
parsing halts until the application reads a frame.
For outgoing data,websocketsbuilds uponStreamWriterwhich implements flow control. If the output buffers
grow too large, it waits until they’re drained. That’s why all APIs that write frames are asynchronous.
Of course, it’s still possible for an application to create its own unbounded buffers and break the backpressure.  Be
careful with queues.
## 4.1.9  Buffers
Note:This section discusses buffers from the perspective of a server but it applies to clients as well.
An asynchronous systems works best when its buffers are almost always empty.
For example, if a client sends data too fast for a server, the queue of incoming messages will be constantly full.  The
server will always be 32 messages (by default) behind the client. This consumes memory and increases latency for no
good reason. The problem is called bufferbloat.
If buffers are almost always full and that problem cannot be solved by adding capacity — typically because the system
is bottlenecked by the output and constantly regulated by backpressure — reducing the size of buffers minimizes
negative consequences.
By defaultwebsocketshas rather high limits. You can decrease them according to your application’s characteristics.
Bufferbloat can happen at every level in the stack where there is a buffer.  For each connection, the receiving side
contains these buffers:
-  OS buffers: tuning them is an advanced optimization.
•StreamReaderbytes buffer: the default limit is 64 KiB. You can set another limit by passing aread_limit
keyword argument toconnect()orserve().
-  Incoming messagesdeque: its size depends both on the size and the number of messages it contains. By default
the maximum UTF-8 encoded size is 1 MiB and the maximum number is 32.  In the worst case, after UTF-8
decoding,  a single message could take up to 4 MiB of memory and the overall memory consumption could
reach 128 MiB. You should adjust these limits by setting themax_sizeandmax_queuekeyword arguments
ofconnect()orserve()according to your application’s requirements.
For each connection, the sending side contains these buffers:
•StreamWriterbytes  buffer:    the  default  size  is  64  KiB.  You  can  set  another  limit  by  passing  a
write_limitkeyword argument toconnect()orserve().
## 4.1.  Design55

websockets Documentation, Release 9.0
-  OS buffers: tuning them is an advanced optimization.
## 4.1.10  Concurrency
Awaiting any combination ofrecv(),send(),close() ping(), orpong()concurrently is safe, including
multiple calls to the same method, with one exception and one limitation.
•Only one coroutine can receive messages at a time.This constraint avoids non-deterministic behavior (and
simplifies the implementation). If a coroutine is awaitingrecv(), awaiting it again in another coroutine raises
RuntimeError.
•Sending a fragmented message forces serialization.Indeed, the WebSocket protocol doesn’t support multi-
plexing messages. If a coroutine is awaitingsend()to send a fragmented message, awaiting it again in another
coroutine waits until the first call completes. This will be transparent in many cases. It may be a concern if the
fragmented message is generated slowly by an asynchronous iterator.
Receiving frames is independent from sending frames. This isolatesrecv(), which receives frames, from the other
methods, which send frames.
While  the  connection  is  open,  each  frame  is  sent  with  a  single  write.   Combined  with  the  concurrency  model  of
asyncio, this enforces serialization.  The only other requirement is to prevent interleaving other data frames in the
middle of a fragmented message.
After the connection is closed, sending a frame raisesConnectionClosed, which is safe.
## 4.2  Limitations
The client doesn’t attempt to guarantee that there is no more than one connection to a given IP address in a CON-
NECTING state.
The client doesn’t support connecting through a proxy.
There is no way to fragment outgoing messages. A message is always sent in a single frame.
## 4.3  Security
## 4.3.1  Encryption
For production use, a server should require encrypted connections.
See this example ofencrypting connections with TLS.
4.3.2  Memory use
Warning:An attacker who can open an arbitrary number of connections will be able to perform a denial of service
by memory exhaustion.  If you’re concerned by denial of service attacks, you must reject suspicious connections
before they reachwebsockets, typically in a reverse proxy.
With the default settings, opening a connection uses 325 KiB of memory.
56Chapter 4.  Discussions

websockets Documentation, Release 9.0
Sending some highly compressed messages could use up to 128 MiB of memory with an amplification factor of 1000
between network traffic and memory use.
Configuring a server tooptimize memory usagewill improve security in addition to improving performance.
4.3.3  Other limits
websocketsimplements additional limits on the amount of data it accepts in order to minimize exposure to security
vulnerabilities.
In the opening handshake,websocketslimits the number of HTTP headers to 256 and the size of an individual
header to 4096 bytes.  These limits are 10 to 20 times larger than what’s expected in standard use cases.  They’re
hard-coded. If you need to change them, monkey-patch the constants inwebsockets.http.
## 4.3.  Security57

websockets Documentation, Release 9.0
58Chapter 4.  Discussions

## CHAPTER
## FIVE
## PROJECT
This is about websockets-the-project rather than websockets-the-software.
## 5.1  Changelog
5.1.1  Backwards-compatibility policy
websocketsis intended for production use. Therefore, stability is a goal.
websocketsalso aims at providing the best API for WebSocket in Python.
While we value stability, we value progress more.  When an improvement requires changing a public API, we make
the change and document it in this changelog.
When possible with reasonable effort, we preserve backwards-compatibility for five years after the release that intro-
duced the change.
When a release contains backwards-incompatible API changes, the major version is increased, else the minor version
is increased. Patch versions are only for fixing regressions shortly after a release.
Only documented APIs are public. Undocumented APIs are considered private. They may change at any time.
## 5.1.2  9.1
In development
## 5.1.3  9.0
## May 1, 2021
Note:  Version 9.0 moves or deprecates several APIs.
Aliases provide backwards compatibility for all previously public APIs.
•HeadersandMultipleValuesErrorwere  moved  fromwebsockets.httptowebsockets.
datastructures. If you’re using them, you should adjust the import path.
-  Theclient,server,protocol,  andauthmodules  were  moved  from  thewebsocketspackage  to
websockets.legacysub-package, as part of an upcoming refactoring. Despite the name, they’re still fully
supported.   The  refactoring  should  be  a  transparent  upgrade  for  most  uses  when  it’s  available.   The  legacy
implementation will be preserved according to thebackwards-compatibility policy.
## 59

websockets Documentation, Release 9.0
-  Theframing,handshake,headers,http, andurimodules in thewebsocketspackage are depre-
cated.  These modules provided low-level APIs for reuse by other WebSocket implementations, but that never
happened. Keeping these APIs public makes it more difficult to improve websockets for no actual benefit.
-  Added compatibility with Python 3.9.
-  Added support for IRIs in addition to URIs.
-  Added close codes 1012, 1013, and 1014.
-  Raised an error when passing adicttosend().
-  Fixed sending fragmented, compressed messages.
-  FixedHostheader sent when connecting to an IPv6 address.
-  Fixed creating a client or a server with an existing Unix socket.
-  Aligned maximum cookie size with popular web browsers.
-  Ensured  cancellation  always  propagates,   even  on  Python  versions  whereCancelledErrorinherits
## Exception.
-  Improved error reporting.
## 5.1.4  8.1
## November 1, 2019
-  Added compatibility with Python 3.8.
## 5.1.5  8.0.2
## July 31, 2019
-  Restored the ability to pass a socket with thesockparameter ofserve().
-  Removed an incorrect assertion when a connection drops.
## 5.1.6  8.0.1
## July 21, 2019
-  Restored the ability to importWebSocketProtocolErrorfromwebsockets.
## 5.1.7  8.0
## July 7, 2019
Warning:  Version 8.0 drops compatibility with Python 3.4 and 3.5.
Note:  Version 8.0 expectsprocess_requestto be a coroutine.
Previously, it could be a function or a coroutine.
60Chapter 5.  Project

websockets Documentation, Release 9.0
If you’re passing aprocess_requestargument toserve()orWebSocketServerProtocol, or if you’re
overridingprocess_request()in a subclass, define it withasync definstead ofdef.
For backwards compatibility, functions are still mostly supported, but mixing functions and coroutines won’t work in
some inheritance scenarios.
Note:  Version 8.0 changes the behavior of themax_queueparameter.
If   you   were   settingmax_queue=0to   make   the   queue   of   incoming   messages   unbounded,   change   it   to
max_queue=None.
Note:  Version 8.0 deprecates thehost,port, andsecureattributes ofWebSocketCommonProtocol.
Uselocal_addressin servers andremote_addressin clients instead ofhostandport.
Note:  Version 8.0 renames theWebSocketProtocolErrorexceptiontoProtocolError.
AWebSocketProtocolErroralias provides backwards compatibility.
Note:  Version 8.0 adds the reason phrase to the return type of the low-level APIread_response().
## Also:
•send(),ping(),  andpong()support  bytes-like  typesbytearrayandmemoryviewin  addition  to
bytes.
-  AddedConnectionClosedOKandConnectionClosedErrorsubclasses ofConnectionClosedto
tell apart normal connection termination from errors.
-  Addedbasic_auth_protocol_factory()to enforce HTTP Basic Auth on the server side.
•connect()handles redirects from the server during the handshake.
•connect()supports overridinghostandport.
-  Addedunix_connect()for connecting to Unix sockets.
-  Improved support for sending fragmented messages by accepting asynchronous iterators insend().
-  Prevented spurious log messages aboutConnectionClosedexceptions in keepalive ping task.  If you were
usingping_timeout=Noneas a workaround, you can remove it.
-  ChangedWebSocketServer.close()to perform a proper closing handshake instead of failing the con-
nection.
-  Avoided a crash when aextra_headerscallable returnsNone.
-  Improved error messages when HTTP parsing fails.
-  Enabled readline in the interactive client.
-  Added type hints (PEP 484).
-  Added a FAQ to the documentation.
-  Added documentation for extensions.
## 5.1.  Changelog61

websockets Documentation, Release 9.0
-  Documented how to optimize memory usage.
-  Improved API documentation.
## 5.1.8  7.0
## November 1, 2018
Warning:websocketsnow sends Ping frames at regular intervals and closes the connection if it doesn’t
receive a matching Pong frame.
SeeWebSocketCommonProtocolfor details.
Warning:Version   7.0   changes   how   a   server   terminates   connections   when   it’s   closed   with
WebSocketServer.close().
Previously, connections handlers were canceled. Now, connections are closed with close code 1001 (going away).
From the perspective of the connection handler, this is the same as if the remote endpoint was disconnecting. This
removes the need to prepare forCancelledErrorin connection handlers.
You can restore the previous behavior by adding the following line at the beginning of connection handlers:
defhandler(websocket, path):
closed = asyncio.ensure_future(websocket.wait_closed())
closed.add_done_callback(lambdatask: task.cancel())
Note:  Version 7.0 renames thetimeoutargument ofserve()andconnect()toclose_timeout.
This prevents confusion withping_timeout.
For backwards compatibility,timeoutis still supported.
Note:Version 7.0 changes how aping()that hasn’t received a pong yet behaves when the connection is
closed.
The ping — as inping = await websocket.ping()— used to be canceled when the connection is closed, so
thatawait pingraisedCancelledError. Nowawait pingraisesConnectionClosedlike other public
APIs.
Note:  Version 7.0 raises aRuntimeErrorexception if two coroutines callrecv()concurrently.
Concurrent calls lead to non-deterministic behavior because there are no guarantees about which coroutine will receive
which message.
## Also:
## •  Addedprocess_requestandselect_subprotocolargumentstoserve()and
WebSocketServerProtocolto  customizeprocess_request()andselect_subprotocol()
without subclassingWebSocketServerProtocol.
-  Added support for sending fragmented messages.
62Chapter 5.  Project

websockets Documentation, Release 9.0
-  Added thewait_closed()method to protocols.
-  Added an interactive client:python -m websockets <uri>.
-  Changed theoriginsargument to represent the lack of an origin withNonerather than''.
-  Fixed a data loss bug inrecv(): canceling it at the wrong time could result in messages being dropped.
-  Improved handling of multiple HTTP headers with the same name.
-  Improved error messages when a required HTTP header is missing.
## 5.1.9  6.0
## July 16, 2018
Warning:Version 6.0 introduces theHeadersclass for managing HTTP headers and changes several
public APIs:
•process_request()now receives aHeadersinstead of ahttp.client.HTTPMessagein the
request_headersargument.
-  Therequest_headersandresponse_headersattributes ofWebSocketCommonProtocolare
Headersinstead ofhttp.client.HTTPMessage.
## •  Theraw_request_headersandraw_response_headersattributesof
WebSocketCommonProtocolare removed. Useraw_items()instead.
-  Functions defined in thehandshakemodule now receiveHeadersin argument instead ofget_header
orset_headerfunctions. This affects libraries that rely on low-level APIs.
-  Functions defined in thehttpmodule now return HTTP headers asHeadersinstead of lists of(name,
value)pairs.
SinceHeadersandhttp.client.HTTPMessageprovide similar APIs, this change won’t affect most of the
code dealing with HTTP headers.
## Also:
-  Added compatibility with Python 3.7.
## 5.1.10  5.0.1
## May 24, 2018
-  Fixed a regression in 5.0 that broke some invocations ofserve()andconnect().
## 5.1.  Changelog63

websockets Documentation, Release 9.0
## 5.1.11  5.0
## May 22, 2018
Note:  Version 5.0 fixes a security issue introduced in version 4.0.
Version 4.0 was vulnerable to denial of service by memory exhaustion because it didn’t enforcemax_sizewhen
decompressing compressed messages (CVE-2018-1000518).
Note:  Version 5.0 adds auser_infofield to the return value ofparse_uri()andWebSocketURI.
If you’re unpackingWebSocketURIinto four variables, adjust your code to account for that fifth field.
## Also:
•connect()performs HTTP Basic Auth when the URI contains credentials.
-  Iterating on incoming messages no longer raises an exception when the connection terminates with close code
1001 (going away).
-  A plain HTTP request now receives a 426 Upgrade Required response and doesn’t log a stack trace.
•unix_serve()can be used as an asynchronous context manager on Python  3.5.1.
-  Added theclosedproperty to protocols.
-  If aping()doesn’t receive a pong, it’s canceled when the connection is closed.
-  Reported the cause ofConnectionClosedexceptions.
-  Added new examples in the documentation.
-  Updated documentation with new features from Python 3.6.
-  Improved several other sections of the documentation.
-  Fixed missing close code, which causedTypeErroron connection close.
-  Fixed a race condition in the closing handshake that raisedInvalidState.
-  Stopped logging stack traces when the TCP connection dies prematurely.
-  Prevented writing to a closing TCP connection during unclean shutdowns.
-  Made connection termination more robust to network congestion.
-  Prevented processing of incoming frames after failing the connection.
## 5.1.12  4.0.1
## November 2, 2017
-  Fixed issues with the packaging of the 4.0 release.
64Chapter 5.  Project

websockets Documentation, Release 9.0
## 5.1.13  4.0
## November 2, 2017
Warning:  Version 4.0 drops compatibility with Python 3.3.
Note:  Version 4.0 enables compression with the permessage-deflate extension.
In August 2017, Firefox and Chrome support it, but not Safari and IE.
Compression should improve performance but it increases RAM and CPU use.
If you want to disable compression, addcompression=Nonewhen callingserve()orconnect().
Note:  Version 4.0 removes thestate_nameattribute of protocols.
Useprotocol.state.nameinstead ofprotocol.state_name.
## Also:
•WebSocketCommonProtocolinstances can be used as asynchronous iterators on Python  3.6.  They yield
incoming messages.
-  Addedunix_serve()for listening on Unix sockets.
-  Added thesocketsattribute to the return value ofserve().
-  Reorganized and extended documentation.
-  Aborted connections if they don’t close within the configuredtimeout.
-  Rewrote connection termination to increase robustness in edge cases.
-  Stopped leaking pending tasks whencancel()is called on a connection while it’s being closed.
-  Reduced verbosity of “Failing the WebSocket connection” logs.
-  Allowedextra_headersto overrideServerandUser-Agentheaders.
## 5.1.14  3.4
## August 20, 2017
-  Renamedserve()andconnect()’sklassargument tocreate_protocolto reflect that it can also be
a callable. For backwards compatibility,klassis still supported.
•serve()can be used as an asynchronous context manager on Python  3.5.1.
-  Added support for customizing handling of incoming connections withprocess_request().
-  Made read and write buffer sizes configurable.
-  Rewrote HTTP handling for simplicity and performance.
-  Added an optional C extension to speed up low-level operations.
-  An invalid response status code duringconnect()now raisesInvalidStatusCodewith acodeattribute.
-  Providing asockargument toconnect()no longer crashes.
## 5.1.  Changelog65

websockets Documentation, Release 9.0
## 5.1.15  3.3
## March 29, 2017
-  Ensured compatibility with Python 3.6.
-  Reduced noise in logs caused by connection resets.
-  Avoided crashing on concurrent writes on slow connections.
## 5.1.16  3.2
## August 17, 2016
-  Addedtimeout,max_size, andmax_queuearguments toconnect()andserve().
-  Made server shutdown more robust.
## 5.1.17  3.1
## April 21, 2016
-  Avoided a warning when closing a connection before the opening handshake.
-  Added flow control for incoming data.
## 5.1.18  3.0
## December 25, 2015
Warning:  Version 3.0 introduces a backwards-incompatible change in therecv()API.
If you’re upgrading from 2.x or earlier, please read this carefully.
recv()used to returnNonewhen the connection was closed.  This required checking the return value of every
call:
message =awaitwebsocket.recv()
ifmessageis None:
return
Now  it  raises  aConnectionClosedexception  instead.   This  is  more Pythonic.   The  previous  code  can  be
simplified to:
message =awaitwebsocket.recv()
When implementing a server, which is the more popular use case, there’s no strong reason to handle such excep-
tions. Let them bubble up, terminate the handler coroutine, and the server will simply ignore them.
In   order   to   avoid   stranding   projects   built   upon   an   earlier   version,   the   previous   behavior   can   be   re-
stored  by  passinglegacy_recv=Truetoserve(),connect(),WebSocketServerProtocol,  or
WebSocketClientProtocol.legacy_recvisn’t documented in their signatures but isn’t scheduled for
deprecation either.
## Also:
•connect()can be used as an asynchronous context manager on Python  3.5.1.
66Chapter 5.  Project

websockets Documentation, Release 9.0
-  Updated documentation withawaitandasyncsyntax from Python 3.5.
•ping()andpong()support data passed asstrin addition tobytes.
-  Worked around anasynciobug affecting connection termination under load.
-  Madestate_nameattribute on protocols a public API.
-  Improved documentation.
## 5.1.19  2.7
## November 18, 2015
-  Added compatibility with Python 3.5.
-  Refreshed documentation.
## 5.1.20  2.6
## August 18, 2015
-  Addedlocal_addressandremote_addressattributes on protocols.
-  Closed open connections with code 1001 when a server shuts down.
-  Avoided TCP fragmentation of small frames.
## 5.1.21  2.5
## July 28, 2015
-  Improved documentation.
-  Provided access to handshake request and response HTTP headers.
-  Allowed customizing handshake request and response HTTP headers.
-  Added support for running on a non-default event loop.
-  Returned a 403 status code instead of 400 when the request Origin isn’t allowed.
-  Cancelingrecv()no longer drops the next message.
-  Clarified that the closing handshake can be initiated by the client.
-  Set the close code and reason more consistently.
-  Strengthened connection termination by simplifying the implementation.
-  Improved tests, added tox configuration, and enforced 100% branch coverage.
## 5.1.  Changelog67

websockets Documentation, Release 9.0
## 5.1.22  2.4
## January 31, 2015
-  Added support for subprotocols.
-  Addedloopargument toconnect()andserve().
## 5.1.23  2.3
## November 3, 2014
-  Improved compliance of close codes.
## 5.1.24  2.2
## July 28, 2014
-  Added support for limiting message size.
## 5.1.25  2.1
## April 26, 2014
-  Addedhost,portandsecureattributes on protocols.
-  Added support for providing and checking Origin.
## 5.1.26  2.0
## February 16, 2014
Warning:   Version 2.0 introduces a backwards-incompatible change in thesend(),ping(), andpong()
APIs.
If you’re upgrading from 1.x or earlier, please read this carefully.
These APIs used to be functions. Now they’re coroutines.
Instead of:
websocket.send(message)
you must now write:
awaitwebsocket.send(message)
## Also:
-  Added flow control for outgoing data.
68Chapter 5.  Project

websockets Documentation, Release 9.0
## 5.1.27  1.0
## November 14, 2013
-  Initial public release.
## 5.2  Contributing
Thanks for taking the time to contribute to websockets!
5.2.1  Code of Conduct
This project and everyone participating in it is governed by the Code of Conduct.  By participating, you are expected
to uphold this code. Please report inappropriate behavior to aymeric DOT augustin AT fractalideas DOT com.
(If I’m the person with the inappropriate behavior, please accept my apologies.  I know I can mess up.  I can’t expect
you to tell me, but if you choose to do so, I’ll do my best to handle criticism constructively. – Aymeric)
## 5.2.2  Contributions
Bug reports, patches and suggestions are welcome!
Please open an issue or send a pull request.
Feedback about the documentation is especially valuable — the authors ofwebsocketsfeel more confident about
writing code than writing docs :-)
If you’re wondering why things are done in a certain way,  thedesign documentprovides lots of details about the
internals of websockets.
## 5.2.3  Questions
GitHub issues aren’t a good medium for handling questions.  There are better places to ask questions, for example
## Stack Overflow.
If you want to ask a question anyway, please make sure that:
-  it’s a question aboutwebsocketsand not aboutasyncio;
-  it isn’t answered by the documentation;
-  it wasn’t asked already.
A good question can be written as a suggestion to improve the documentation.
## 5.2.  Contributing69

websockets Documentation, Release 9.0
5.2.4  Bitcoin users
websockets appears to be quite popular for interfacing with Bitcoin or other cryptocurrency trackers.  I’m strongly
opposed to Bitcoin’s carbon footprint.
I’m aware of efforts to build proof-of-stake models.  I’ll care once the total carbon footprint of all cryptocurrencies
drops to a non-bullshit level.
Please stop heating the planet where my children are supposed to live, thanks.
Sincewebsocketsis released under an open-source license, you can use it for any purpose you like.  However, I
won’t spend any of my time to help.
I will summarily close issues related to Bitcoin or cryptocurrency in any way.
## 5.3  License
## Copyright (c) 2013-2021 Aymeric Augustinandcontributors.
All rights reserved.
Redistributionanduseinsourceandbinary forms,with orwithout
modification, are permitted provided that the following conditions are met:
## *
Redistributions of source code must retain the above copyright notice,
this list of conditionsandthe following disclaimer.
## *
Redistributionsinbinary form must reproduce the above copyright notice,
this list of conditionsandthe following disclaimerinthe documentation
and/orother materials providedwiththe distribution.
## *
Neither the name of websockets nor the names of its contributors may
be used to endorseorpromote products derivedfrom thissoftware without
specific prior written permission.
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
## ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
## WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
## DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
## FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
## DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
## SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
## CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
## OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
## OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
70Chapter 5.  Project

websockets Documentation, Release 9.0
5.4  websockets for enterprise
5.4.1  Available as part of the Tidelift Subscription
Tidelift is working with the maintainers of websockets and thousands of other open source projects to deliver commer-
cial support and maintenance for the open source dependencies you use to build your applications. Save time, reduce
risk, and improve code health, while paying the maintainers of the exact dependencies you use.
5.4.2  Enterprise-ready open source software—managed for you
The Tidelift Subscription is a managed open source subscription for application dependencies covering millions of
open source projects across JavaScript, Python, Java, PHP, Ruby, .NET, and more.
Your subscription includes:
•Security updates
–Tidelift’s security response team coordinates patches for new breaking security vulnerabilities and alerts
immediately through a private channel, so your software supply chain is always secure.
•Licensing verification and indemnification
–Tidelift verifies license information to enable easy policy enforcement and adds intellectual property in-
demnification to cover creators and users in case something goes wrong. You always have a 100% up-to-
date bill of materials for your dependencies to share with your legal team, customers, or partners.
•Maintenance and code improvement
–Tidelift ensures the software you rely on keeps working as long as you need it to work.  Your managed
dependencies are actively maintained and we recruit additional maintainers where required.
•Package selection and version guidance
–We help you choose the best open source packages from the start—and then guide you through updates
to stay on the best releases as new issues arise.
•Roadmap input
–Take a seat at the table with the creators behind the software you use. Tidelift’s participating maintainers
earn more income as their software is used by more subscribers, so they’re interested in knowing what
you need.
•Tooling and cloud integration
–Tidelift works with GitHub, GitLab, BitBucket, and more.  We support every cloud platform (and other
deployment targets, too).
5.4.  websockets for enterprise71

websockets Documentation, Release 9.0
The  end  result?   All  of  the  capabilities  you  expect  from  commercial-grade  software,  for  the  full  breadth  of  open
source you use.  That means less time grappling with esoteric open source trivia, and more time building your own
applications—and your business.
72Chapter 5.  Project

## PYTHON MODULE INDEX
w
websockets.datastructures, 44
websockets.exceptions, 45
websockets.extensions.base, 42
websockets.extensions.permessage_deflate,
## 41
websockets.legacy.auth, 40
websockets.legacy.client, 27
websockets.legacy.server, 33
websockets.typing, 47
## 73

websockets Documentation, Release 9.0
74Python Module Index

## INDEX
## A
AbortHandshake, 45
## B
basic_auth_protocol_factory()(in   module
websockets.legacy.auth), 40
BasicAuthWebSocketServerProtocol(class in
websockets.legacy.auth), 41
## C
clear()(websockets.datastructures.Headers  method),
## 44
ClientExtensionFactory(class    in    websock-
ets.extensions.base), 42
ClientPerMessageDeflateFactory(class    in
websockets.extensions.permessage_deflate), 41
close()(websockets.legacy.client.WebSocketClientProtocol
method), 32
close()(websockets.legacy.server.WebSocketServer
method), 35
close()(websockets.legacy.server.WebSocketServerProtocol
method), 40
close_code(websock-
ets.legacy.client.WebSocketClientProtocol
attribute), 31
close_code(websock-
ets.legacy.server.WebSocketServerProtocol
attribute), 37
close_reason(websock-
ets.legacy.client.WebSocketClientProtocol
attribute), 31
close_reason(websock-
ets.legacy.server.WebSocketServerProtocol
attribute), 37
closed(websockets.legacy.client.WebSocketClientProtocol
attribute), 30
closed(websockets.legacy.server.WebSocketServerProtocol
attribute), 37
connect()(in module websockets.legacy.client), 28
ConnectionClosed, 45
ConnectionClosedError, 45
ConnectionClosedOK, 45
## D
decode()(websockets.extensions.base.Extension
method), 42
DuplicateParameter, 46
## E
encode()(websockets.extensions.base.Extension
method), 42
Extension(class in websockets.extensions.base), 42
## G
get_all()(websockets.datastructures.Headers
method), 44
get_request_params()(websock-
ets.extensions.base.ClientExtensionFactory
method), 42
## H
Headers(class in websockets.datastructures), 44
## I
InvalidHandshake, 46
InvalidHeader, 46
InvalidHeaderFormat, 46
InvalidHeaderValue, 46
InvalidMessage, 46
InvalidOrigin, 46
InvalidParameterName, 46
InvalidParameterValue, 46
InvalidState, 46
InvalidStatusCode, 46
InvalidUpgrade, 46
InvalidURI, 46
## L
local_address(websock-
ets.legacy.client.WebSocketClientProtocol
attribute), 30
local_address(websock-
ets.legacy.server.WebSocketServerProtocol
attribute), 36
## 75

websockets Documentation, Release 9.0
## M
module
websockets.datastructures, 44
websockets.exceptions, 45
websockets.extensions.base, 42
websockets.extensions.permessage_deflate,
## 41
websockets.legacy.auth, 40
websockets.legacy.client, 27
websockets.legacy.server, 33
websockets.typing, 47
MultipleValuesError, 44
## N
name()(websockets.extensions.base.ClientExtensionFactory
property), 43
name()(websockets.extensions.base.Extension   prop-
erty), 42
name()(websockets.extensions.base.ServerExtensionFactory
property), 43
NegotiationError, 46
## O
open(websockets.legacy.client.WebSocketClientProtocol
attribute), 30
open(websockets.legacy.server.WebSocketServerProtocol
attribute), 37
Origin()(in module websockets.typing), 47
## P
path(websockets.legacy.client.WebSocketClientProtocol
attribute), 30
path(websockets.legacy.server.WebSocketServerProtocol
attribute), 37
PayloadTooBig, 46
ping()(websockets.legacy.client.WebSocketClientProtocol
method), 32
ping()(websockets.legacy.server.WebSocketServerProtocol
method), 39
pong()(websockets.legacy.client.WebSocketClientProtocol
method), 32
pong()(websockets.legacy.server.WebSocketServerProtocol
method), 39
process_request()(websock-
ets.legacy.auth.BasicAuthWebSocketServerProtocol
method), 41
process_request()(websock-
ets.legacy.server.WebSocketServerProtocol
method), 37
process_request_params()(websock-
ets.extensions.base.ServerExtensionFactory
method), 43
process_response_params()(websock-
ets.extensions.base.ClientExtensionFactory
method), 43
ProtocolError, 46
## Python Enhancement Proposals
## PEP 484, 61
## R
raw_items()(websockets.datastructures.Headers
method), 44
recv()(websockets.legacy.client.WebSocketClientProtocol
method), 31
recv()(websockets.legacy.server.WebSocketServerProtocol
method), 38
RedirectHandshake, 46
remote_address(websock-
ets.legacy.client.WebSocketClientProtocol
attribute), 30
remote_address(websock-
ets.legacy.server.WebSocketServerProtocol
attribute), 37
request_headers(websock-
ets.legacy.client.WebSocketClientProtocol
attribute), 30
request_headers(websock-
ets.legacy.server.WebSocketServerProtocol
attribute), 37
response_headers(websock-
ets.legacy.client.WebSocketClientProtocol
attribute), 31
response_headers(websock-
ets.legacy.server.WebSocketServerProtocol
attribute), 37
## RFC
## RFC 6455, 49
## RFC 7235, 40
## RFC 7617, 40
## RFC 7692, 23, 41
## S
SecurityError, 47
select_subprotocol()(websock-
ets.legacy.server.WebSocketServerProtocol
method), 38
send()(websockets.legacy.client.WebSocketClientProtocol
method), 31
send()(websockets.legacy.server.WebSocketServerProtocol
method), 39
serve()(in module websockets.legacy.server), 33
ServerExtensionFactory(class    in    websock-
ets.extensions.base), 43
ServerPerMessageDeflateFactory(class    in
websockets.extensions.permessage_deflate), 42
76Index

websockets Documentation, Release 9.0
sockets(websockets.legacy.server.WebSocketServer
attribute), 34
subprotocol(websock-
ets.legacy.client.WebSocketClientProtocol
attribute), 31
subprotocol(websock-
ets.legacy.server.WebSocketServerProtocol
attribute), 37
Subprotocol()(in module websockets.typing), 47
## U
unix_connect()(inmodulewebsock-
ets.legacy.client), 28
unix_serve()(in  module  websockets.legacy.server),
## 34
username(websockets.legacy.auth.BasicAuthWebSocketServerProtocol
attribute), 41
## W
wait_closed()(websock-
ets.legacy.client.WebSocketClientProtocol
method), 32
wait_closed()(websock-
ets.legacy.server.WebSocketServermethod),
## 35
wait_closed()(websock-
ets.legacy.server.WebSocketServerProtocol
method), 40
WebSocketClientProtocol(class   in   websock-
ets.legacy.client), 29
WebSocketException, 47
WebSocketProtocolError(in   module   websock-
ets.exceptions), 47
websockets.datastructures
module, 44
websockets.exceptions
module, 45
websockets.extensions.base
module, 42
websockets.extensions.permessage_deflate
module, 41
websockets.legacy.auth
module, 40
websockets.legacy.client
module, 27
websockets.legacy.server
module, 33
websockets.typing
module, 47
WebSocketServer(classinwebsock-
ets.legacy.server), 34
WebSocketServerProtocol(class   in   websock-
ets.legacy.server), 35
## Index77