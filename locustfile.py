from locust import HttpUser, task, between
import random

class ChatbotUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        """Called when a user starts"""
        self.session_id = f"test_user_{random.randint(1000, 9999)}"
    
    @task(3)
    def ask_admission_question(self):
        questions = [
            "What are the admission requirements?",
            "How do I apply for CSE?",
            "What documents are needed for admission?",
            "When is the admission deadline?",
            "What are the fees for engineering?"
        ]
        
        response = self.client.post("/api/chat", json={
            "message": random.choice(questions),
            "session_id": self.session_id
        })
    
    @task(2)
    def ask_course_question(self):
        questions = [
            "What courses are offered in computer science?",
            "Tell me about the curriculum",
            "What are the core subjects?",
            "Are there any electives available?"
        ]
        
        response = self.client.post("/api/chat", json={
            "message": random.choice(questions),
            "session_id": self.session_id
        })
    
    @task(1)
    def health_check(self):
        response = self.client.get("/health")