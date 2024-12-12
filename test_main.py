import pytest
import os
import json
from datetime import datetime
from unittest.mock import Mock, patch
import asyncio
from main import (
    get_next_report_filename,
    log_report_metadata,
    create_weekly_plot,
    consolidate_reports_and_create_weekly,
    get_next_weekly_folder
)

# Add timeout decorator
def timeout(seconds):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                pytest.fail(f"Test timed out after {seconds} seconds")
        return wrapper
    return decorator

# Test file naming function - Simple and fast
def test_get_next_report_filename(tmp_path):
    """Test get_next_report_filename function"""
    test_dir = tmp_path / "reports"
    test_dir.mkdir()
    
    filename1 = get_next_report_filename(str(test_dir))
    assert filename1.endswith("report1.md")

# Test metadata logging - Simple and fast
def test_log_report_metadata(tmp_path):
    """Test log_report_metadata function"""
    test_dir = tmp_path / "reports"
    test_dir.mkdir()
    
    test_metadata = {
        "filename": "report1.md",
        "generated_at": datetime.now().isoformat(),
        "ai": 4,
        "app": 3
    }
    
    log_report_metadata(str(test_dir), test_metadata)
    assert (test_dir / "metadata.json").exists()

# Test plot creation with timeout
@timeout(5)
async def test_create_weekly_plot(tmp_path):
    """Test create_weekly_plot function"""
    ai_hours = [4, 3, 5, 4, 3, 2, 3]
    app_hours = [3, 4, 4, 5, 3, 2, 2]
    
    with patch('matplotlib.pyplot.savefig') as mock_savefig:
        plot_filename = create_weekly_plot(ai_hours, app_hours, 1)
        assert mock_savefig.called
        assert plot_filename == 'week_1_development_hours.png'

# Test weekly folder creation - Simple and fast
def test_get_next_weekly_folder(tmp_path):
    """Test get_next_weekly_folder function"""
    test_weekly_dir = tmp_path / "weekly-report"
    test_weekly_dir.mkdir()
    
    with patch('main.WEEKLY_DIR', str(test_weekly_dir)):
        folder1 = get_next_weekly_folder()
        assert "daily-report-week1" in folder1

# Test message handler with timeout
@timeout(5)
@pytest.mark.asyncio
async def test_handle_files():
    """Test handle_files function"""
    mock_message = Mock()
    mock_message.content_type = 'audio'
    mock_message.audio.mime_type = 'audio/mp3'
    mock_message.audio.file_id = 'test_file_id'
    mock_message.chat.id = '123'
    
    with patch('main.bot') as mock_bot, \
         patch('main.whisper') as mock_whisper, \
         patch('main.get_gpt_response') as mock_gpt:
        
        mock_whisper.return_value = "Test transcription"
        mock_gpt.return_value = "Test response"
        
        from main import handle_files
        await handle_files(mock_message)
        
        assert mock_bot.reply_to.called

if __name__ == '__main__':
    pytest.main(['-v', '--tb=short']) 