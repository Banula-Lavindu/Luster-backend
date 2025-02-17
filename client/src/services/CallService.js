class CallService {
    constructor() {
        this.peerConnection = null;
        this.localStream = null;
        this.remoteStream = null;
        this.ws = null;
        this.config = {
            iceServers: [
                {
                    urls: [
                        'stun:stun.l.google.com:19302',
                        'stun:stun1.l.google.com:19302'
                    ]
                }
            ]
        };
    }

    async initializeCall(token, callId, isVideo = false) {
        // Connect to signaling server
        this.ws = new WebSocket(`ws://your-server/ws/calls/signal/${token}`);
        
        // Get user media
        const constraints = {
            audio: true,
            video: isVideo
        };
        
        try {
            this.localStream = await navigator.mediaDevices.getUserMedia(constraints);
            
            // Create peer connection
            this.peerConnection = new RTCPeerConnection(this.config);
            
            // Add local stream
            this.localStream.getTracks().forEach(track => {
                this.peerConnection.addTrack(track, this.localStream);
            });
            
            // Handle remote stream
            this.peerConnection.ontrack = (event) => {
                this.remoteStream = event.streams[0];
                // Update UI with remote stream
            };
            
            // Handle ICE candidates
            this.peerConnection.onicecandidate = (event) => {
                if (event.candidate) {
                    this.ws.send(JSON.stringify({
                        type: 'ice-candidate',
                        call_id: callId,
                        candidate: event.candidate
                    }));
                }
            };
            
            // Handle WebSocket messages
            this.ws.onmessage = async (event) => {
                const message = JSON.parse(event.data);
                
                switch (message.type) {
                    case 'offer':
                        await this.handleOffer(message);
                        break;
                    case 'answer':
                        await this.handleAnswer(message);
                        break;
                    case 'ice-candidate':
                        await this.handleIceCandidate(message);
                        break;
                    case 'end-call':
                        this.endCall();
                        break;
                }
            };
            
        } catch (error) {
            console.error('Error initializing call:', error);
            throw error;
        }
    }

    // Other methods for handling offers, answers, and ICE candidates...
}

export default new CallService(); 