#!/usr/bin/env python3
"""
Micro-Orchestrator Python Scheduler
Central component for managing workload distribution across Node Agents
"""

import json
import time
import threading
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import requests
from flask import Flask, request, jsonify
import click
from tabulate import tabulate
from colorama import init, Fore, Style

# Import fault tolerance module
from fault_tolerance import FaultToleranceManager

# Initialize colorama for cross-platform colored output
init()

@dataclass
class NodeInfo:
    """Information about a Node Agent"""
    host: str
    port: int
    status: str = "unknown"
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    total_memory: int = 0
    available_memory: int = 0
    running_processes: int = 0
    last_seen: Optional[datetime] = None

@dataclass
class WorkloadInfo:
    """Information about a workload"""
    id: str
    script_path: str
    node_host: str
    node_port: int
    pid: Optional[int] = None
    status: str = "pending"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

class MicroOrchestratorScheduler:
    """Main scheduler class for managing Node Agents and workloads"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 5000):
        self.host = host
        self.port = port
        self.nodes: Dict[str, NodeInfo] = {}
        self.workloads: Dict[str, WorkloadInfo] = {}
        self.node_lock = threading.Lock()
        self.workload_lock = threading.Lock()
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Setup Flask app
        self.app = Flask(__name__)
        self.setup_routes()
        
        # Initialize fault tolerance manager
        self.fault_tolerance = FaultToleranceManager(self)
        
        # Start health monitoring thread (legacy - now handled by fault tolerance)
        self.monitoring_thread = threading.Thread(target=self._monitor_nodes, daemon=True)
        self.monitoring_thread.start()
    
    def setup_routes(self):
        """Setup Flask API routes"""
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Health check endpoint"""
            return jsonify({
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'nodes': len(self.nodes),
                'workloads': len(self.workloads)
            })
        
        @self.app.route('/nodes', methods=['GET'])
        def list_nodes():
            """List all registered nodes"""
            with self.node_lock:
                return jsonify([asdict(node) for node in self.nodes.values()])
        
        @self.app.route('/nodes', methods=['POST'])
        def register_node():
            """Register a new node"""
            data = request.get_json()
            if not data or 'host' not in data or 'port' not in data:
                return jsonify({'error': 'Missing host or port'}), 400
            
            node_key = f"{data['host']}:{data['port']}"
            with self.node_lock:
                self.nodes[node_key] = NodeInfo(
                    host=data['host'],
                    port=data['port'],
                    last_seen=datetime.now()
                )
            
            self.logger.info(f"Registered node: {node_key}")
            return jsonify({'message': f'Node {node_key} registered'})
        
        @self.app.route('/workloads', methods=['GET'])
        def list_workloads():
            """List all workloads"""
            with self.workload_lock:
                return jsonify([asdict(workload) for workload in self.workloads.values()])
        
        @self.app.route('/workloads', methods=['POST'])
        def submit_workload():
            """Submit a new workload"""
            data = request.get_json()
            if not data or 'script_path' not in data:
                return jsonify({'error': 'Missing script_path'}), 400
            
            workload_id = f"workload_{int(time.time())}_{len(self.workloads)}"
            
            # Find best node for workload
            best_node = self._select_best_node()
            if not best_node:
                return jsonify({'error': 'No available nodes'}), 503
            
            workload = WorkloadInfo(
                id=workload_id,
                script_path=data['script_path'],
                node_host=best_node.host,
                node_port=best_node.port
            )
            
            with self.workload_lock:
                self.workloads[workload_id] = workload
            
            # Start workload on selected node
            success = self._start_workload_on_node(workload, best_node)
            if success:
                # Register with fault tolerance manager
                node_key = f"{best_node.host}:{best_node.port}"
                self.fault_tolerance.register_workload(workload_id, data['script_path'], node_key)
                
                self.logger.info(f"Started workload {workload_id} on {best_node.host}:{best_node.port}")
                return jsonify({
                    'workload_id': workload_id,
                    'node': f"{best_node.host}:{best_node.port}",
                    'status': 'started'
                })
            else:
                # Remove failed workload
                with self.workload_lock:
                    self.workloads.pop(workload_id, None)
                return jsonify({'error': 'Failed to start workload'}), 500
        
        @self.app.route('/workloads/<workload_id>', methods=['DELETE'])
        def stop_workload(workload_id):
            """Stop a specific workload"""
            with self.workload_lock:
                workload = self.workloads.get(workload_id)
                if not workload:
                    return jsonify({'error': 'Workload not found'}), 404
            
            success = self._stop_workload_on_node(workload)
            if success:
                workload.status = "stopped"
                workload.end_time = datetime.now()
                
                # Unregister from fault tolerance manager
                self.fault_tolerance.unregister_workload(workload_id)
                
                self.logger.info(f"Stopped workload {workload_id}")
                return jsonify({'message': f'Workload {workload_id} stopped'})
            else:
                return jsonify({'error': 'Failed to stop workload'}), 500
        
        @self.app.route('/health/summary', methods=['GET'])
        def health_summary():
            """Get comprehensive health summary"""
            summary = self.fault_tolerance.get_health_summary()
            return jsonify(summary)
        
        @self.app.route('/health/check', methods=['POST'])
        def force_health_check():
            """Force an immediate health check"""
            summary = self.fault_tolerance.force_health_check()
            return jsonify(summary)
        
        @self.app.route('/recovery/metrics', methods=['GET'])
        def recovery_metrics():
            """Get recovery metrics"""
            metrics = self.fault_tolerance.get_recovery_metrics()
            return jsonify(metrics)
    
    def _select_best_node(self) -> Optional[NodeInfo]:
        """Select the best node for a new workload based on load balancing"""
        with self.node_lock:
            available_nodes = [
                node for node in self.nodes.values()
                if node.status == "online" and node.cpu_usage < 80.0
            ]
            
            if not available_nodes:
                return None
            
            # Simple load balancing: select node with lowest CPU usage
            return min(available_nodes, key=lambda n: n.cpu_usage)
    
    def _start_workload_on_node(self, workload: WorkloadInfo, node: NodeInfo) -> bool:
        """Start a workload on a specific node"""
        try:
            url = f"http://{node.host}:{node.port}"
            response = requests.post(
                f"{url}/start",
                json={'script_path': workload.script_path},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                workload.pid = data.get('pid')
                workload.status = "running"
                workload.start_time = datetime.now()
                return True
            else:
                self.logger.error(f"Failed to start workload on {node.host}:{node.port}")
                return False
                
        except requests.RequestException as e:
            self.logger.error(f"Error starting workload on {node.host}:{node.port}: {e}")
            return False
    
    def _stop_workload_on_node(self, workload: WorkloadInfo) -> bool:
        """Stop a workload on its assigned node"""
        if not workload.pid:
            return False
        
        try:
            url = f"http://{workload.node_host}:{workload.node_port}"
            response = requests.post(
                f"{url}/stop",
                json={'pid': workload.pid},
                timeout=10
            )
            
            return response.status_code == 200
            
        except requests.RequestException as e:
            self.logger.error(f"Error stopping workload: {e}")
            return False
    
    def _monitor_nodes(self):
        """Background thread to monitor node health"""
        while True:
            try:
                with self.node_lock:
                    for node_key, node in list(self.nodes.items()):
                        self._update_node_status(node)
                
                time.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Error in node monitoring: {e}")
                time.sleep(60)
    
    def _update_node_status(self, node: NodeInfo):
        """Update status of a specific node"""
        try:
            url = f"http://{node.host}:{node.port}/status"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                node.status = "online"
                node.cpu_usage = data.get('cpu_usage', 0.0)
                node.memory_usage = data.get('memory_usage', 0.0)
                node.total_memory = data.get('total_memory', 0)
                node.available_memory = data.get('available_memory', 0)
                node.running_processes = data.get('running_processes', 0)
                node.last_seen = datetime.now()
            else:
                node.status = "offline"
                
        except requests.RequestException:
            node.status = "offline"
    
    def run(self):
        """Start the scheduler"""
        self.logger.info(f"Starting Micro-Orchestrator Scheduler on {self.host}:{self.port}")
        self.app.run(host=self.host, port=self.port, debug=False)

@click.group()
def cli():
    """Micro-Orchestrator Scheduler CLI"""
    pass

@cli.command()
@click.option('--host', default='0.0.0.0', help='Host to bind to')
@click.option('--port', default=5000, help='Port to bind to')
def start(host, port):
    """Start the scheduler"""
    scheduler = MicroOrchestratorScheduler(host=host, port=port)
    scheduler.run()

@cli.command()
@click.option('--host', default='localhost', help='Scheduler host')
@click.option('--port', default=5000, help='Scheduler port')
def status(host, port):
    """Show scheduler status"""
    try:
        response = requests.get(f"http://{host}:{port}/health")
        if response.status_code == 200:
            data = response.json()
            print(f"{Fore.GREEN}✓ Scheduler is healthy{Style.RESET_ALL}")
            print(f"Nodes: {data['nodes']}")
            print(f"Workloads: {data['workloads']}")
        else:
            print(f"{Fore.RED}✗ Scheduler is not responding{Style.RESET_ALL}")
    except requests.RequestException:
        print(f"{Fore.RED}✗ Cannot connect to scheduler{Style.RESET_ALL}")

@cli.command()
@click.option('--host', default='localhost', help='Scheduler host')
@click.option('--port', default=5000, help='Scheduler port')
def nodes(host, port):
    """List all nodes"""
    try:
        response = requests.get(f"http://{host}:{port}/nodes")
        if response.status_code == 200:
            nodes_data = response.json()
            if nodes_data:
                headers = ['Host', 'Port', 'Status', 'CPU %', 'Memory %', 'Processes']
                table_data = []
                for node in nodes_data:
                    status_color = Fore.GREEN if node['status'] == 'online' else Fore.RED
                    table_data.append([
                        node['host'],
                        node['port'],
                        f"{status_color}{node['status']}{Style.RESET_ALL}",
                        f"{node['cpu_usage']:.1f}",
                        f"{node['memory_usage']:.1f}",
                        node['running_processes']
                    ])
                print(tabulate(table_data, headers=headers, tablefmt='grid'))
            else:
                print("No nodes registered")
        else:
            print(f"{Fore.RED}Failed to get nodes{Style.RESET_ALL}")
    except requests.RequestException:
        print(f"{Fore.RED}Cannot connect to scheduler{Style.RESET_ALL}")

@cli.command()
@click.option('--host', default='localhost', help='Scheduler host')
@click.option('--port', default=5000, help='Scheduler port')
def workloads(host, port):
    """List all workloads"""
    try:
        response = requests.get(f"http://{host}:{port}/workloads")
        if response.status_code == 200:
            workloads_data = response.json()
            if workloads_data:
                headers = ['ID', 'Script', 'Node', 'Status', 'PID', 'Start Time']
                table_data = []
                for workload in workloads_data:
                    status_color = Fore.GREEN if workload['status'] == 'running' else Fore.YELLOW
                    table_data.append([
                        workload['id'],
                        workload['script_path'],
                        f"{workload['node_host']}:{workload['node_port']}",
                        f"{status_color}{workload['status']}{Style.RESET_ALL}",
                        workload.get('pid', '-'),
                        workload.get('start_time', '-')
                    ])
                print(tabulate(table_data, headers=headers, tablefmt='grid'))
            else:
                print("No workloads")
        else:
            print(f"{Fore.RED}Failed to get workloads{Style.RESET_ALL}")
    except requests.RequestException:
        print(f"{Fore.RED}Cannot connect to scheduler{Style.RESET_ALL}")

@cli.command()
@click.argument('script_path')
@click.option('--host', default='localhost', help='Scheduler host')
@click.option('--port', default=5000, help='Scheduler port')
def submit(script_path, host, port):
    """Submit a new workload"""
    try:
        response = requests.post(
            f"http://{host}:{port}/workloads",
            json={'script_path': script_path}
        )
        if response.status_code == 200:
            data = response.json()
            print(f"{Fore.GREEN}✓ Workload submitted successfully{Style.RESET_ALL}")
            print(f"Workload ID: {data['workload_id']}")
            print(f"Node: {data['node']}")
        else:
            error_data = response.json()
            print(f"{Fore.RED}✗ Failed to submit workload: {error_data.get('error', 'Unknown error')}{Style.RESET_ALL}")
    except requests.RequestException:
        print(f"{Fore.RED}✗ Cannot connect to scheduler{Style.RESET_ALL}")

@cli.command()
@click.argument('workload_id')
@click.option('--host', default='localhost', help='Scheduler host')
@click.option('--port', default=5000, help='Scheduler port')
def stop(workload_id, host, port):
    """Stop a workload"""
    try:
        response = requests.delete(f"http://{host}:{port}/workloads/{workload_id}")
        if response.status_code == 200:
            print(f"{Fore.GREEN}✓ Workload {workload_id} stopped{Style.RESET_ALL}")
        else:
            error_data = response.json()
            print(f"{Fore.RED}✗ Failed to stop workload: {error_data.get('error', 'Unknown error')}{Style.RESET_ALL}")
    except requests.RequestException:
        print(f"{Fore.RED}✗ Cannot connect to scheduler{Style.RESET_ALL}")

@cli.command()
@click.option('--host', default='localhost', help='Scheduler host')
@click.option('--port', default=5000, help='Scheduler port')
def health(host, port):
    """Show comprehensive health summary"""
    try:
        response = requests.get(f"http://{host}:{port}/health/summary")
        if response.status_code == 200:
            data = response.json()
            print(f"{Fore.BLUE}=== Health Summary ==={Style.RESET_ALL}")
            print(f"Total Nodes: {data['total_nodes']}")
            print(f"Online Nodes: {data['online_nodes']}")
            print(f"Offline Nodes: {data['offline_nodes']}")
            print(f"Failed Workloads: {data['failed_workloads']}")
            print(f"Desired Workloads: {data['desired_workloads']}")
            
            if data['node_details']:
                print(f"\n{Fore.BLUE}=== Node Details ==={Style.RESET_ALL}")
                headers = ['Node', 'Status', 'CPU %', 'Memory %', 'Failures', 'Response Time']
                table_data = []
                for node in data['node_details']:
                    status_color = Fore.GREEN if node['status'] == 'online' else Fore.RED
                    table_data.append([
                        f"{node['host']}:{node['port']}",
                        f"{status_color}{node['status']}{Style.RESET_ALL}",
                        f"{node['cpu_usage']:.1f}",
                        f"{node['memory_usage']:.1f}",
                        node['consecutive_failures'],
                        f"{node['response_time']:.3f}s" if node['response_time'] else "N/A"
                    ])
                print(tabulate(table_data, headers=headers, tablefmt='grid'))
        else:
            print(f"{Fore.RED}Failed to get health summary{Style.RESET_ALL}")
    except requests.RequestException:
        print(f"{Fore.RED}Cannot connect to scheduler{Style.RESET_ALL}")

@cli.command()
@click.option('--host', default='localhost', help='Scheduler host')
@click.option('--port', default=5000, help='Scheduler port')
def recovery(host, port):
    """Show recovery metrics"""
    try:
        response = requests.get(f"http://{host}:{port}/recovery/metrics")
        if response.status_code == 200:
            data = response.json()
            print(f"{Fore.BLUE}=== Recovery Metrics ==={Style.RESET_ALL}")
            print(f"Failed Workloads: {len(data['failed_workloads'])}")
            print(f"Desired State Count: {data['desired_state_count']}")
            
            if data['failed_workloads']:
                print(f"\n{Fore.YELLOW}Failed Workloads:{Style.RESET_ALL}")
                for workload_id in data['failed_workloads']:
                    print(f"  - {workload_id}")
            
            if data['health_checks']:
                print(f"\n{Fore.BLUE}Health Check Details:{Style.RESET_ALL}")
                for node_key, health in data['health_checks'].items():
                    status_color = Fore.GREEN if health['status'] == 'online' else Fore.RED
                    print(f"  {node_key}: {status_color}{health['status']}{Style.RESET_ALL} "
                          f"(Failures: {health['consecutive_failures']}, "
                          f"Response: {health['response_time']:.3f}s)")
        else:
            print(f"{Fore.RED}Failed to get recovery metrics{Style.RESET_ALL}")
    except requests.RequestException:
        print(f"{Fore.RED}Cannot connect to scheduler{Style.RESET_ALL}")

@cli.command()
@click.option('--host', default='localhost', help='Scheduler host')
@click.option('--port', default=5000, help='Scheduler port')
def check(host, port):
    """Force immediate health check"""
    try:
        response = requests.post(f"http://{host}:{port}/health/check")
        if response.status_code == 200:
            data = response.json()
            print(f"{Fore.GREEN}✓ Health check completed{Style.RESET_ALL}")
            print(f"Online Nodes: {data['online_nodes']}")
            print(f"Offline Nodes: {data['offline_nodes']}")
            print(f"Failed Workloads: {data['failed_workloads']}")
        else:
            print(f"{Fore.RED}Failed to perform health check{Style.RESET_ALL}")
    except requests.RequestException:
        print(f"{Fore.RED}Cannot connect to scheduler{Style.RESET_ALL}")

if __name__ == '__main__':
    cli() 