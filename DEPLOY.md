# Deploy production

## Initial deployment

Initial deployment is done once. [Update](#Update) section is executed for redeployment

1. Create environment specific configuration file
```bash
# Run on local machine:
ssh ubuntu@thenewboston.network 'sudo mkdir -p /etc/thenewboston' && \
scp thenewboston/project/settings/templates/template.env ubuntu@thenewboston.network:/tmp/template.env && \
ssh ubuntu@thenewboston.network 'sudo cp /tmp/template.env /etc/thenewboston/.env'

# Update `/etc/thenewboston/.env` with actual values at thenewboston.network
```

2. Install docker as described at https://docs.docker.com/engine/install/ on thenewboston.network
```bash
# Known working versions described in the comments below 

docker --version # Docker version 26.0.1, build d260a54

# (!!!) At least Docker Compose version v2.24.0 is required
docker compose version # Docker Compose version v2.26.1
```

3. Create database RDS instance:

   3.1 Open AWS RDS -> Databases: https://us-west-2.console.aws.amazon.com/rds/home?region=us-west-2#databases

   3.2 Click "Create database"

   3.3 Fill in the following:

   - Choose a database creation method: Standard create
   - Engine options -> Engine type: PostgreSQL
   - Engine options -> Engine version: 16.2
   - Templates: Free tier
   - Settings -> DB instance identifier: thenewboston
   - Settings -> Credentials Settings -> Master username: thenewboston
   - Settings -> Credentials Settings -> Credentials management: Self managed
   - Settings -> Credentials Settings -> Master password: <replace with password>
   - Settings -> Credentials Settings -> Confirm master password: <replace with password>
   - Instance configuration -> DB instance class -> Burstable classes (includes t classes): db.t3.micro
   - Storage -> Storage type -> gp2
   - Storage -> Allocated storage: 20
   - Storage -> Storage autoscaling -> Storage autoscaling -> Enable storage autoscaling: checked
   - Storage -> Storage autoscaling -> Storage autoscaling -> Maximum storage threshold: 40
   - Connectivity -> Compute resource: Don’t connect to an EC2 compute resource
   - Connectivity -> Network type: IPv4
   - Connectivity -> Virtual private cloud (VPC): Default VPC
   - Connectivity -> DB subnet group: default
   - Connectivity -> Public access: Yes
   - Connectivity -> VPC security group (firewall) -> Create new: Automatic setup
   - Connectivity -> New VPC security group name: thenewboston-database-sg
   - Database authentication -> Database authentication options: Password authentication
   - Monitoring -> Turn on Performance Insights: unchecked
   - Monitoring -> Additional configuration -> Enable Enhanced Monitoring: unchecked
   - Additional configuration -> Database options -> Initial database name: thenewboston
   - Additional configuration -> Log exports -> PostgreSQL log: checked
   - Additional configuration -> Log exports -> Upgrade log: checked
   - Additional configuration -> Deletion protection -> Enable deletion protection: checked
   - Additional configuration: leave defaults for the rest of the options

```bash
aws rds create-db-instance --db-instance-identifier thenewboston --db-instance-class db.t3.micro --engine postgres --engine-version 16.2 --allocated-storage 20 --master-username thenewboston --master-user-password '<replace with password>' --backup-retention-period 3 --db-subnet-group-name my-subnet-group --vpc-security-group-ids sg-xxxxxx --publicly-accessible
aws rds create-db-instance --db-instance-identifier thenewboston --db-instance-class db.t2.micro --engine postgres --allocated-storage 20 --master-username thenewboston  --master-user-password '<replace with password>' --backup-retention-period 3 --db-subnet-group-name my-subnet-group --vpc-security-group-ids sg-xxxxxx --no-publicly-accessible
aws ec2 authorize-security-group-ingress --group-id $SECURITY_GROUP_ID --protocol all --port all --cidr 0.0.0.0/0
aws rds modify-db-instance --db-instance-identifier $TARGET_DB_IDENTIFIER --vpc-security-group-ids $SECURITY_GROUP_ID --apply-immediately
aws rds wait db-instance-available --db-instance-identifier $TARGET_DB_IDENTIFIER
aws rds modify-db-instance --db-instance-identifier $TARGET_DB_IDENTIFIER --master-user-password "$NEW_DB_PASSWORD" --apply-immediately
```

## Update
1. Login:

```bash
ssh ubuntu@thenewboston.network
```

3. Fetch the latest code:

```bash
cd thenewboston-Backend && git fetch origin
```

3. Redeploy:

```bash
docker-compose down  # skip if docker-compose.yml did not change since last deployment
git checkout origin/master
make deploy
```
