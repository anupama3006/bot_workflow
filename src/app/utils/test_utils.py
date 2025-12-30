import os
import subprocess
import time

import boto3

class TestUtils:
    @staticmethod
    def forward_port(server_cmd: str, sleep_time: int = 2) -> any:
        env = os.environ.copy()
        proc = subprocess.Popen(server_cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(sleep_time)
        if proc.poll() is not None and proc.returncode != 0:
            stderr = proc.stderr.read().decode()
            raise RuntimeError(f'Subprocess failed: {stderr}')
        return proc

    @staticmethod
    def get_vm_instance(aws_region: str) -> any:
        ec2 = boto3.client('ec2', region_name=aws_region)
        response = ec2.describe_instances(Filters=[{'Name': 'tag:Name', 'Values': ['cubeassist-ec2-dev-profile']}])
        instance_ids = [instance['InstanceId'] for reservation in response['Reservations'] for instance in reservation['Instances']]
        return instance_ids[0] if instance_ids else None

    @staticmethod    
    def start_port_forwarding(host, remote_port, local_port, aws_region, sleep_time: int = 2) -> any:
        server_cmd = [
            'aws', 'ssm', 'start-session',
            '--region', aws_region,
            '--target', TestUtils.get_vm_instance(aws_region),
            '--document-name', 'AWS-StartPortForwardingSessionToRemoteHost',
            '--parameters', f'host={host},portNumber={remote_port},localPortNumber={local_port}',
        ]
        return TestUtils.forward_port(server_cmd, sleep_time)