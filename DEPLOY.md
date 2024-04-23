# Deploy production

## Initial deployment

Initial deployment is done once. [Update](#Update) section is executed for redeployment

1. Create EC2 instance:

   1.1 Open EC2 console: https://us-west-2.console.aws.amazon.com/ec2/home?region=us-west-2

   1.2 Click "Launch instance"

   1.3 Fill in the following:

   - Name and tags -> Name: thenewboston.network
   - Application and OS Images: Ubuntu Server 22.04 LTS (HVM), SSD Volume Type, Architecture = 64-bit (x86)
   - Instance type: t2.micro
   - Key pair (login): choose a key pair from the list
   - Network settings: Create security group
   - Network settings: Allow SSH traffic from (Anywhere), Allow HTTPS traffic from the internet, Allow HTTP traffic from the internet
   - Configure storage: 20 Gb (gp2)

   1.4 Click "Launch instance"

2. Create elastic IPv4 address and assign to the EC2 instance
3. Create DNS A record `thenewboston.network` pointing to the elastic IPv4 address
4. Add 4G swapfile (this is necessary to avoid out of memory errors which lead to EC2 instance reboot):

```bash
# Login to the EC2 instance
ssh ubuntu@thenewboston.network
sudo  -i

# Allocate swap space
fallocate -l 4G /swapfile && \
chmod 600 /swapfile && \
mkswap /swapfile

# Turn on swap file
swapon /swapfile
vim /etc/fstab
# Add the following line
# /swapfile swap swap defaults 0 0

# Correcting swappiness
sysctl vm.swappiness=10
vim /etc/sysctl.conf
# Add the following line
# vm.swappiness=10

# Reboot
reboot

# Login to the EC2 instance again
ssh ubuntu@thenewboston.network

# Validate new settings
free -h
swapon --show
cat /proc/sys/vm/swappiness
```

5. Upgrade to the latest software:

```bash
ssh ubuntu@thenewboston.network  # if necessary

sudo apt update && sudo apt upgrade
sudo reboot
```

6. Create environment specific configuration file:

```bash
# Run on local machine:
ssh ubuntu@thenewboston.network 'sudo mkdir -p /etc/thenewboston' && \
scp thenewboston/project/settings/templates/template.env ubuntu@thenewboston.network:/tmp/template.env && \
ssh ubuntu@thenewboston.network 'sudo cp /tmp/template.env /etc/thenewboston/.env'
```

7. Update `/etc/thenewboston/.env` with actual values at thenewboston.network:

```bash
ssh ubuntu@thenewboston.network

sudo vim /etc/thenewboston/.env
```
   
8. Install docker as described at https://docs.docker.com/engine/install/ on thenewboston.network
9. Setup and check docker installation:

```bash
ssh ubuntu@thenewboston.network
sudo usermod -aG docker $USER
exit

ssh ubuntu@thenewboston.network

# Known working versions described in the comments below 
docker --version # Docker version 26.0.1, build d260a54

# (!!!) At least Docker Compose version v2.24.0 is required
docker compose version # Docker Compose version v2.26.1
```

10. Create database RDS instance:

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

12. Clone git repo:

```bash
ssh ubuntu@thenewboston.network  # if necessary

git clone https://github.com/thenewboston-developers/thenewboston-Backend.git
```

13. Update docker-compose.yaml:

```bash
ssh ubuntu@thenewboston.network  # if necessary

cd ~/thenewboston-Backend && make update-docker-compose-yaml
```

14. Run [Update](#Update) section

## Update
1. Login:

```bash
ssh ubuntu@thenewboston.network
```

2. Fetch the latest code:

```bash
cd thenewboston-Backend && git fetch origin && git checkout origin/master
```

3. Redeploy:

```bash
make deploy
```
