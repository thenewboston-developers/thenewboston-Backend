from django.core.cache import cache
from model_bakery import baker
from rest_framework import status


class TestUserSearchEndpoint:
    url = '/api/users/search'

    def test_unauthenticated_request(self, api_client):
        """Test that unauthenticated users cannot access the endpoint."""
        response = api_client.get(self.url, {'q': 'test'})
        assert (response.status_code, response.json()) == (
            status.HTTP_401_UNAUTHORIZED,
            {'message': 'Authentication credentials were not provided.', 'code': 'not_authenticated'},
        )

    def test_missing_query_parameter(self, authenticated_api_client):
        """Test that missing query parameter returns 400."""
        response = authenticated_api_client.get(self.url)
        assert (response.status_code, response.json()) == (
            status.HTTP_400_BAD_REQUEST,
            {'error': 'Query parameter "q" is required'},
        )

    def test_empty_query_parameter(self, authenticated_api_client):
        """Test that empty query parameter returns 400."""
        response = authenticated_api_client.get(self.url, {'q': ''})
        assert (response.status_code, response.json()) == (
            status.HTTP_400_BAD_REQUEST,
            {'error': 'Query parameter "q" is required'},
        )

    def test_whitespace_only_query(self, authenticated_api_client):
        """Test that whitespace-only query returns 400."""
        response = authenticated_api_client.get(self.url, {'q': '   '})
        assert (response.status_code, response.json()) == (
            status.HTTP_400_BAD_REQUEST,
            {'error': 'Query parameter "q" is required'},
        )

    def test_successful_search(self, authenticated_api_client, sample_search_users):
        """Test successful user search returns correct fields."""
        response = authenticated_api_client.get(self.url, {'q': 'alice'})
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert len(data) == 3  # alice, AliceWonder, ALICE_CAPS

        # Check that only minimal fields are returned
        for user in data:
            assert set(user.keys()) == {'id', 'username', 'avatar'}
            assert 'alice' in user['username'].lower()

    def test_case_insensitive_search(self, authenticated_api_client, sample_search_users):
        """Test that search is case-insensitive."""
        response_lower = authenticated_api_client.get(self.url, {'q': 'alice'})
        response_upper = authenticated_api_client.get(self.url, {'q': 'ALICE'})
        response_mixed = authenticated_api_client.get(self.url, {'q': 'AliCe'})

        assert (response_lower.status_code, response_upper.status_code, response_mixed.status_code) == (
            status.HTTP_200_OK,
            status.HTTP_200_OK,
            status.HTTP_200_OK,
        )

        # All should return same number of results
        assert len(response_lower.json()) == len(response_upper.json()) == len(response_mixed.json()) == 3

    def test_partial_match(self, authenticated_api_client, sample_search_users):
        """Test that partial username matches work."""
        response = authenticated_api_client.get(self.url, {'q': 'al'})
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert len(data) == 3  # alice, AliceWonder, ALICE_CAPS
        assert all('al' in user['username'].lower() for user in data)

    def test_no_results(self, authenticated_api_client, sample_search_users):
        """Test search with no matching users."""
        response = authenticated_api_client.get(self.url, {'q': 'xyz123'})
        assert (response.status_code, response.json()) == (status.HTTP_200_OK, [])

    def test_result_limit(self, authenticated_api_client, sample_search_users):
        """Test that results are limited to 10 users."""
        # Create more users with similar names
        for i in range(15):
            baker.make('users.User', username=f'testuser{i}')

        response = authenticated_api_client.get(self.url, {'q': 'test'})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()) == 10  # Should be limited to 10

    def test_cache_key_normalization(self, authenticated_api_client, sample_search_users):
        """Test that cache keys are normalized (lowercase)."""
        from thenewboston.users.utils.cache import generate_cache_key

        key1 = generate_cache_key('user_search', 'Alice')
        key2 = generate_cache_key('user_search', 'alice')
        key3 = generate_cache_key('user_search', 'ALICE')

        assert key1 == key2 == key3

    def test_throttling(self, authenticated_api_client, sample_search_users):
        """Test that rate limiting works (20 requests per minute)."""
        # Make 20 requests (should succeed)
        for i in range(20):
            response = authenticated_api_client.get(self.url, {'q': f'test{i}'})
            assert response.status_code == status.HTTP_200_OK

        # 21st request should be throttled
        response = authenticated_api_client.get(self.url, {'q': 'test21'})
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert 'Request was throttled' in response.json()['message']

    def test_special_characters_in_query(self, authenticated_api_client, sample_search_users):
        """Test search with special characters in query."""
        special_queries = ['@alice', 'alice!', 'ali-ce', 'ali_ce', 'ali.ce']

        for query in special_queries:
            response = authenticated_api_client.get(self.url, {'q': query})
            assert response.status_code == status.HTTP_200_OK

    def test_unicode_query(self, authenticated_api_client):
        """Test search with unicode characters."""
        baker.make('users.User', username='пользователь')

        response = authenticated_api_client.get(self.url, {'q': 'польз'})
        assert (response.status_code, len(response.json())) == (status.HTTP_200_OK, 1)

    def test_long_query_string(self, authenticated_api_client, sample_search_users):
        """Test search with very long query string."""
        long_query = 'a' * 1000
        response = authenticated_api_client.get(self.url, {'q': long_query})
        assert (response.status_code, response.json()) == (status.HTTP_200_OK, [])

    def test_cache_functionality(self, authenticated_api_client, sample_search_users):
        """Test basic cache functionality."""
        cache.clear()

        # First request should populate cache
        response1 = authenticated_api_client.get(self.url, {'q': 'alice'})
        assert response1.status_code == status.HTTP_200_OK

        # Second request should use cache (check results are consistent)
        response2 = authenticated_api_client.get(self.url, {'q': 'alice'})
        assert (response2.status_code, response1.json()) == (status.HTTP_200_OK, response2.json())

    def test_cache_miss_database_query(self, authenticated_api_client, sample_search_users):
        """Test that cache miss triggers database query and caching."""
        from unittest.mock import patch

        # from thenewboston.users.utils.cache import get_cached_user_search, user_search_cache

        # Clear cache to ensure miss
        cache.clear()

        # Mock cache to simulate miss then verify set is called
        with patch('thenewboston.users.views.user_search.get_cached_user_search') as mock_get_cache:
            with patch('thenewboston.users.views.user_search.set_cached_user_search') as mock_set_cache:
                mock_get_cache.return_value = None  # Cache miss

                response = authenticated_api_client.get(self.url, {'q': 'alice'})

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert len(data) == 3  # alice, AliceWonder, ALICE_CAPS

                # Verify cache was checked
                mock_get_cache.assert_called_once_with('alice')

                # Verify results were cached
                mock_set_cache.assert_called_once()
                call_args = mock_set_cache.call_args
                assert call_args[0][0] == 'alice'  # query
                assert len(call_args[0][1]) == 3  # results

    def test_database_query_with_serializer(self, authenticated_api_client, sample_search_users):
        """Test database query flow with serializer."""
        from unittest.mock import patch

        # Clear cache to force database query
        cache.clear()

        with patch('thenewboston.users.views.user_search.get_cached_user_search') as mock_cache:
            mock_cache.return_value = None  # Force cache miss

            response = authenticated_api_client.get(self.url, {'q': 'alice'})

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            # Verify serialized data structure
            assert len(data) == 3
            for user in data:
                assert 'id' in user
                assert 'username' in user
                assert 'avatar' in user
                assert 'alice' in user['username'].lower()
