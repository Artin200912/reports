import pytest
import os

@pytest.fixture(autouse=True)
def setup_test_env():
    """Setup test environment variables"""
    os.environ['BOT_TOKEN'] = '8172736928:AAFPwG5khBTYSWZzL2ItLVIWDCLKYfdirlw'
    os.environ['OPENAI_API_KEY'] = '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'
    os.environ['GROQ_API_KEY'] = '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' 