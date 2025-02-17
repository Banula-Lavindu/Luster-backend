# STUN/TURN server configuration
ICE_SERVERS = [
    {
        "urls": [
            "stun:stun.l.google.com:19302",
            "stun:stun1.l.google.com:19302"
        ]
    },
    # Add your TURN server configuration here
    # {
    #     "urls": "turn:your-turn-server.com:3478",
    #     "username": "your-username",
    #     "credential": "your-password"
    # }
]

# WebRTC configuration
WEBRTC_CONFIG = {
    "iceServers": ICE_SERVERS,
    "iceTransportPolicy": "all",
    "bundlePolicy": "balanced",
    "rtcpMuxPolicy": "require",
    "iceCandidatePoolSize": 10
} 