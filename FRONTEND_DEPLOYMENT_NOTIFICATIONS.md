# Frontend Deployment Notifications

This implementation provides real-time notifications to connected frontend clients when a new frontend deployment occurs.

## Architecture Overview

### Components

1. **Database Model**: `FrontendDeployment` - Stores deployment timestamps and metadata
2. **WebSocket Consumer**: `FrontendDeploymentConsumer` - Broadcasts deployment updates to all connected clients
3. **REST API Endpoints** (via ViewSet):
   - `/api/deployments/trigger/` - Admin endpoint to register new deployments
   - `/api/deployments/status/` - Public endpoint for polling latest deployment timestamp
   - Standard CRUD endpoints for deployment management
4. **Django Admin Interface**: Allows admins to manage deployments through Django admin

### WebSocket Connection

Clients connect to: `ws://[host]/ws/deployment-updates`

All connected clients receive deployment notifications in this format:
```json
{
  "type": "deployment_update",
  "deployed_at": "2025-06-25T12:00:00Z"
}
```

### REST API Endpoints

#### 1. Trigger Deployment (Admin Only)
- **URL**: `POST /api/deployments/trigger/`
- **Permission**: Requires Django model permissions
- **Response**:
  ```json
  {
    "id": 1,
    "deployed_at": "2025-06-25T12:00:00Z",
    "deployed_by": 1,
    "deployed_by_username": "admin"
  }
  ```

#### 2. Get Deployment Status (Public)
- **URL**: `GET /api/deployments/status/`
- **Permission**: None (public)
- **Response**:
  ```json
  {
    "id": 1,
    "deployed_at": "2025-06-25T12:00:00Z",
    "deployed_by": 1,
    "deployed_by_username": "admin"
  }
  ```

#### 3. Standard ViewSet Endpoints
- `GET /api/deployments/` - List all deployments (requires auth)
- `POST /api/deployments/` - Create new deployment (requires auth)
- `GET /api/deployments/{id}/` - Retrieve specific deployment (requires auth)
- `PUT /api/deployments/{id}/` - Update deployment (requires auth)
- `DELETE /api/deployments/{id}/` - Delete deployment (requires auth)

## Client Implementation Guide

### WebSocket Connection (Recommended)

```javascript
// Connect to WebSocket
const ws = new WebSocket('ws://localhost:8000/ws/deployment-updates');

// Store current deployment timestamp
let currentDeploymentTime = localStorage.getItem('deploymentTime');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'deployment_update') {
    const newDeploymentTime = data.deployed_at;
    
    // Check if deployment is newer than current
    if (!currentDeploymentTime || new Date(newDeploymentTime) > new Date(currentDeploymentTime)) {
      // Show notification to user
      notifyUser('New version available! Refreshing...');
      
      // Store new deployment time
      localStorage.setItem('deploymentTime', newDeploymentTime);
      
      // Reload the application
      setTimeout(() => window.location.reload(), 2000);
    }
  }
};

// Handle connection errors with fallback to polling
ws.onerror = () => {
  console.log('WebSocket error, falling back to polling');
  startPolling();
};
```

### Polling Fallback

```javascript
function startPolling() {
  // Poll every 5 minutes
  setInterval(async () => {
    try {
      const response = await fetch('/api/deployments/status/');
      const data = await response.json();
      
      const newDeploymentTime = data.deployed_at;
      const currentDeploymentTime = localStorage.getItem('deploymentTime');
      
      if (!currentDeploymentTime || new Date(newDeploymentTime) > new Date(currentDeploymentTime)) {
        notifyUser('New version available! Refreshing...');
        localStorage.setItem('deploymentTime', newDeploymentTime);
        setTimeout(() => window.location.reload(), 2000);
      }
    } catch (error) {
      console.error('Polling error:', error);
    }
  }, 5 * 60 * 1000); // 5 minutes
}
```

## Admin Usage

### Via Django Admin

1. Navigate to Django Admin: `/admin/`
2. Go to "General" > "Frontend Deployments"
3. Click "Add Frontend Deployment"
4. Save - this will automatically broadcast to all connected clients

### Via API

```bash
# Trigger a new deployment (requires admin authentication)
curl -X POST http://localhost:8000/api/deployments/trigger/ \
  -H "Authorization: Bearer YOUR_AUTH_TOKEN" \
  -H "Content-Type: application/json"

# Create a deployment via standard endpoint
curl -X POST http://localhost:8000/api/deployments/ \
  -H "Authorization: Bearer YOUR_AUTH_TOKEN" \
  -H "Content-Type: application/json"
```

## Security Considerations

1. The trigger endpoint and standard CRUD operations require Django model permissions
2. Only authenticated users with appropriate permissions can create/modify deployments
3. The status endpoint is public to allow unauthenticated clients to check deployment status
4. WebSocket connections don't require authentication as they only receive broadcast messages

## Testing

1. Run migrations: `python manage.py migrate`
2. Create a superuser: `python manage.py createsuperuser`
3. Start the development server with Daphne for WebSocket support
4. Connect a test client to the WebSocket endpoint
5. Trigger a deployment via admin or API
6. Verify the client receives the notification and reloads

## File Structure

- `thenewboston/general/models/frontend_deployment.py` - FrontendDeployment model
- `thenewboston/general/consumers/frontend_deployment.py` - WebSocket consumer
- `thenewboston/general/views/frontend_deployment.py` - ViewSet implementation
- `thenewboston/general/serializers/frontend_deployment.py` - Serializer
- `thenewboston/general/serializers/general.py` - Base serializers and mixins
- `thenewboston/general/admin.py` - Admin configuration