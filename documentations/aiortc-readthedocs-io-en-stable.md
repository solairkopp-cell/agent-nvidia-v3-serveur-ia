

aiortc
## Jeremy Lainé
## Oct 13, 2025



## CONTENTS
1  Why should I useaiortc?3
1.1   Examples . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .   3
1.2   API Reference  . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .   3
1.3   Helpers . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  17
1.4   Contributing  . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  19
1.5   Changelog  . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  19
1.6   License . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  33
## Python Module Index35
## Index37
i

ii

aiortc
aiortcis a library for Web Real-Time Communication (WebRTC) and Object Real-Time Communication (ORTC) in
Python. It is built on top ofasyncio, Python’s standard asynchronous I/O framework.
The API closely follows its Javascript counterpart while using pythonic constructs:
•promises are replaced by coroutines
•events are emitted usingpyee.EventEmitter
## CONTENTS1

aiortc
## 2CONTENTS

## CHAPTER
## ONE
## WHY SHOULD I USEAIORTC?
The main WebRTC and ORTC implementations are either built into web browsers, or come in the form of native
code. While they are extensively battle tested, their internals are complex and they do not provide Python bindings.
Furthermore they are tightly coupled to a media stack, making it hard to plug in audio or video processing algorithms.
In contrast, theaiortcimplementation is fairly simple and readable. As such it is a good starting point for programmers
wishing to understand how WebRTC works or tinker with its internals. It is also easy to create innovative products by
leveraging the extensive modules available in the Python ecosystem. For instance you can build a full server handling
both signaling and data channels or apply computer vision algorithms to video frames using OpenCV.
Furthermore, a lot of effort has gone into writing an extensive test suite for theaiortccode to ensure best-in-class
code quality.
## 1.1 Examples
aiortccomes with a selection of examples, which are a great starting point for new users.
The examples can be browsed on GitHub:
https://github.com/aiortc/aiortc/tree/main/examples
1.2 API Reference
1.2.1 WebRTC
classaiortc.RTCPeerConnection(configuration=None)
TheRTCPeerConnectioninterface represents a WebRTC connection between the local computer
and a remote peer.
## Parameters
configuration(Optional[RTCConfiguration])–Anoptional
RTCConfiguration.
property connectionState:  str
The current connection state.
Possible values:“connected”,“connecting”,“closed”,“failed”,“new”.
When the state changes, the“connectionstatechange”event is fired.
property iceConnectionState:  str
The current ICE connection state.
Possible values:“checking”,“completed”,“closed”,“failed”,“new”.
When the state changes, the“iceconnectionstatechange”event is fired.
## 3

aiortc
property iceGatheringState:  str
The current ICE gathering state.
Possible values:“complete”,“gathering”,“new”.
When the state changes, the“icegatheringstatechange”event is fired.
property localDescription:RTCSessionDescription
AnRTCSessionDescriptiondescribing the session for the local end of the connection.
property remoteDescription:RTCSessionDescription
AnRTCSessionDescriptiondescribing the session for the remote end of the connection.
property sctp:RTCSctpTransport| None
AnRTCSctpTransportdescribing the SCTP transport being used for datachannels orNone.
property signalingState:  str
The current signaling state.
Possible values:“closed”,“have-local-offer”,“have-remote-offer”,“stable”.
When the state changes, the“signalingstatechange”event is fired.
await addIceCandidate(candidate)
Add a newRTCIceCandidatereceived from the remote peer.
The specified candidate must have a value for eithersdpMidorsdpMLineIndex.
## Parameters
candidate(Optional[RTCIceCandidate]) – The new remote candidate orNone
to signal end-of-candidates.
Return type
## None
addTrack(track)
Add aMediaStreamTrackto the set of media tracks which will be transmitted to the remote
peer.
Return type
RTCRtpSender
addTransceiver(trackOrKind,direction='sendrecv')
Add a newRTCRtpTransceiver.
Return type
RTCRtpTransceiver
await close()
Terminate the ICE agent, ending ICE processing and streams.
Return type
## None
await createAnswer()
Create an SDP answer to an offer received from a remote peer during the offer/answer negotiation
of a WebRTC connection.
Return type
RTCSessionDescription
createDataChannel(label,maxPacketLifeTime=None,maxRetransmits=None,ordered=True,
protocol='',negotiated=False,id=None)
Create a data channel with the given label.
4Chapter 1. Why should I useaiortc?

aiortc
Return type
RTCDataChannel
await createOffer()
Create an SDP offer for the purpose of starting a new WebRTC connection to a remote peer.
Return type
RTCSessionDescription
getReceivers()
Returns the list ofRTCRtpReceiverobjects that are currently attached to the connection.
Return type
list[RTCRtpReceiver]
getSenders()
Returns the list ofRTCRtpSenderobjects that are currently attached to the connection.
Return type
list[RTCRtpSender]
await getStats()
Returns statistics for the connection.
Return type
RTCStatsReport
getTransceivers()
Returns the list ofRTCRtpTransceiverobjects that are currently attached to the connection.
Return type
list[RTCRtpTransceiver]
await setLocalDescription(sessionDescription=None)
Change the local description associated with the connection.
## Parameters
sessionDescription(Optional[RTCSessionDescription])    –    An
RTCSessionDescriptiongenerated bycreateOffer()orcreateAnswer()or
Noneto implicitly create an offer or create an answer, as needed.
Return type
## None
await setRemoteDescription(sessionDescription)
Changes the remote description associated with the connection.
## Parameters
sessionDescription(RTCSessionDescription)–An
RTCSessionDescriptioncreated from information received over the signal-
ing channel.
Return type
## None
classaiortc.RTCSessionDescription(sdp,type)
TheRTCSessionDescriptiondictionary describes one end of a connection and how it’s config-
ured.
classaiortc.RTCBundlePolicy
TheRTCBundlePolicyaffects which media tracks are negotiated if the remote endpoint is not
bundle-aware, and what ICE candidates are gathered.
See https://w3c.github.io/webrtc-pc/#rtcbundlepolicy-enum
1.2. API Reference5

aiortc
BALANCED ='balanced'
Gather ICE candidates for each media type in use (audio, video, and data). If the remote endpoint
is not bundle-aware, negotiate only one audio and video track on separate transports.
MAX_COMPAT ='max-compat'
Gather ICE candidates for each track. If the remote endpoint is not bundle-aware, negotiate all
media tracks on separate transports.
MAX_BUNDLE ='max-bundle'
Gather ICE candidates for only one track. If the remote endpoint is not bundle-aware, negotiate
only one media track.
classaiortc.RTCConfiguration(iceServers=None,
bundlePolicy=RTCBundlePolicy.BALANCED)
TheRTCConfigurationdictionary  is  used  to  provide  configuration  options  for  an
RTCPeerConnection.
iceServers:  Optional[list[RTCIceServer]] = None
A list ofRTCIceServerobjects to configure STUN / TURN servers.
bundlePolicy:RTCBundlePolicy='balanced'
The media-bundling policy to use when gathering ICE candidates.
1.2.2 Interactive Connectivity Establishment (ICE)
classaiortc.RTCIceCandidate(component,foundation,ip,port,priority,protocol,type,
relatedAddress=None,relatedPort=None,sdpMid=None,
sdpMLineIndex=None,tcpType=None)
TheRTCIceCandidateinterface represents a candidate Interactive Connectivity Establishment
(ICE) configuration which may be used to establish an RTCPeerConnection.
classaiortc.RTCIceGatherer(iceServers=None,local_username=None,local_password=None)
TheRTCIceGathererinterface gathers local host, server reflexive and relay candidates, as well as
enabling the retrieval of local Interactive Connectivity Establishment (ICE) parameters which can be
exchanged in signaling.
property state:  str
The current state of the ICE gatherer.
await gather()
Gather ICE candidates.
Return type
## None
classmethod getDefaultIceServers()
Return the list of defaultRTCIceServer.
Return type
list[RTCIceServer]
getLocalCandidates()
Retrieve the list of valid local candidates associated with the ICE gatherer.
Return type
list[RTCIceCandidate]
6Chapter 1. Why should I useaiortc?

aiortc
getLocalParameters()
Retrieve the ICE parameters of the ICE gatherer.
Return type
RTCIceParameters
classaiortc.RTCIceTransport(gatherer)
TheRTCIceTransportinterface allows an application access to information about the Interactive
Connectivity Establishment (ICE) transport over which packets are sent and received.
## Parameters
gatherer(RTCIceGatherer) – AnRTCIceGatherer.
property iceGatherer:RTCIceGatherer
The ICE gatherer passed in the constructor.
property role:  str
The current role of the ICE transport.
## Either‘controlling’or‘controlled’.
property state:  str
The current state of the ICE transport.
await addRemoteCandidate(candidate)
Add a remote candidate.
## Parameters
candidate(Optional[RTCIceCandidate]) – The new candidate orNoneto signal
end of candidates.
Return type
## None
getRemoteCandidates()
Retrieve the list of candidates associated with the remoteRTCIceTransport.
Return type
list[RTCIceCandidate]
await start(remoteParameters)
Initiate connectivity checks.
## Parameters
remoteParameters(RTCIceParameters) – TheRTCIceParametersassociated
with the remoteRTCIceTransport.
Return type
## None
await stop()
Irreversibly stop theRTCIceTransport.
Return type
## None
classaiortc.RTCIceParameters(usernameFragment=None,password=None,iceLite=False)
TheRTCIceParametersdictionary includes the ICE username fragment and password and other
ICE-related parameters.
usernameFragment:  Optional[str] = None
ICE username fragment.
1.2. API Reference7

aiortc
password:  Optional[str] = None
ICE password.
classaiortc.RTCIceServer(urls,username=None,credential=None,credentialType='password')
TheRTCIceServerdictionary defines how to connect to a single STUN or TURN server. It includes
both the URL and the necessary credentials, if any, to connect to the server.
urls:  Union[str, list[str]]
This required property is either a single string or a list of strings, each specifying a URL which
can be used to connect to the server.
username:  Optional[str] = None
The username to use during authentication (for TURN only).
credential:  Optional[str] = None
The credential to use during authentication (for TURN only).
1.2.3 Datagram Transport Layer Security (DTLS)
classaiortc.RTCCertificate(key,cert)
TheRTCCertificateinterface enables the certificates used by anRTCDtlsTransport.
To generate a certificate and the corresponding private key usegenerateCertificate().
property expires:  datetime
The date and time after which the certificate will be considered invalid.
getFingerprints()
Returns the list of certificate fingerprints, one of which is computed with the digest algorithm
used in the certificate signature.
Return type
list[RTCDtlsFingerprint]
classmethod generateCertificate()
Create and return an X.509 certificate and corresponding private key.
Return type
RTCCertificate
classaiortc.RTCDtlsTransport(transport,certificates)
TheRTCDtlsTransportobject includes information relating to Datagram Transport Layer Security
(DTLS) transport.
## Parameters
•transport(RTCIceTransport) – AnRTCIceTransport.
•certificates(list[RTCCertificate]) – A list ofRTCCertificate(only one
is allowed currently).
property state:  str
The current state of the DTLS transport.
One of‘new’,‘connecting’,‘connected’,‘closed’or‘failed’.
property transport:RTCIceTransport
The associatedRTCIceTransportinstance.
8Chapter 1. Why should I useaiortc?

aiortc
getLocalParameters()
Get the local parameters of the DTLS transport.
Return type
RTCDtlsParameters
await start(remoteParameters)
Start DTLS transport negotiation with the parameters of the remote DTLS transport.
## Parameters
remoteParameters(RTCDtlsParameters) – AnRTCDtlsParameters.
Return type
## None
await stop()
Stop and close the DTLS transport.
Return type
## None
classaiortc.RTCDtlsParameters(fingerprints=<factory>,role='auto')
TheRTCDtlsParametersdictionary includes information relating to DTLS configuration.
fingerprints:  list[RTCDtlsFingerprint]
List ofRTCDtlsFingerprint, one fingerprint for each certificate.
role:  str ='auto'
The DTLS role, with a default of auto.
classaiortc.RTCDtlsFingerprint(algorithm,value)
TheRTCDtlsFingerprintdictionary includes the hash function algorithm and certificate finger-
print.
algorithm:  str
The hash function name, for instance‘sha-256’.
value:  str
The fingerprint value.
1.2.4 Real-time Transport Protocol (RTP)
classaiortc.RTCRtpReceiver(kind,transport)
TheRTCRtpReceiverinterface  manages  the  reception  and  decoding  of  data  for  a
MediaStreamTrack.
## Parameters
•kind(str) – The kind of media (‘audio’or‘video’).
•transport(RTCDtlsTransport) – AnRTCDtlsTransport.
property track:MediaStreamTrack
TheMediaStreamTrackwhich is being handled by the receiver.
property transport:RTCDtlsTransport
TheRTCDtlsTransportover which the media for the receiver’s track is received.
classmethod getCapabilities(kind)
Returns the most optimistic view of the system’s capabilities for receiving media of the given
kind.
1.2. API Reference9

aiortc
Return type
RTCRtpCapabilities
await getStats()
Returns statistics about the RTP receiver.
Return type
RTCStatsReport
getSynchronizationSources()
Returns aRTCRtpSynchronizationSourcefor each unique SSRC identifier received in the
last 10 seconds.
Return type
list[RTCRtpSynchronizationSource]
await receive(parameters)
Attempt to set the parameters controlling the receiving of media.
## Parameters
parameters(RTCRtpReceiveParameters) – TheRTCRtpParametersfor the re-
ceiver.
Return type
## None
await stop()
Irreversibly stop the receiver.
Return type
## None
classaiortc.RTCRtpSender(trackOrKind,transport)
TheRTCRtpSenderinterface provides the ability to control and obtain details about how a particular
MediaStreamTrackis encoded and sent to a remote peer.
## Parameters
•trackOrKind(Union[MediaStreamTrack,str]) – Either aMediaStreamTrack
instance or a media kind (‘audio’or‘video’).
•transport(RTCDtlsTransport) – AnRTCDtlsTransport.
property track:MediaStreamTrack
TheMediaStreamTrackwhich is being handled by the sender.
property transport:RTCDtlsTransport
TheRTCDtlsTransportover which media data for the track is transmitted.
classmethod getCapabilities(kind)
Returns the most optimistic view of the system’s capabilities for sending media of the givenkind.
Return type
RTCRtpCapabilities
await getStats()
Returns statistics about the RTP sender.
Return type
RTCStatsReport
await send(parameters)
Attempt to set the parameters controlling the sending of media.
## Parameters
parameters(RTCRtpSendParameters) – TheRTCRtpSendParametersfor the
sender.
10Chapter 1. Why should I useaiortc?

aiortc
Return type
## None
await stop()
Irreversibly stop the sender.
Return type
## None
classaiortc.RTCRtpTransceiver(kind,receiver,sender,direction='sendrecv')
The RTCRtpTransceiver interface describes a permanent pairing of anRTCRtpSenderand an
RTCRtpReceiver, along with some shared state.
property currentDirection:  str | None
The currently negotiated direction of the transceiver.
One of‘sendrecv’,‘sendonly’,‘recvonly’,‘inactive’orNone.
property direction:  str
The preferred direction of the transceiver, which will be used inRTCPeerConnection.
createOffer()andRTCPeerConnection.createAnswer().
One of‘sendrecv’,‘sendonly’,‘recvonly’or‘inactive’.
property receiver:RTCRtpReceiver
TheRTCRtpReceiverthat handles receiving and decoding incoming media.
property sender:RTCRtpSender
TheRTCRtpSenderresponsible for encoding and sending data to the remote peer.
setCodecPreferences(codecs)
Override the default codec preferences.
SeeRTCRtpSender.getCapabilities()andRTCRtpReceiver.getCapabilities()for
the supported codecs.
## Parameters
codecs(list[RTCRtpCodecCapability]) – A list ofRTCRtpCodecCapability,
in decreasing order of preference. If empty, restores the default preferences.
Return type
## None
await stop()
Permanently stops theRTCRtpTransceiver.
Return type
## None
classaiortc.RTCRtpSynchronizationSource(timestamp,source)
TheRTCRtpSynchronizationSourcedictionary contains information about a synchronization
source (SSRC).
timestamp:  datetime
The timestamp associated with this source.
source:  int
The SSRC identifier associated with this source.
classaiortc.RTCRtpCapabilities(codecs=<factory>,headerExtensions=<factory>)
TheRTCRtpCapabilitiesdictionary provides information about support codecs and header exten-
sions.
1.2. API Reference11

aiortc
codecs:  list[RTCRtpCodecCapability]
A list ofRTCRtpCodecCapability.
headerExtensions:  list[RTCRtpHeaderExtensionCapability]
A list ofRTCRtpHeaderExtensionCapability.
classaiortc.RTCRtpCodecCapability(mimeType,clockRate,channels=None,
parameters=<factory>)
TheRTCRtpCodecCapabilitydictionary provides information on codec capabilities.
mimeType:  str
The codec MIME media type/subtype, for instance‘audio/PCMU’.
clockRate:  int
The codec clock rate expressed in Hertz.
channels:  Optional[int] = None
The number of channels supported (e.g. two for stereo).
parameters:  dict[str, Union[int, str, None]]
Codec-specific parameters available for signaling.
classaiortc.RTCRtpHeaderExtensionCapability(uri)
TheRTCRtpHeaderExtensionCapabilitydictionary provides information on a supported header
extension.
uri:  str
The URI of the RTP header extension.
classaiortc.RTCRtpParameters(codecs=<factory>,headerExtensions=<factory>,muxId='',
rtcp=<factory>)
TheRTCRtpParametersdictionary describes the configuration of anRTCRtpReceiveror an
RTCRtpSender.
codecs:  list[RTCRtpCodecParameters]
A list ofRTCRtpCodecParametersto send or receive.
headerExtensions:  list[RTCRtpHeaderExtensionParameters]
A list ofRTCRtpHeaderExtensionParameters.
muxId:  str =''
The muxId assigned to the RTP stream, if any, empty string if unset.
rtcp:RTCRtcpParameters
Parameters to configure RTCP.
classaiortc.RTCRtpCodecParameters(mimeType,clockRate,channels=None,
payloadType=None,rtcpFeedback=<factory>,
parameters=<factory>)
TheRTCRtpCodecParametersdictionary provides information on codec settings.
mimeType:  str
The codec MIME media type/subtype, for instance‘audio/PCMU’.
clockRate:  int
The codec clock rate expressed in Hertz.
12Chapter 1. Why should I useaiortc?

aiortc
channels:  Optional[int] = None
The number of channels supported (e.g. two for stereo).
payloadType:  Optional[int] = None
The value that goes in the RTP Payload Type Field.
rtcpFeedback:  list[RTCRtcpFeedback]
Transport layer and codec-specific feedback messages for this codec.
parameters:  dict[str, Union[int, str, None]]
Codec-specific parameters available for signaling.
classaiortc.RTCRtcpParameters(cname=None,mux=False,ssrc=None)
TheRTCRtcpParametersdictionary provides information on RTCP settings.
cname:  Optional[str] = None
The Canonical Name (CNAME) used by RTCP.
mux:  bool = False
Whether RTP and RTCP are multiplexed.
ssrc:  Optional[int] = None
The Synchronization Source identifier.
1.2.5 Stream Control Transmission Protocol (SCTP)
classaiortc.RTCSctpTransport(transport,port=5000)
TheRTCSctpTransportinterface includes information relating to Stream Control Transmission
Protocol (SCTP) transport.
## Parameters
transport(RTCDtlsTransport) – AnRTCDtlsTransport.
property maxChannels:  int | None
The maximum number ofRTCDataChannelthat can be used simultaneously.
property port:  int
The local SCTP port number used for data channels.
property state:  str
The current state of the SCTP transport.
property transport:RTCDtlsTransport
TheRTCDtlsTransportover which SCTP data is transmitted.
classmethod getCapabilities()
Retrieve the capabilities of the transport.
Return type
RTCSctpCapabilities
await start(remoteCaps,remotePort)
Start the transport.
Return type
## None
1.2. API Reference13

aiortc
await stop()
Stop the transport.
Return type
## None
class State(value)
classaiortc.RTCSctpCapabilities(maxMessageSize)
TheRTCSctpCapabilitiesdictionary provides information about the capabilities of the
RTCSctpTransport.
maxMessageSize:  int
The maximum size of data that the implementation can send or 0 if the implementation can
handle messages of any size.
1.2.6 Data channels
classaiortc.RTCDataChannel(transport,parameters,send_open=True)
TheRTCDataChannelinterface represents a network channel which can be used for bidirectional
peer-to-peer transfers of arbitrary data.
## Parameters
•transport(RTCSctpTransport) – AnRTCSctpTransport.
•parameters(RTCDataChannelParameters)–An
RTCDataChannelParameters.
property bufferedAmount:  int
The number of bytes of data currently queued to be sent over the data channel.
property bufferedAmountLowThreshold:  int
The number of bytes of buffered outgoing data that is considered “low”.
property negotiated:  bool
Whether data channel was negotiated out-of-band.
property id:  int | None
An ID number which uniquely identifies the data channel.
property label:  str
A name describing the data channel.
These labels are not required to be unique.
property ordered:  bool
Indicates whether or not the data channel guarantees in-order delivery of messages.
property maxPacketLifeTime:  int | None
The maximum time in milliseconds during which transmissions are attempted.
property maxRetransmits:  int | None
“The maximum number of retransmissions that are attempted.
property protocol:  str
The name of the subprotocol in use.
property readyState:  str
A string indicating the current state of the underlying data transport.
14Chapter 1. Why should I useaiortc?

aiortc
property transport:RTCSctpTransport
TheRTCSctpTransportover which data is transmitted.
close()
Close the data channel.
Return type
## None
send(data)
Senddataacross the data channel to the remote peer.
Return type
## None
classaiortc.RTCDataChannelParameters(label='',maxPacketLifeTime=None,
maxRetransmits=None,ordered=True,protocol='',
negotiated=False,id=None)
TheRTCDataChannelParametersdictionary describes the configuration of anRTCDataChannel.
label:  str =''
A name describing the data channel.
maxPacketLifeTime:  Optional[int] = None
The maximum time in milliseconds during which transmissions are attempted.
maxRetransmits:  Optional[int] = None
The maximum number of retransmissions that are attempted.
ordered:  bool = True
Whether the data channel guarantees in-order delivery of messages.
protocol:  str =''
The name of the subprotocol in use.
negotiated:  bool = False
Whether data channel will be negotiated out of-band, where both sides create data channel with
an agreed-upon ID.
id:  Optional[int] = None
An numeric ID for the channel; permitted values are 0-65534. If you don’t include this option,
the user agent will select an ID for you. Must be set when negotiating out-of-band.
## 1.2.7 Media
classaiortc.MediaStreamTrack
A single media track within a stream.
property id:  str
An automatically generated globally unique ID.
abstractmethod await recv()
Receive the nextAudioFrame,VideoFrameorPacket
Return type
Union[Frame,Packet]
1.2. API Reference15

aiortc
## 1.2.8 Statistics
classaiortc.RTCStatsReport
Provides statistics data about WebRTC connections as returned by theRTCPeerConnection.
getStats(),RTCRtpReceiver.getStats()andRTCRtpSender.getStats()coroutines.
This object consists of a mapping of string identifiers to objects which are instances of:
•RTCInboundRtpStreamStats
•RTCOutboundRtpStreamStats
•RTCRemoteInboundRtpStreamStats
•RTCRemoteOutboundRtpStreamStats
•RTCTransportStats
classaiortc.RTCInboundRtpStreamStats(timestamp,type,id,ssrc,kind,transportId,
packetsReceived,packetsLost,jitter)
TheRTCInboundRtpStreamStatsdictionary represents the measurement metrics for the incoming
RTP media stream.
classaiortc.RTCOutboundRtpStreamStats(timestamp,type,id,ssrc,kind,transportId,
packetsSent,bytesSent,trackId)
TheRTCOutboundRtpStreamStatsdictionary represents the measurement metrics for the outgoing
RTP stream.
classaiortc.RTCRemoteInboundRtpStreamStats(timestamp,type,id,ssrc,kind,transportId,
packetsReceived,packetsLost,jitter,
roundTripTime,fractionLost)
TheRTCRemoteInboundRtpStreamStatsdictionary represents the remote endpoint’s measure-
ment metrics for a particular incoming RTP stream.
classaiortc.RTCRemoteOutboundRtpStreamStats(timestamp,type,id,ssrc,kind,transportId,
packetsSent,bytesSent,
remoteTimestamp=None)
TheRTCRemoteOutboundRtpStreamStatsdictionary represents the remote endpoint’s measure-
ment metrics for its outgoing RTP stream.
classaiortc.RTCTransportStats(timestamp,type,id,packetsSent,packetsReceived,bytesSent,
bytesReceived,iceRole,dtlsState)
RTCTransportStats(timestamp: datetime.datetime, type: str, id: str, packetsSent: int, packetsRe-
ceived: int, bytesSent: int, bytesReceived: int, iceRole: str, dtlsState: str)
packetsSent:  int
Total number of packets sent over this transport.
packetsReceived:  int
Total number of packets received over this transport.
bytesSent:  int
Total number of bytes sent over this transport.
bytesReceived:  int
Total number of bytes received over this transport.
iceRole:  str
The current value ofRTCIceTransport.role.
16Chapter 1. Why should I useaiortc?

aiortc
dtlsState:  str
The current value ofRTCDtlsTransport.state.
## 1.3 Helpers
These classes are not part of the WebRTC or ORTC API, but provide higher-level helpers for tasks like manipulating
media streams.
1.3.1 Media sources
classaiortc.contrib.media.MediaPlayer(file,format=None,options=None,timeout=None,
loop=False,decode=True)
A media source that reads audio and/or video from a file.
## Examples:
# Open a video file.
player = MediaPlayer('/path/to/some.mp4')
# Open an HTTP stream.
player = MediaPlayer(
## 'http://download.tsi.telecom-paristech.fr/'
'gpac/dataset/dash/uhd/mux_sources/hevcds_720p30_2M.mp4')
# Open webcam on Linux.
player = MediaPlayer('/dev/video0', format='v4l2', options={
## 'video_size':'640x480'
## })
# Open webcam on OS X.
player = MediaPlayer('default:none', format='avfoundation', options={
## 'video_size':'640x480'
## })
# Open webcam on Windows.
player = MediaPlayer('video=Integrated Camera', format='dshow', options={
## 'video_size':'640x480'
## })
## Parameters
•file(Any) – The path to a file, or a file-like object.
•format(Optional[str]) – The format to use, defaults to autodect.
•options(Optional[dict[str,str]]) – Additional options to pass to FFmpeg.
•timeout(Optional[int]) – Open/read timeout to pass to FFmpeg.
•loop(bool) – Whether to repeat playback indefinitely (requires a seekable file).
property audio:MediaStreamTrack| None
Aaiortc.MediaStreamTrackinstance if the file contains audio.
property video:MediaStreamTrack| None
Aaiortc.MediaStreamTrackinstance if the file contains video.
## 1.3. Helpers17

aiortc
1.3.2 Media sinks
classaiortc.contrib.media.MediaRecorder(file,format=None,options=None)
A media sink that writes audio and/or video to a file.
## Examples:
# Write to a video file.
player = MediaRecorder('/path/to/file.mp4')
# Write to a set of images.
player = MediaRecorder('/path/to/file-%3d.png')
## Parameters
•file(Any) – The path to a file, or a file-like object.
•format(Optional[str]) – The format to use, defaults to autodect.
•options(Optional[dict[str,str]]) – Additional options to pass to FFmpeg.
addTrack(track)
Add a track to be recorded.
## Parameters
track(MediaStreamTrack) – Aaiortc.MediaStreamTrack.
Return type
## None
await start()
Start recording.
Return type
## None
await stop()
Stop recording.
Return type
## None
classaiortc.contrib.media.MediaBlackhole
A media sink that consumes and discards all media.
addTrack(track)
Add a track whose media should be discarded.
## Parameters
track(MediaStreamTrack) – Aaiortc.MediaStreamTrack.
Return type
## None
await start()
Start discarding media.
Return type
## None
await stop()
Stop discarding media.
Return type
## None
18Chapter 1. Why should I useaiortc?

aiortc
1.3.3 Media transforms
classaiortc.contrib.media.MediaRelay
A media source that relays one or more tracks to multiple consumers.
This is especially useful for live tracks such as webcams or media received over the network.
subscribe(track,buffered=True)
Create a proxy around the giventrackfor a new consumer.
## Parameters
•track(MediaStreamTrack) – SourceMediaStreamTrackwhich is relayed.
•buffered(bool) – Whether there need a buffer between the source track and
relayed track.
Return type
class
MediaStreamTrack
## 1.4 Contributing
Thanks for taking the time to contribute toaiortc!
1.4.1 Code of Conduct
This project and everyone participating in it is governed by the Code of Conduct. By participating, you are expected
to uphold this code. Please report inappropriate behavior to jeremy DOT laine AT m4x DOT org.
## 1.4.2 Contributions
Bug reports, patches and suggestions are welcome!
Please open an issue or send a pull request.
Feedback about the examples or documentation are especially valuable as they makeaiortcaccessible to a wider
audience.
Code contributionsmustcome with full unit test coverage. WebRTC is a complex protocol stack and ensuring correct
behaviour now and in the future requires a proper investment in automated testing.
## 1.4.3 Questions
GitHub issues aren’t a good medium for handling questions. There are better places to ask questions, for example Stack
## Overflow.
If you want to ask a question anyway, please make sure that:
•it’s a question aboutaiortcand not aboutasyncio;
•it isn’t answered by the documentation;
•it wasn’t asked already.
A good question can be written as a suggestion to improve the documentation.
## 1.5 Changelog
## 1.5.1 1.14.0
•AllowMediaRecorderto record audio and / or video to a WebM container.
## 1.4. Contributing19

aiortc
•Restore support for callingRTCPeerConnection.addIceCandidate()beforeRTCPeerConnection.
setRemoteDescription().
•Send a keyframe if an RTCP Full Instantaneous Resolution (FIR) feedback is received.
•Support parsing SDPrtcpattribute without a host.
•Use the “modern” SDP form “UDP/DTLS/SCTP” in offers to negotiate data channels.
•Relax versioned dependency on PyAV to allow version 15.x and 16.x.
•Add support for Python 3.14, drop end-of-life Python 3.9.
## 1.5.2 1.13.0
•Add support forG.722audio codec.
•Handle undecodable VP8 packages as was done prior to release 1.12.0.
•Limit the number of threads used for VP8 encoding as was done prior to release 1.12.0.
•Allow callingRTCPeerConnection.setLocalDescription()with no argument to implicitly create an offer
or answer as needed.
•Allow callingRTCPeerConnection.addIceCandidate()withNoneargument to signal remote end-of-
candidates.
•Support creating offers without media or data channels.
•Reject STUN URLs containing a “transport” query parameter.
•Ensure thewebcamexample shuts down cleanly onKeyboardInterrupt.
## 1.5.3 1.12.0
•Use PyAV to perform Opus + VP8 encoding and decoding. This meansaiortcis now pure Python.
•Allow configuring the media-bundling policy usingRTCConfiguration.bundlePolicy.
•Fix reversed track negotiated media ID (mid) when using multiple transceivers of the same kind.
•Fix theRTCIceServer.urlstyping to acceptList[str]in addition tostr.
•Fix octet count and packet count overflow inRTCRtpSenderwhen sending RTCP sender reports.
•FixRTCPeerConnection.addIceCandidate()when handling candidates with and m-line index and no media
## ID.
## 1.5.4 1.11.0
•Fix decoding of RTX retransmission packets.
•Drop support for obsoleteh264_omxcodec.
•Require PyAV 14.x to support recent FFmpeg versions.
•Require pyee 13.x for better typing support.
•Require pyOpenSSL 25.x and fix deprecation warnings.
20Chapter 1. Why should I useaiortc?

aiortc
## 1.5.5 1.10.1
•Build wheels for Linux aarch64 again.
•Be more cautious when releasingRTCRtpSender’s encoder.
•Set correct codec forMediaRecorderOGG output.
## 1.5.6 1.10.0
•Add support for Python 3.13, drop end-of-life Python 3.8.
•Stop building wheels for Linux aarch64 for now due to CI instability.
•Addpy.typedto indicate the package has typings, fix some annotations.
•Avoid early wraparound of RTP sequences numbers which can break SRTP.
•Add support forsha-384andsha-512DTLS certificate fingerprints.
•Allow using PyAV 13.x.
## 1.5.7 1.9.0
•Handle offers withactiveorpassiveDTLS setups.
•Stop using the deprecatedaudioopstandard library module.
•Allow using PyAV 12.x.
## 1.5.8 1.8.0
•Only send / receive RTP according toRTCRtpTransceiver.currentDirection.
•Close theRTCPeerConnectionif all DTLS transports are closed.
•Free the encoder as soon as theRTCRtpSenderstops to save memory.
•Modernise JavaScript inserverandwebcamexamples.
## 1.5.9 1.7.0
•Add support for GCM based SRTP protection profiles.
•Reduce supported DTLS cipher list to avoid Client Hello fragmentation.
•Fixutcnow()deprecation warning on Python 3.12.
## 1.5.10 1.6.0
•Build wheels usingPy_LIMITED_ABIto make them compatible with future Python versions.
•Build wheels using opus 1.4 and vpx 1.13.1.
•Use unique IDs for audio and video header extensions.
•AllowMediaRecorderto record audio from pulse.
## 1.5.11 1.5.0
•Make H.264 send a full picture when picture loss occurs.
•Fix TURN over TCP by updatingaioiceto 0.9.0.
•Make use of theifaddrpackage instead of the unmaintainednetifacespackage.
## 1.5. Changelog21

aiortc
## 1.5.12 1.4.0
•Build wheels for Python 3.11.
•AllowMediaPlayerto send media without transcoding.
•AllowMediaPlayerto specify a timeout when opening media.
•MakeRTCSctpTransporttransmit packets sooner to reduce datachannel latency.
•RefactorRTCDtlsTransportto use PyOpenSSL.
•MakeRTCPeerConnectionlog sent and received SDP when using verbose logging.
## 1.5.13 1.3.2
•Limit size of NACK reports to avoid excessive packet size.
•Improve H.264 codec matching.
•Determine video size from first frame received byMediaRecorder.
•Fix a deprecation warning when usingav>= 9.1.0.
•Tolerate STUN URLs containing aprotocolquerystring argument.
## 1.5.14 1.3.1
•Build wheels for aarch64 on Linux.
•AdaptMediaPlayerfor PyAV 9.x.
•Ensure H.264 produces B-frames by resetting picture type.
## 1.5.15 1.3.0
•Build wheels for Python 3.10 and for arm64 on Mac.
•Build wheels againstlibvpx1.10.
•Add support for looping inMediaPlayer.
•Add unbuffered option toMediaRelay.
•Calculate audio energy and send in RTP header extension.
•Fix a race condition in RTP sender/receiver shutdown.
•Improve performance of H.264 bitstream splitting code.
•Update imports forpyeeversion 9.x.
•Fully switch togoogle-crc32cinstead ofcrc32.
•Drop support for Python 3.6.
•Removeapprtccode as the service is no longer publicly hosted.
## 1.5.16 1.2.1
•Add a clear error message when no common codec is found.
•Replace thecrc32dependency withgoogle-crc32cwhich offers a more liberal license.
22Chapter 1. Why should I useaiortc?

aiortc
## 1.5.17 1.2.0
•Fix jitter buffer to avoid severe picture corruption under packet loss and send Picture Loss Indication (PLI) when
needed.
•Make H.264 encoder honour the bitrate from the bandwidth estimator.
•Add support for hardware-accelerated H.264 encoding on Raspberry Pi 4 using theh264_omxcodec.
•AddMediaRelayclass to allow sending media tracks to multiple consumers.
## 1.5.18 1.1.2
•AddRTCPeerConnection.connectionStateproperty.
•Correctly detect RTCIceTransport“failed”state.
•Correctly route RTP packets when there are multiple tracks of the same kind.
•Use full module name to name loggers.
## 1.5.19 1.1.1
•Defer adding remote candidates until after transport bundling to avoid unnecessary mDNS lookups.
## 1.5.20 1.1.0
•Add support for resolving mDNS candidates.
•Improve support for TURN, especially long-lived connections.
## 1.5.21 1.0.0
## Breaking
•MakeRTCPeerConnection.addIceCandidate()a coroutine.
•MakeRTCIceTransport.addRemoteCandidate()a coroutine.
## Media
•Handle SSRC attributes in SDP containing a colon (#372).
•Limit number of H.264 NALU per packet (#394, #426).
## Examples
•servermake it possible to specify bind address (#347).
## 1.5.22 0.9.28
Provide binary wheels for Linux, Mac and Windows on PyPI.
## 1.5.23 0.9.27
Data channels
•AddRTCSctpTransport.maxChannelsproperty.
•Recycle stream IDs (#256).
•Correctly close data channel when SCTP is not established (#300).
## 1.5. Changelog23

aiortc
## Media
•Add addRTCRtpReceiver.trackproperty (#298).
•Fix a crash inAimdRateControl(#295).
## 1.5.24 0.9.26
## DTLS
•Drop support for OpenSSL < 1.0.2.
## Examples
•apprtcfix handling of empty “candidate” message.
## Media
•Fix a MediaPlayer crash when stopping one track of a multi-track file (#237, #274).
•Fix a MediaPlayer error when stopping a track while waiting for the next frame.
•MakeRTCRtpSenderresilient to exceptions raised by media stream tracks (#283).
## 1.5.25 0.9.25
## Media
•Do not repeatedly send key frames after receiving a PLI.
## SDP
•Do not try to determine track ID if there is no Msid.
•Accept a star in rtcp-fb attributes.
## 1.5.26 0.9.24
Peer connection
•Assign DTLS role based on the SDP negotiation, not the resolved ICE role.
•When the peer is ICE lite, adopt the ICE controlling role, and do not use agressive nomination.
•Do not close transport onsetRemoteDescriptionif media and data are bundled.
•Set RemoteStreamTrack.id based on the Msid.
## Media
•Support alsa hardware output in MediaRecorder.
## SDP
•Add support for theice-liteattribute.
•Add support for receiving session-levelice-ufrag,ice-pwdandsetupattributes.
24Chapter 1. Why should I useaiortc?

aiortc
## Miscellaneous
•Switch fromattrsto standard Pythondataclasses.
•Use PEP-526 style variable annotations instead of comments.
## 1.5.27 0.9.23
•Drop support for Python 3.5.
•Drop dependency on PyOpenSSL.
•Use PyAV >= 7.0.0.
•Add partial type hints.
## 1.5.28 0.9.22
## DTLS
•Display exception if data handler fails.
## Examples
•serverandwebcam: add playsinline attribute for iOS compatibility.
•webcam: make it possible to play media from a file.
## Miscellaneous
•Use aioice >= 0.6.15 to not fail on mDNS candidates.
•Use pyee version 6.x.
## 1.5.29 0.9.21
## DTLS
•Call SSL_CTX_set_ecdh_auto for OpenSSL 1.0.2.
## Media
•Correctly route REMB packets to theRTCRtpSender.
## Examples
•MediaPlayer: release resources (e.g. webcam) when the player stops.
•ApprtcSignaling: make AppRTC signaling available for more examples.
•datachannel-cli: make uvloop optional.
•videostream-cli: animate the flag with a wave effect.
•webcam: explicitly set frame rate to 30 fps for webcams.
## 1.5.30 0.9.20
Data channels
•Support out-of-band negotiation and custom channel id.
## 1.5. Changelog25

aiortc
## Documentation
•Fix documentation build by installingcrc32cinstead ofcrcmod.
## Examples
•MediaPlayer: skip frames with no presentation timestamp (pts).
## 1.5.31 0.9.19
Data channels
•Do not raise congestion window when it is not fully utilized.
•Fix Highest TSN Newly Acknowledged logic for striking lost chunks.
•Do not limit congestion window to 120kB, limit burst size instead.
## Media
•Skip RTX packets with an empty payload.
## Examples
•apprtc: make the initiator send messages using an HTTP POST instead of WebSocket.
•janus: new example to connect to the Janus WebRTC server.
•server: add cartoon effect to video transforms.
## 1.5.32 0.9.18
## DTLS
•Do not use DTLSv1_get_timeout after DTLS handshake completes.
Data channels
•Add setter forRTCDataChannel.bufferedAmountLowThreshold.
•Usecrc32cpackage instead ofcrcmod, it provides better performance.
•Improve parsing and serialization code performance.
•Disable logging code if it is not used to improve performance.
## 1.5.33 0.9.17
## DTLS
•Do not bomb if SRTP is received before DTLS handshake completes.
Data channels
•Implement unordered delivery, so that theorderedoption is honoured.
•Implement partial reliability, so that themaxRetransmitsandmaxPacketLifeTimeoptions are honoured.
26Chapter 1. Why should I useaiortc?

aiortc
## Media
•Put all tracks in the same stream for now, fixes breakage introduced in 0.9.14.
•Use case-insensitive comparison for codec names.
•Use a=msid attribute in SDP instead of SSRC-level attributes.
## Examples
•server: make it possible to select unreliable mode for data channels.
•server: print the round-trip time for data channel messages.
## 1.5.34 0.9.16
## DTLS
•Log OpenSSL errors if the DTLS handshake fails.
•Fix DTLS handshake in server mode with OpenSSL < 1.1.0.
## Media
•AddRTCRtpReceiver.getCapabilities()andRTCRtpSender.getCapabilities().
•AddRTCRtpReceiver.getSynchronizationSources().
•AddRTCRtpTransceiver.setCodecPreferences().
## Examples
•server: make it possible to force audio codec.
•server: shutdown cleanly on Chrome which lacksRTCRtpTransceiver.stop().
## 1.5.35 0.9.15
Data channels
•Emit a warning if the crcmod C extension is not present.
## Media
•Support subsequent offer / answer exchanges.
•Route RTCP parameters to RTP receiver and sender independently.
•Fix a regression when the remote SSRC are not known.
•Fix VP8 descriptor parsing errors detected by fuzzing.
•Fix H264 descriptor parsing errors detected by fuzzing.
## 1.5.36 0.9.14
## Media
•Add support for RTX retransmission packets.
•Fix RTP and RTCP parsing errors detected by fuzzing.
•Use case-insensitive comparison for hash algorithm in SDP, fixes interoperability with Asterisk.
## 1.5. Changelog27

aiortc
•Offer NACK PLI and REMB feedback mechanisms for H.264.
## 1.5.37 0.9.13
Data channels
•Raise an exception ifRTCDataChannel.send()is called when readyState is not‘open’.
•Do not use stream sequence number for unordered data channels.
## Media
•Set VP8 target bitrate according to Receiver Estimated Maximum Bandwidth.
## Examples
•Correctly handle encoding in copy-and-paste signaling.
•server: add command line options to use HTTPS.
•webcam: add command line options to use HTTPS.
•webcam: add code to open webcam on OS X.
## 1.5.38 0.9.12
•Rework code in order to facilitate garbage collection and avoid memory leaks.
## 1.5.39 0.9.11
## Media
•Make AudioStreamTrack and VideoStreamTrack produce empty frames more regularly.
## Examples
•Fix a regession in copy-and-paste signaling which blocked the event loop.
## 1.5.40 0.9.10
Peer connection
•Sendraddrandrportparameters for server reflexive and relayed candidates. This is required for Firefox to accept
our STUN / TURN candidates.
•Do not raise an exception if ICE or DTLS connection fails, just change state.
## Media
•Revert to using asyncio’srun_in_executorto send data to the encoder, it greatly reduces the response time.
•Adjust package requirements to accept PyAV < 7.0.0.
## Examples
•webcam: force Chrome to use “unified-plan” semantics to enabledaddTransceiver.
•MediaPlayer: don’t sleep at all when playing from webcam. This eliminates the constant one-second lag in
thewebcamdemo.
28Chapter 1. Why should I useaiortc?

aiortc
## 1.5.41 0.9.9
.Warning
aiortcnow uses PyAV’sAudioFrameandVideoFrameclasses instead of defining its own.
## Media
•Use a jitter buffer for incoming audio.
•AddRTCPeerConnection.addTransceiver()method.
•AddRTCRtpTransceiver.directionto manage transceiver direction.
## Examples
•apprtc: demonstrate the use ofMediaPlayerandMediaRecorder.
•webcam: new examples illustrating sending video from a webcam to a browser.
•MediaPlayer: don’t sleep if a frame lacks timing information.
•MediaPlayer: removestart()andstop()methods.
•MediaRecorder: uselibx264for encoding.
•MediaRecorder: makestart()andstop()coroutines.
## 1.5.42 0.9.8
## Media
•Add support for H.264 video, a big thank you to @dsvictor94!
•Add support for sending Receiver Estimate Maximum Bitrate (REMB) feedback.
•Add support for parsing / serializing more RTP header extensions.
•Move each media encoder / decoder its one thread instead of using a thread pool.
## Statistics
•Add theRTCPeerConnection.getStats()coroutine to retrieve statistics.
•Add initialRTCTransportStatsto report transport statistics.
## Examples
•Add newMediaPlayerclass to read audio / video from a file.
•Add newMediaRecorderclass to write audio / video to a file.
•Add newMediaBlackholeclass to discard audio / video.
## 1.5.43 0.9.7
## Media
•Make RemoteStreamTrack emit an “ended” event, to simplify shutting down media consumers.
•Add RemoteStreamTrack.readyState property.
•Handle timestamp wraparound on sent RTP packets.
## 1.5. Changelog29

aiortc
## Packaging
•Add a versioned dependency on cffi>=1.0.0 to fix Raspberry Pi builds.
## 1.5.44 0.9.6
Data channels
•Optimize reception for improved latency and throughput.
## Media
•Add initialRTCRtpReceiver.getStats()andRTCRtpReceiver.getStats()coroutines.
## Examples
•datachannel-cli: display ping/pong roundtrip time.
## 1.5.45 0.9.5
## Media
•Make it possible to add multiple audio or video streams.
•Implement basic RTP video packet loss detection / retransmission using RTCP NACK feedback.
•Respond to Picture Loss Indications (PLI) by sending a keyframe.
•Use shorter MID values to reduce RTP header extension overhead.
•Correctly shutdown and discard unused transports when using BUNDLE.
## Examples
•server: make it possible to save received video to an AVI file.
## 1.5.46 0.9.4
Peer connection
•Add support for TURN over TCP.
## Examples
•Add media and signaling helpers inaiortc.contrib.
•Fix colorspace OpenCV colorspace conversions.
•apprtc: send rotating image on video track.
## 1.5.47 0.9.3
## Media
•Set PictureID attribute on outgoing VP8 frames.
•Negotiate and send SDES MID header extension for RTP packets.
•Fix negative packets_lost encoding for RTCP reports.
30Chapter 1. Why should I useaiortc?

aiortc
## 1.5.48 0.9.2
Data channels
•Numerous performance improvements in congestion control.
## Examples
•datachannel-filexfer: use uvloop instead of default asyncio loop.
## 1.5.49 0.9.1
Data channels
•Revert making RTCDataChannel.send a coroutine.
## 1.5.50 0.9.0
## Media
•Enable post-processing in VP8 decoder to remove (macro) blocks.
•Set target bitrate for VP8 encoder to 900kbps.
•Re-create VP8 encoder if frame size changes.
•Implement jitter estimation for RTCP reports.
•Avoid overflowing the DLSR field for RTCP reports.
•Raise video jitter buffer size.
Data channels
•BREAKING CHANGE: make RTCDataChannel.send a coroutine.
•Support spec-compliant SDP format for datachannels, as used in Firefox 63.
•Never send a negative advertised_cwnd.
## Examples
•datachannel-filexfer: new example for file transfer over a data channel.
•datachannel-vpn: new example for a VPN over a data channel.
•server: make it possible to select video resolution.
## 1.5.51 0.8.0
## Media
•Align VP8 settings with those used by WebRTC project, which greatly improves video quality.
•Send RTCP source description, sender report, receiver report and bye packets.
## Examples
## •server:
–make it possible to not transform video at all.
–allow video display to be up to 1280px wide.
## 1.5. Changelog31

aiortc
## •videostream-cli:
–fix Python 3.5 compatibility
## Miscellaneous
•Delay logging string interpolation to reduce cost of packet logging in non-verbose mode.
## 1.5.52 0.7.0
Peer connection
•AddRTCPeerConnection.addIceCandidate()method to handle trickled ICE candidates.
## Media
•Make stop() methods ofRTCRtpReceiver,RTCRtpSenderandRTCRtpTransceivercoroutines to enable
clean shutdown.
Data channels
•Clean upRTCDataChannelshutdown sequence.
•Support receiving an SCTPRE-CONFIGto raise number of inbound streams.
## Examples
## •server:
–perform some image processing using OpenCV.
–make it possible to disable data channels.
–make demo web interface more mobile-friendly.
## •apprtc:
–automatically create a room if no room is specified on command line.
## –handlebyecommand.
## 1.5.53 0.6.0
Peer connection
•Make it possible to specify one STUN server and / or one TURN server.
•AddBUNDLEsupport to use a single ICE/DTLS transport for multiple media.
•Move media encoding / decoding off the main thread.
Data channels
•Use SCTPABORTinstead ofSHUTDOWNwhen stoppingRTCSctpTransport.
•Advertise support for SCTPRE-CONFIGextension.
•MakeRTCDataChannelemitopenandcloseevents.
32Chapter 1. Why should I useaiortc?

aiortc
## Examples
•Add an example of how to connect to appr.tc.
•Capture audio frames to a WAV file in server example.
•Show datachannel open / close events in server example.
## 1.6 License
## Copyright (c) Jeremy Lainé.
All rights reserved.
Redistributionanduseinsourceandbinary forms,with orwithout
modification, are permitted provided that the following conditions are met:
- Redistributions of source code must retain the above copyright notice,
this list of conditionsandthe following disclaimer.
- Redistributionsinbinary form must reproduce the above copyright notice,
this list of conditionsandthe following disclaimerinthe documentation
and/orother materials providedwiththe distribution.
- Neither the name of aiortc nor the names of its contributors may
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
## 1.6. License33

aiortc
34Chapter 1. Why should I useaiortc?

## PYTHON MODULE INDEX
a
aiortc, 3
## 35

aiortc
36Python Module Index

## INDEX
## A
addIceCandidate()(aiortc.RTCPeerConnection
method), 4
addRemoteCandidate()(aiortc.RTCIceTransport
method), 7
addTrack()(aiortc.contrib.media.MediaBlackhole
method), 18
addTrack()(aiortc.contrib.media.MediaRecorder
method), 18
addTrack()(aiortc.RTCPeerConnection method), 4
addTransceiver()(aiortc.RTCPeerConnection
method), 4
aiortc
module, 3
algorithm(aiortc.RTCDtlsFingerprint attribute), 9
audio(aiortc.contrib.media.MediaPlayer property), 17
## B
BALANCED(aiortc.RTCBundlePolicy attribute), 5
bufferedAmount(aiortc.RTCDataChannel property),
## 14
bufferedAmountLowThreshold
(aiortc.RTCDataChannel property), 14
bundlePolicy(aiortc.RTCConfiguration attribute), 6
bytesReceived(aiortc.RTCTransportStats attribute), 16
bytesSent(aiortc.RTCTransportStats attribute), 16
## C
channels(aiortc.RTCRtpCodecCapability attribute), 12
channels(aiortc.RTCRtpCodecParameters  attribute),
## 12
clockRate(aiortc.RTCRtpCodecCapability attribute),
## 12
clockRate(aiortc.RTCRtpCodecParameters attribute),
## 12
close()(aiortc.RTCDataChannel method), 15
close()(aiortc.RTCPeerConnection method), 4
cname(aiortc.RTCRtcpParameters attribute), 13
codecs(aiortc.RTCRtpCapabilities attribute), 11
codecs(aiortc.RTCRtpParameters attribute), 12
connectionState(aiortc.RTCPeerConnection  prop-
erty), 3
createAnswer()(aiortc.RTCPeerConnection method),
## 4
createDataChannel()(aiortc.RTCPeerConnection
method), 4
createOffer()(aiortc.RTCPeerConnection method), 5
credential(aiortc.RTCIceServer attribute), 8
currentDirection(aiortc.RTCRtpTransceiver  prop-
erty), 11
## D
direction(aiortc.RTCRtpTransceiver property), 11
dtlsState(aiortc.RTCTransportStats attribute), 16
## E
expires(aiortc.RTCCertificate property), 8
## F
fingerprints(aiortc.RTCDtlsParameters attribute), 9
## G
gather()(aiortc.RTCIceGatherer method), 6
generateCertificate()(aiortc.RTCCertificate class
method), 8
getCapabilities()(aiortc.RTCRtpReceiver  class
method), 9
getCapabilities()(aiortc.RTCRtpSender   class
method), 10
getCapabilities()(aiortc.RTCSctpTransport  class
method), 13
getDefaultIceServers()(aiortc.RTCIceGatherer
class method), 6
getFingerprints()(aiortc.RTCCertificate method), 8
getLocalCandidates()(aiortc.RTCIceGatherer
method), 6
getLocalParameters()(aiortc.RTCDtlsTransport
method), 8
getLocalParameters()(aiortc.RTCIceGatherer
method), 6
getReceivers()(aiortc.RTCPeerConnection method),
## 5
getRemoteCandidates()(aiortc.RTCIceTransport
method), 7
## 37

aiortc
getSenders()(aiortc.RTCPeerConnection method), 5
getStats()(aiortc.RTCPeerConnection method), 5
getStats()(aiortc.RTCRtpReceiver method), 10
getStats()(aiortc.RTCRtpSender method), 10
getSynchronizationSources()
(aiortc.RTCRtpReceiver method), 10
getTransceivers()(aiortc.RTCPeerConnection
method), 5
## H
headerExtensions(aiortc.RTCRtpCapabilities  at-
tribute), 12
headerExtensions(aiortc.RTCRtpParameters   at-
tribute), 12
## I
iceConnectionState(aiortc.RTCPeerConnection
property), 3
iceGatherer(aiortc.RTCIceTransport property), 7
iceGatheringState(aiortc.RTCPeerConnection prop-
erty), 4
iceRole(aiortc.RTCTransportStats attribute), 16
iceServers(aiortc.RTCConfiguration attribute), 6
id(aiortc.MediaStreamTrack property), 15
id(aiortc.RTCDataChannel property), 14
id(aiortc.RTCDataChannelParameters attribute), 15
## L
label(aiortc.RTCDataChannel property), 14
label(aiortc.RTCDataChannelParameters attribute), 15
localDescription(aiortc.RTCPeerConnection prop-
erty), 4
## M
MAX_BUNDLE(aiortc.RTCBundlePolicy attribute), 6
MAX_COMPAT(aiortc.RTCBundlePolicy attribute), 6
maxChannels(aiortc.RTCSctpTransport property), 13
maxMessageSize(aiortc.RTCSctpCapabilities   at-
tribute), 14
maxPacketLifeTime(aiortc.RTCDataChannel  prop-
erty), 14
maxPacketLifeTime(aiortc.RTCDataChannelParameters
attribute), 15
maxRetransmits(aiortc.RTCDataChannel property),
## 14
maxRetransmits(aiortc.RTCDataChannelParameters
attribute), 15
MediaBlackhole(class in aiortc.contrib.media), 18
MediaPlayer(class in aiortc.contrib.media), 17
MediaRecorder(class in aiortc.contrib.media), 18
MediaRelay(class in aiortc.contrib.media), 19
MediaStreamTrack(class in aiortc), 15
mimeType(aiortc.RTCRtpCodecCapability attribute), 12
mimeType(aiortc.RTCRtpCodecParameters  attribute),
## 12
module
aiortc, 3
mux(aiortc.RTCRtcpParameters attribute), 13
muxId(aiortc.RTCRtpParameters attribute), 12
## N
negotiated(aiortc.RTCDataChannel property), 14
negotiated(aiortc.RTCDataChannelParameters
attribute), 15
## O
ordered(aiortc.RTCDataChannel property), 14
ordered(aiortc.RTCDataChannelParameters attribute),
## 15
## P
packetsReceived(aiortc.RTCTransportStats attribute),
## 16
packetsSent(aiortc.RTCTransportStats attribute), 16
parameters(aiortc.RTCRtpCodecCapability attribute),
## 12
parameters(aiortc.RTCRtpCodecParameters attribute),
## 13
password(aiortc.RTCIceParameters attribute), 7
payloadType(aiortc.RTCRtpCodecParameters   at-
tribute), 13
port(aiortc.RTCSctpTransport property), 13
protocol(aiortc.RTCDataChannel property), 14
protocol(aiortc.RTCDataChannelParameters   at-
tribute), 15
## R
readyState(aiortc.RTCDataChannel property), 14
receive()(aiortc.RTCRtpReceiver method), 10
receiver(aiortc.RTCRtpTransceiver property), 11
recv()(aiortc.MediaStreamTrack method), 15
remoteDescription(aiortc.RTCPeerConnection prop-
erty), 4
role(aiortc.RTCDtlsParameters attribute), 9
role(aiortc.RTCIceTransport property), 7
RTCBundlePolicy(class in aiortc), 5
RTCCertificate(class in aiortc), 8
RTCConfiguration(class in aiortc), 6
RTCDataChannel(class in aiortc), 14
RTCDataChannelParameters(class in aiortc), 15
RTCDtlsFingerprint(class in aiortc), 9
RTCDtlsParameters(class in aiortc), 9
RTCDtlsTransport(class in aiortc), 8
RTCIceCandidate(class in aiortc), 6
RTCIceGatherer(class in aiortc), 6
RTCIceParameters(class in aiortc), 7
RTCIceServer(class in aiortc), 8
38Index

aiortc
RTCIceTransport(class in aiortc), 7
RTCInboundRtpStreamStats(class in aiortc), 16
RTCOutboundRtpStreamStats(class in aiortc), 16
rtcp(aiortc.RTCRtpParameters attribute), 12
RTCPeerConnection(class in aiortc), 3
rtcpFeedback(aiortc.RTCRtpCodecParameters  at-
tribute), 13
RTCRemoteInboundRtpStreamStats(class in aiortc),
## 16
RTCRemoteOutboundRtpStreamStats(class in aiortc),
## 16
RTCRtcpParameters(class in aiortc), 13
RTCRtpCapabilities(class in aiortc), 11
RTCRtpCodecCapability(class in aiortc), 12
RTCRtpCodecParameters(class in aiortc), 12
RTCRtpHeaderExtensionCapability(class in aiortc),
## 12
RTCRtpParameters(class in aiortc), 12
RTCRtpReceiver(class in aiortc), 9
RTCRtpSender(class in aiortc), 10
RTCRtpSynchronizationSource(class in aiortc), 11
RTCRtpTransceiver(class in aiortc), 11
RTCSctpCapabilities(class in aiortc), 14
RTCSctpTransport(class in aiortc), 13
RTCSctpTransport.State(class in aiortc), 14
RTCSessionDescription(class in aiortc), 5
RTCStatsReport(class in aiortc), 16
RTCTransportStats(class in aiortc), 16
## S
sctp(aiortc.RTCPeerConnection property), 4
send()(aiortc.RTCDataChannel method), 15
send()(aiortc.RTCRtpSender method), 10
sender(aiortc.RTCRtpTransceiver property), 11
setCodecPreferences()(aiortc.RTCRtpTransceiver
method), 11
setLocalDescription()(aiortc.RTCPeerConnection
method), 5
setRemoteDescription()(aiortc.RTCPeerConnection
method), 5
signalingState(aiortc.RTCPeerConnection property),
## 4
source(aiortc.RTCRtpSynchronizationSource attribute),
## 11
ssrc(aiortc.RTCRtcpParameters attribute), 13
start()(aiortc.contrib.media.MediaBlackhole method),
## 18
start()(aiortc.contrib.media.MediaRecorder method),
## 18
start()(aiortc.RTCDtlsTransport method), 9
start()(aiortc.RTCIceTransport method), 7
start()(aiortc.RTCSctpTransport method), 13
state(aiortc.RTCDtlsTransport property), 8
state(aiortc.RTCIceGatherer property), 6
state(aiortc.RTCIceTransport property), 7
state(aiortc.RTCSctpTransport property), 13
stop()(aiortc.contrib.media.MediaBlackhole method),
## 18
stop()(aiortc.contrib.media.MediaRecorder method),
## 18
stop()(aiortc.RTCDtlsTransport method), 9
stop()(aiortc.RTCIceTransport method), 7
stop()(aiortc.RTCRtpReceiver method), 10
stop()(aiortc.RTCRtpSender method), 11
stop()(aiortc.RTCRtpTransceiver method), 11
stop()(aiortc.RTCSctpTransport method), 13
subscribe()(aiortc.contrib.media.MediaRelay
method), 19
## T
timestamp(aiortc.RTCRtpSynchronizationSource
attribute), 11
track(aiortc.RTCRtpReceiver property), 9
track(aiortc.RTCRtpSender property), 10
transport(aiortc.RTCDataChannel property), 14
transport(aiortc.RTCDtlsTransport property), 8
transport(aiortc.RTCRtpReceiver property), 9
transport(aiortc.RTCRtpSender property), 10
transport(aiortc.RTCSctpTransport property), 13
## U
uri(aiortc.RTCRtpHeaderExtensionCapability   at-
tribute), 12
urls(aiortc.RTCIceServer attribute), 8
username(aiortc.RTCIceServer attribute), 8
usernameFragment(aiortc.RTCIceParameters   at-
tribute), 7
## V
value(aiortc.RTCDtlsFingerprint attribute), 9
video(aiortc.contrib.media.MediaPlayer property), 17
## Index39