import os

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class Settings:
    """Simple configuration management"""
    
    def __init__(self):
        # NVIDIA API
        self.NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
        
        # Google OAuth
        self.GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8501")
        self.GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "credentials.json")
        
        # Only validate if not in development mode
        if not os.getenv("SKIP_VALIDATION"):
            self.validate()
    
    def validate(self):
        """Validate required environment variables"""
        missing_vars = []
        
        if not self.NVIDIA_API_KEY:
            missing_vars.append("NVIDIA_API_KEY")
        
        if self.GOOGLE_CREDENTIALS_JSON == "credentials.json":
            if not os.path.exists("credentials.json"):
                missing_vars.append("GOOGLE_CREDENTIALS_JSON or credentials.json file")
        
        if missing_vars:
            error_msg = f"Missing required: {', '.join(missing_vars)}\n"
            error_msg += "Please check your .env file or add credentials.json"
            raise ValueError(error_msg)

# Global settings instance
settings = Settings()