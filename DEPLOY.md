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

5. Install the latest software and prerequisites:

```bash
ssh ubuntu@thenewboston.network  # if necessary

sudo apt update && sudo apt upgrade
sudo apt install make nginx
sudo reboot
```

6. Configure nginx:
```bash
# Run on local machine:
scp thenewboston/project/settings/templates/nginx.conf ubuntu@thenewboston.network:/tmp/thenewboston.conf && \
ssh ubuntu@thenewboston.network 'sudo cp /tmp/thenewboston.conf /etc/nginx/sites-available/ && sudo ln -s /etc/nginx/sites-available/thenewboston.conf /etc/nginx/sites-enabled/thenewboston.conf && sudo rm /etc/nginx/sites-available/default'
```

7. Install certbot as described at https://certbot.eff.org/instructions?ws=nginx&os=ubuntufocal
   and verify automated renewal using the [checks below](#certificate-renewal-checks).

8. Create environment specific configuration file:

```bash
# Run on local machine:
ssh ubuntu@thenewboston.network 'sudo mkdir -p /etc/thenewboston' && \
scp thenewboston/project/settings/templates/template.env ubuntu@thenewboston.network:/tmp/template.env && \
ssh ubuntu@thenewboston.network 'sudo cp /tmp/template.env /etc/thenewboston/.env'
```

9. Update `/etc/thenewboston/.env` with actual values at thenewboston.network:

```bash
ssh ubuntu@thenewboston.network

sudo vim /etc/thenewboston/.env
```

10. Install docker as described at https://docs.docker.com/engine/install/ on thenewboston.network
11. Setup and check docker installation:

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

12. Create database RDS instance:

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

13. Clone git repo:

```bash
ssh ubuntu@thenewboston.network  # if necessary

git clone https://github.com/thenewboston-developers/thenewboston-Backend.git
```

14. Update docker-compose.yaml:

```bash
ssh ubuntu@thenewboston.network  # if necessary

bash -c 'cd ~/thenewboston-Backend && make update-docker-compose-yaml'
```

15. Run [Update](#Update) section

## Update
1. Login:

```bash
ssh ubuntu@thenewboston.network
```

2. Fetch the latest code:

```bash
cd ~/thenewboston-Backend && git fetch origin && git checkout origin/master
```

3. Redeploy:

```bash
make deploy
```

4. Clean up:

```bash
make deploy-cleanup
```

## Sentry performance monitoring

When `THENEWBOSTON_SETTING_SENTRY_DSN` is set, the Django and Celery integrations capture performance traces at a default 10% sampling rate, including instrumented database and outbound HTTP calls. Override the rate with `THENEWBOSTON_SETTING_SENTRY_TRACES_SAMPLE_RATE` (a number from 0 to 1) in `/etc/thenewboston/.env`, then recreate the application containers to apply the setting.

The API allows the `sentry-trace` and `baggage` CORS headers so requests from the frontend can continue the same trace. Deploy these backend settings before enabling cross-origin trace propagation in the frontend. In Sentry's Traces view, filter to the backend and frontend projects and the production environment, then load an authenticated page and inspect a sampled request and its database spans. Incoming sampled traces inherit their parent's sampling decision.

## Certificate renewal checks

Run these checks on the EC2 host:

```bash
certbot --version
sudo certbot certificates
systemctl list-timers --all --no-pager
```

Inspect the existing Certbot timer and its service with `systemctl status` and `systemctl cat`, including the next run and recent service logs. Installation methods use different unit names; check existing cron entries if no timer exists. Inspect the certificate's renewal configuration under `/etc/letsencrypt/renewal/` and existing renewal hooks before changing its authenticator, installer, or nginx reload behavior. Preserve the existing scheduler rather than adding a duplicate.

Use the certificate name reported above, which may differ from the domain:

```bash
CERTBOT_CERT_NAME='replace-with-name-from-certbot-certificates'
sudo certbot renew --cert-name "$CERTBOT_CERT_NAME" --dry-run
```

A dry run can temporarily change nginx configuration and reload it. Deploy hooks are skipped unless `--run-deploy-hooks` is supported and supplied; inspect hooks before testing them. See the [Certbot renewal documentation](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates).

After renewal, compare the served certificate's dates and fingerprint with the certificate file reported by `certbot certificates`. Run the following from outside the host:

```bash
openssl s_client -connect thenewboston.network:443 -servername thenewboston.network </dev/null 2>/dev/null \
  | openssl x509 -noout -dates -fingerprint -sha256
curl --max-time 15 --silent --show-error --output /dev/null --write-out 'HTTP %{http_code}\n' \
  https://thenewboston.network/api/login
```

The GET request may return HTTP 405 because login requires POST. TLS errors, timeouts, or HTTP 5xx still require investigation. Keep certificate verification enabled when testing login.

Configure an external certificate expiry and availability check: [Let's Encrypt stopped expiration notification emails on June 4, 2025](https://letsencrypt.org/2025/01/22/ending-expiration-emails/).

## Troubleshooting runtime filesystem exhaustion

An error such as `No space left on device` under `/run/systemd/journal/streams/` identifies the affected path, not necessarily a full root EBS volume. `/run` normally uses a separate tmpfs; check both byte and inode limits and identify the owner before choosing a repair:

```bash
findmnt -T /run -o TARGET,SOURCE,FSTYPE,OPTIONS
df -hT / /run /var/log /var/lib/docker
df -i / /run /var/log /var/lib/docker
free -h
sudo du -xhd1 /run
sudo du -x --inodes --max-depth=2 /run
```

Preserve these observations and relevant logs before rebooting, because `/run` is volatile. Do not delete arbitrary `/run` files: services use them for runtime state and sockets. Journald's `RuntimeMaxUse` and `RuntimeKeepFree` settings govern journal files under `/run/log/journal`, not stream metadata under `/run/systemd/journal/streams`. Set retention or capacity limits only after identifying the resource and process responsible. See [journald configuration](https://www.freedesktop.org/software/systemd/man/252/journald.conf.html) and [tmpfs limits](https://docs.kernel.org/filesystems/tmpfs.html).


## Guest computer games

Deploy the backend before the frontend that starts guest games. The normal app startup runs the new guest-session and game-ownership migrations. Existing account games and payouts continue using their existing paths. Restarting Celery and Celery Beat with this deployment registers the hourly `tasks.delete_expired_guest_games` cleanup.

Signed-out clients create a seven-day session with `POST /api/guest-games/session`, then send its signed `token` in `X-Guest-Token` on game requests. The response includes `session_id` for matching cached game snapshots, not for authorization. Game snapshots include `guest_mode`, `guest_session_id`, and `your_side`; the existing creation, polling, action, and rematch routes are unchanged. The CORS allowlist includes the new header.

Guest sessions authorize only free computer play, never account access, multiplayer stakes, purchases, or fund contributions. Guest games are private to the session and cannot become reward-bearing games after registration. A qualifying guest win returns an informational `computer_reward` with status `guest` and the advertised amount only when the fund is available; it creates no user, wallet, ledger entry, or payout decision. Expired sessions and their matches are deleted in bounded hourly batches. The session creation endpoint is throttled, and each session can have at most ten unfinished matches per game.

Guest capability responses are not cached, debug logs omit the session response, and Sentry scrubs the capability header. Keep `X-Guest-Token` out of any additional proxy or request logging configuration.

## Game product analytics

The optional PostHog server integration uses the same project ingestion key and ingestion host as the frontend. Configure `THENEWBOSTON_SETTING_POSTHOG_ENABLED=true`, `THENEWBOSTON_SETTING_POSTHOG_API_KEY`, and `THENEWBOSTON_SETTING_POSTHOG_HOST` (for this project, `https://us.i.posthog.com`). These are optional and default to disabled. The API key is the project ingestion token, never a personal API key. CI provisions these settings from `PROD_POSTHOG_KEY` and `PROD_POSTHOG_HOST` before deploying; an enabled deployment fails verification if the configuration or ingestion is broken.

Deploy the backend before the matching frontend. App startup applies the `product_analytics` migration; restarting Celery and Beat registers the 15-second `tasks.deliver_product_analytics` schedule. All event snapshots are saved in the same database transaction as the game, reward, deposit, or signup. A rollback discards them. The worker sends committed snapshots synchronously with their original timestamp and deterministic UUID, retries failures with backoff, and marks delivery only after the SDK acknowledges ingestion. An analytics write or delivery failure does not change game or financial behavior. Check undelivered `AnalyticsEvent` rows, their `attempts` and `next_attempt_at` when investigating a backlog. Outbox and participant snapshots are retained; this change introduces no historical backfill or analytics-data deletion policy.

CI verifies the deployed pipeline with `python -m thenewboston.manage verify_product_analytics --deployment-sha <40-character-commit-sha>`. The command queues and delivers `analytics_pipeline_verified` using `internal_traffic=true` and `$process_person_profile=false`, and fails unless PostHog acknowledges the event. This creates no game, signup, deposit, or reward. Confirm that event and deployment SHA in PostHog after rollout, then inspect real traffic for lifecycle events.

| Event | Authoritative meaning |
| --- | --- |
| `game_started` | A participant's newly created match becomes active. Pending/declined invitations do not count. Battleship begins at fleet placement; Backgammon counts the whole match once. |
| `game_engaged` | The participant's first successfully committed move, fleet placement, shot, roll, swap, or doubling action. Opening/polling a match, an invalid attempt, resigning without playing, and AI turns do not count. |
| `game_completed` | A previously tracked participant's match reaches a terminal played status, including worker timeouts. Includes outcome, finish reason, elapsed seconds, and reward decision/guest-offer status. |
| `game_reward_decided` | A new community-fund reward decision exists, including paid, ineligible, or insufficient-fund decisions. |
| `game_reward_paid` | A new community-fund ledger decision confirms an actual payout. Includes reward ID, recipient ID, game, match, TNB currency, and amount. Guest advertised winnings never count as paid. |
| `game_fund_deposited` | A new committed community-fund deposit. Includes deposit ID, donor ID, currency, and amount. Retried requests do not count twice. |
| `signup_completed` | The account was created successfully, with allowlisted game/reward-offer attribution when supplied by the browser. The standard `$identify` event links its preceding anonymous browser history. |

Lifecycle events are **per participant**, with `auth_state`, `game`, `mode`, `difficulty`, `match_id`, and `match_key`. Computer games have one human participant; multiplayer matches can have two. Count distinct `match_key` for matches, unique people for reach, and `game_engaged` for actual players. Use `game_started -> game_engaged -> game_completed` for play conversion; filter `auth_state=guest` for the guest funnel. Match `elapsed_seconds` includes idle time and must not be treated as active time on site. Community reward and deposit events cover fund transfers, not multiplayer stake settlement. Analyze reward appeal using the frontend's offer/click events followed by `signup_completed`; offer exposure alone does not establish causation.

The frontend passes `X-POSTHOG-DISTINCT-ID` and `X-POSTHOG-SESSION-ID` only to this API, plus `X-POSTHOG-OPT-OUT`, `X-POSTHOG-INTERNAL-TRAFFIC` and allowlisted game-attribution headers. Backend identity always uses the authenticated account ID, or the original anonymous ID for a verified guest owner. A spectator cannot replace participant identity or consent, and guest ownership never converts into an account payout after signup. A browser reset does not split an existing guest match across new anonymous IDs. Each human participant retains their own context, including a Connect Five challenger's context before acceptance. Read-only owner requests persist opt-out for subsequent worker outcomes. DNT/SDK opt-out suppresses events; blocked/missing browser telemetry cannot be reconstructed, and old matches are not fabricated as new starts.

Account events include the public username, numeric user ID and profile URL as person properties so reports can answer who earned or deposited. Anonymous events disable person-profile processing. No email, real name, password, request body, move payload, IP address, or guest capability is copied into the event. Exclude `internal_traffic=true` from public conversion/popularity reports; server staff status and the frontend internal flag are combined. Attribution is descriptive browser context, not authorization or proof of a payout.
