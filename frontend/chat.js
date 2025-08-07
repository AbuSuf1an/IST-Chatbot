class ChatBot {
    constructor() {
        this.sessionId = localStorage.getItem('chatbot_session_id');
        this.conversationHistory = [];
    }
    
    async sendMessage(message) {
        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    session_id: this.sessionId
                })
            });
            
            const data = await response.json();
            
            // Store session ID
            if (data.session_id) {
                this.sessionId = data.session_id;
                localStorage.setItem('chatbot_session_id', this.sessionId);
            }
            
            // Update conversation history
            this.conversationHistory.push({
                user: message,
                bot: data.response,
                timestamp: data.timestamp
            });
            
            return data.response;
            
        } catch (error) {
            console.error('Chat error:', error);
            throw error;
        }
    }
    
    async clearSession() {
        if (this.sessionId) {
            await fetch(`/chat/session/${this.sessionId}`, {
                method: 'DELETE'
            });
            
            localStorage.removeItem('chatbot_session_id');
            this.sessionId = null;
            this.conversationHistory = [];
        }
    }
}