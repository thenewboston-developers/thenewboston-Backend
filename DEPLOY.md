# Deploy production

## Update
1. Login:
```bash
ssh ubuntu@thenewboston.network
```
2. Fetch the latest code:
```bash
cd thenewboston-Backend && git fetch origin
```
3. Redeploy:
```bash
docker-compose down  # skip if docker-compose.yml did not change since last deployment
git checkout origin/master
make deploy
```
