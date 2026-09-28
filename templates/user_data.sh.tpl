#!/bin/bash
# v2: forced replacement via user_data_replace_on_change, since
# cloud-init only ever runs user-data once per instance ID.
set -e
exec > /var/log/ci-key-setup.log 2>&1
echo "ci-key-setup running at $(date)"
mkdir -p /home/ec2-user/.ssh
chmod 700 /home/ec2-user/.ssh
CI_KEY='${ci_ssh_public_key}'
if [ -n "$CI_KEY" ]; then
  echo "CI_KEY is non-empty (length: $${#CI_KEY} chars) - appending to authorized_keys"
  echo "$CI_KEY" >> /home/ec2-user/.ssh/authorized_keys
  chown ec2-user:ec2-user /home/ec2-user/.ssh/authorized_keys
  chmod 600 /home/ec2-user/.ssh/authorized_keys
  echo "Done. authorized_keys now has $(wc -l < /home/ec2-user/.ssh/authorized_keys) line(s)"
else
  echo "CI_KEY is EMPTY - var.ci_ssh_public_key was not passed in, skipping"
fi
