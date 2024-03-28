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
docker-compose down
git checkout origin/master
make deploy
```
