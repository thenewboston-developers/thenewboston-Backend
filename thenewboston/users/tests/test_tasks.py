from unittest.mock import patch

import pytest

from thenewboston.users.tasks import warm_user_cache


class TestWarmUserCache:
    """Test the warm_user_cache Celery task."""

    def test_warm_user_cache_success(self):
        """Test successful execution of warm_user_cache task."""
        with patch('thenewboston.users.tasks.warm_popular_users_cache') as mock_warm_cache:
            with patch('thenewboston.users.tasks.logger') as mock_logger:
                result = warm_user_cache()

                # Verify the cache warming function was called
                mock_warm_cache.assert_called_once()

                # Verify success was logged
                mock_logger.info.assert_called_once_with('Successfully warmed popular users cache')

                # Verify return value
                assert result == 'Cache warming completed'

    def test_warm_user_cache_exception(self):
        """Test exception handling in warm_user_cache task."""
        test_exception = Exception('Cache warming failed')

        with patch('thenewboston.users.tasks.warm_popular_users_cache') as mock_warm_cache:
            mock_warm_cache.side_effect = test_exception

            with patch('thenewboston.users.tasks.logger') as mock_logger:
                with pytest.raises(Exception) as exc_info:
                    warm_user_cache()

                # Verify the original exception is raised
                assert exc_info.value == test_exception

                # Verify error was logged
                mock_logger.error.assert_called_once_with('Failed to warm cache: Cache warming failed')

    def test_warm_user_cache_task_registration(self):
        """Test that the task is properly registered with Celery."""
        # Verify the task is decorated as a shared task
        assert hasattr(warm_user_cache, 'delay')
        assert hasattr(warm_user_cache, 'apply_async')

        # Verify task name
        assert warm_user_cache.name == 'thenewboston.users.tasks.warm_user_cache'

    def test_warm_user_cache_imports(self):
        """Test that all required imports are working."""
        # This test ensures all imports in tasks.py are executed
        import thenewboston.users.tasks

        # Verify the module has the expected attributes
        assert hasattr(thenewboston.users.tasks, 'logger')
        assert hasattr(thenewboston.users.tasks, 'warm_user_cache')
        assert hasattr(thenewboston.users.tasks, 'warm_popular_users_cache')
