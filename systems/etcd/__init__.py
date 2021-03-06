from enum import Enum
from sys import stdout
import subprocess
import os

from ..systems_classes import AbstractSystem, AbstractClient


class Go(AbstractClient):
    def cmd(self, ips, client_id, result_address):
        client_path = "systems/etcd/clients/go/client"
        return "{client_path} {ips} {client_id} {result_pipe}".format(
            client_path=client_path,
            ips=ips,
            client_id=str(client_id),
            result_pipe=result_address,
        )


class GoNoMem(AbstractClient):
    def cmd(self, ips, client_id, result_address):
        client_path = "systems/etcd/clients/go-no-mem/client"
        return "{client_path} {ips} {client_id} {result_pipe}".format(
            client_path=client_path,
            ips=ips,
            client_id=str(client_id),
            result_pipe=result_address,
        )


class ClientType(Enum):
    Go = "go"
    GoNoMem = "go-no-mem"

    def __str__(self):
        return self.value


class Etcd(AbstractSystem):
    def get_client(self, args):
        if args.client == str(ClientType.Go):
            return Go()
        elif args.client == str(ClientType.GoNoMem):
            return GoNoMem()
        else:
            raise Exception("Not supported client type: " + args.client)

    def start_nodes(self, cluster):
        cluster_str = ",".join(
            self.get_node_tag(host) + "=http://" + host.IP() + ":2380"
            for i, host in enumerate(cluster)
        )

        restarters = {}
        stoppers = {}

        for host in cluster:
            tag = self.get_node_tag(host)

            def start_cmd(cluster_state):
                etcd_cmd = (
                    "systems/etcd/bin/etcd "
                    + "--data-dir=/data/{tag} "
                    + "--name {tag} "
                    + "--initial-advertise-peer-urls http://{ip}:2380 "
                    + "--listen-peer-urls http://{ip}:2380 "
                    + "--listen-client-urls http://0.0.0.0:2379 "
                    + "--advertise-client-urls http://{ip}:2379 "
                    + "--initial-cluster {cluster} "
                    + "--initial-cluster-token {cluster_token} "
                    + "--initial-cluster-state {cluster_state} "
                    + "--heartbeat-interval=100 "
                    + "--election-timeout=500"
                ).format(
                    tag=tag,
                    ip=host.IP(),
                    cluster=cluster_str,
                    cluster_state=cluster_state,
                    cluster_token="urop_cluster",
                )
                return self.add_logging(etcd_cmd, tag + ".log")

            self.start_screen(host, start_cmd("new"))
            print("Start cmd: " + start_cmd("new"))

            # We use the default arguemnt to capture the host variable semantically rather than lexically
            stoppers[tag] = lambda host=host: self.kill_screen(host)

            restarters[tag] = lambda host=host: self.start_screen(
                host, start_cmd("existing")
            )

        return restarters, stoppers

    def start_client(self, client, client_id, cluster):
        print("starting microclient: " + str(client_id))
        tag = self.get_client_tag(client)
        result_address = "src/utils/sockets/" + tag

        args_ips = ",".join("http://" + host.IP() + ":2379" for host in cluster)

        if os.path.exists(result_address):
            os.unlink(result_address)
        os.mkfifo(result_address)

        cmd = self.client_class.cmd(args_ips, client_id, result_address)
        cmd = self.add_logging(cmd, tag + ".log")

        print("Starting client with: ", cmd)
        FNULL = open(os.devnull, "w")
        sp = client.popen(
            cmd, stdin=subprocess.PIPE, stdout=FNULL, stderr=FNULL, shell=True
        )

        results = open(result_address, "r")

        return sp.stdin, results

    def parse_resp(self, resp):
        print("--------------------------------------------------")
        print(resp)
        print("--------------------------------------------------")
        endpoint_statuses = resp.split("\n")[0:-1]
        leader = ""
        for endpoint in endpoint_statuses:
            endpoint_ip = endpoint.split(",")[0].split("://")[-1].split(":")[0]
            if endpoint.split(",")[4].strip() == "true":
                return endpoint_ip

    def get_leader(self, cluster):
        ips = [host.IP() for host in cluster]
        for host in cluster:
            try:
                cmd = "ETCDCTL_API=3 systems/etcd/bin/etcdctl endpoint status --cluster"
                resp = host.cmd(cmd)
                leader_ip = self.parse_resp(resp)
                leader = cluster[ips.index(leader_ip)]
                return leader
            except:
                pass
