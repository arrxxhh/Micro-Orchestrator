#!/usr/bin/env python3
"""
Fault Tolerance Module for Micro-Orchestrator
Implements automated failure detection and workload rescheduling
"""

import json
import time
import threading
import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
import requests
from enum import Enum

class NodeStatus(Enum):
    """Node status enumeration"""
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"

@dataclass
class HealthCheck:
    """Health check information"""
    last_check: datetime
    consecutive_failures: int = 0
    response_time: float = 0.0
    status: NodeStatus = NodeStatus.UNKNOWN

@dataclass
class DesiredState:
    """Desired state for workload recovery"""
    workload_id: str
    script_path: str
    target_node: str
    status: str
    created_at: datetime
    retry_count: int = 0
    max_retries: int = 3

class FaultToleranceManager:
    """Manages fault tolerance and high availability features"""
    
    def __init__(self, scheduler, state_file: str = "orchestrator_state.json"):
        self.scheduler = scheduler
        self.state_file = Path(state_file)
        self.health_checks: Dict[str, HealthCheck] = {}
        self.desired_state: Dict[str, DesiredState] = {}
        self.failed_workloads: Set[str] = set()
        self.recovery_lock = threading.Lock()
        
        # Configuration
        self.health_check_interval = 3.0  # seconds
        self.failure_threshold = 2  # consecutive failures
        self.recovery_timeout = 30.0  # seconds
        self.max_retry_attempts = 3
        
        # Start background threads
        self.health_monitor_thread = threading.Thread(
            target=self._health_monitor_loop, 
            daemon=True
        )
        self.state_persistence_thread = threading.Thread(
            target=self._state_persistence_loop, 
            daemon=True
        )
        self.recovery_thread = threading.Thread(
            target=self._recovery_loop, 
            daemon=True
        )
        
        # Load existing state
        self._load_state()
        
        # Start monitoring
        self.health_monitor_thread.start()
        self.state_persistence_thread.start()
        self.recovery_thread.start()
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("Fault Tolerance Manager initialized")
    
    def _load_state(self):
        """Load persisted state from file"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    
                # Restore desired state
                for workload_data in data.get('workloads', []):
                    workload = DesiredState(
                        workload_id=workload_data['workload_id'],
                        script_path=workload_data['script_path'],
                        target_node=workload_data['target_node'],
                        status=workload_data['status'],
                        created_at=datetime.fromisoformat(workload_data['created_at']),
                        retry_count=workload_data.get('retry_count', 0),
                        max_retries=workload_data.get('max_retries', 3)
                    )
                    self.desired_state[workload.workload_id] = workload
                
                self.logger.info(f"Loaded {len(self.desired_state)} workloads from state file")
        except Exception as e:
            self.logger.error(f"Failed to load state: {e}")
    
    def _save_state(self):
        """Save current state to file"""
        try:
            with self.recovery_lock:
                state_data = {
                    'timestamp': datetime.now().isoformat(),
                    'workloads': [
                        {
                            'workload_id': workload.workload_id,
                            'script_path': workload.script_path,
                            'target_node': workload.target_node,
                            'status': workload.status,
                            'created_at': workload.created_at.isoformat(),
                            'retry_count': workload.retry_count,
                            'max_retries': workload.max_retries
                        }
                        for workload in self.desired_state.values()
                    ]
                }
            
            with open(self.state_file, 'w') as f:
                json.dump(state_data, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Failed to save state: {e}")
    
    def _health_monitor_loop(self):
        """Background thread for health monitoring"""
        while True:
            try:
                self._perform_health_checks()
                time.sleep(self.health_check_interval)
            except Exception as e:
                self.logger.error(f"Error in health monitoring: {e}")
                time.sleep(5)
    
    def _perform_health_checks(self):
        """Perform health checks on all registered nodes"""
        with self.scheduler.node_lock:
            for node_key, node in list(self.scheduler.nodes.items()):
                self._check_node_health(node_key, node)
    
    def _check_node_health(self, node_key: str, node):
        """Check health of a specific node"""
        start_time = time.time()
        
        try:
            url = f"http://{node.host}:{node.port}/status"
            response = requests.get(url, timeout=2.0)
            
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                # Node is healthy
                if node_key not in self.health_checks:
                    self.health_checks[node_key] = HealthCheck(
                        last_check=datetime.now(),
                        status=NodeStatus.ONLINE
                    )
                else:
                    health_check = self.health_checks[node_key]
                    health_check.last_check = datetime.now()
                    health_check.consecutive_failures = 0
                    health_check.response_time = response_time
                    health_check.status = NodeStatus.ONLINE
                
                # Update node status
                node.status = "online"
                
            else:
                # Node is responding but with error
                self._handle_node_failure(node_key, node, "HTTP error")
                
        except requests.RequestException as e:
            # Node is not responding
            self._handle_node_failure(node_key, node, f"Connection error: {e}")
    
    def _handle_node_failure(self, node_key: str, node, error_msg: str):
        """Handle node failure detection"""
        if node_key not in self.health_checks:
            self.health_checks[node_key] = HealthCheck(
                last_check=datetime.now(),
                consecutive_failures=1,
                status=NodeStatus.OFFLINE
            )
        else:
            health_check = self.health_checks[node_key]
            health_check.consecutive_failures += 1
            health_check.last_check = datetime.now()
            health_check.status = NodeStatus.OFFLINE
        
        # Mark node as offline if threshold exceeded
        if self.health_checks[node_key].consecutive_failures >= self.failure_threshold:
            if node.status != "offline":
                self.logger.warning(f"Node {node_key} marked as offline: {error_msg}")
                node.status = "offline"
                self._trigger_recovery(node_key)
    
    def _trigger_recovery(self, failed_node_key: str):
        """Trigger recovery for workloads on failed node"""
        with self.recovery_lock:
            # Find workloads that were running on the failed node
            failed_workloads = []
            
            for workload_id, workload in self.desired_state.items():
                if (workload.target_node == failed_node_key and 
                    workload.status == "running"):
                    failed_workloads.append(workload_id)
                    self.failed_workloads.add(workload_id)
                    self.logger.info(f"Workload {workload_id} marked for recovery")
            
            if failed_workloads:
                self.logger.info(f"Triggering recovery for {len(failed_workloads)} workloads")
    
    def _recovery_loop(self):
        """Background thread for workload recovery"""
        while True:
            try:
                self._process_recovery_queue()
                time.sleep(1)  # Check every second
            except Exception as e:
                self.logger.error(f"Error in recovery loop: {e}")
                time.sleep(5)
    
    def _process_recovery_queue(self):
        """Process the recovery queue"""
        with self.recovery_lock:
            if not self.failed_workloads:
                return
            
            # Get a healthy node for recovery
            healthy_node = self._select_healthy_node()
            if not healthy_node:
                self.logger.warning("No healthy nodes available for recovery")
                return
            
            # Process failed workloads
            for workload_id in list(self.failed_workloads):
                if self._attempt_workload_recovery(workload_id, healthy_node):
                    self.failed_workloads.remove(workload_id)
    
    def _select_healthy_node(self) -> Optional[str]:
        """Select a healthy node for workload recovery"""
        with self.scheduler.node_lock:
            healthy_nodes = [
                node_key for node_key, node in self.scheduler.nodes.items()
                if node.status == "online" and node.cpu_usage < 80.0
            ]
            
            if not healthy_nodes:
                return None
            
            # Select node with lowest CPU usage
            return min(healthy_nodes, key=lambda n: self.scheduler.nodes[n].cpu_usage)
    
    def _attempt_workload_recovery(self, workload_id: str, target_node: str) -> bool:
        """Attempt to recover a specific workload"""
        if workload_id not in self.desired_state:
            self.logger.warning(f"Workload {workload_id} not found in desired state")
            return True  # Remove from recovery queue
        
        workload = self.desired_state[workload_id]
        
        # Check retry limits
        if workload.retry_count >= workload.max_retries:
            self.logger.error(f"Workload {workload_id} exceeded retry limit")
            workload.status = "failed"
            return True  # Remove from recovery queue
        
        try:
            # Attempt to start workload on healthy node
            node = self.scheduler.nodes[target_node]
            success = self._start_workload_on_node(workload, node)
            
            if success:
                workload.target_node = target_node
                workload.status = "running"
                workload.retry_count += 1
                self.logger.info(f"Successfully recovered workload {workload_id} on {target_node}")
                return True
            else:
                workload.retry_count += 1
                self.logger.warning(f"Failed to recover workload {workload_id}, attempt {workload.retry_count}")
                return False
                
        except Exception as e:
            workload.retry_count += 1
            self.logger.error(f"Error recovering workload {workload_id}: {e}")
            return False
    
    def _start_workload_on_node(self, workload: DesiredState, node) -> bool:
        """Start a workload on a specific node"""
        try:
            url = f"http://{node.host}:{node.port}/start"
            response = requests.post(
                url,
                json={'script_path': workload.script_path},
                timeout=10
            )
            
            return response.status_code == 200
            
        except requests.RequestException as e:
            self.logger.error(f"Error starting workload on {node.host}:{node.port}: {e}")
            return False
    
    def _state_persistence_loop(self):
        """Background thread for state persistence"""
        while True:
            try:
                self._save_state()
                time.sleep(30)  # Save every 30 seconds
            except Exception as e:
                self.logger.error(f"Error in state persistence: {e}")
                time.sleep(60)
    
    def register_workload(self, workload_id: str, script_path: str, target_node: str):
        """Register a new workload in the desired state"""
        with self.recovery_lock:
            desired_workload = DesiredState(
                workload_id=workload_id,
                script_path=script_path,
                target_node=target_node,
                status="running",
                created_at=datetime.now()
            )
            self.desired_state[workload_id] = desired_workload
            self.logger.info(f"Registered workload {workload_id} in desired state")
    
    def unregister_workload(self, workload_id: str):
        """Unregister a workload from the desired state"""
        with self.recovery_lock:
            if workload_id in self.desired_state:
                del self.desired_state[workload_id]
            if workload_id in self.failed_workloads:
                self.failed_workloads.remove(workload_id)
            self.logger.info(f"Unregistered workload {workload_id} from desired state")
    
    def get_health_summary(self) -> Dict:
        """Get health summary for all nodes"""
        summary = {
            'total_nodes': len(self.scheduler.nodes),
            'online_nodes': 0,
            'offline_nodes': 0,
            'degraded_nodes': 0,
            'failed_workloads': len(self.failed_workloads),
            'desired_workloads': len(self.desired_state),
            'node_details': []
        }
        
        with self.scheduler.node_lock:
            for node_key, node in self.scheduler.nodes.items():
                health_check = self.health_checks.get(node_key)
                node_detail = {
                    'node_key': node_key,
                    'host': node.host,
                    'port': node.port,
                    'status': node.status,
                    'cpu_usage': node.cpu_usage,
                    'memory_usage': node.memory_usage,
                    'last_check': health_check.last_check.isoformat() if health_check else None,
                    'consecutive_failures': health_check.consecutive_failures if health_check else 0,
                    'response_time': health_check.response_time if health_check else None
                }
                summary['node_details'].append(node_detail)
                
                if node.status == "online":
                    summary['online_nodes'] += 1
                elif node.status == "offline":
                    summary['offline_nodes'] += 1
                else:
                    summary['degraded_nodes'] += 1
        
        return summary
    
    def force_health_check(self):
        """Force an immediate health check on all nodes"""
        self._perform_health_checks()
        return self.get_health_summary()
    
    def get_recovery_metrics(self) -> Dict:
        """Get recovery metrics"""
        return {
            'failed_workloads': list(self.failed_workloads),
            'desired_state_count': len(self.desired_state),
            'health_checks': {
                node_key: {
                    'last_check': hc.last_check.isoformat(),
                    'consecutive_failures': hc.consecutive_failures,
                    'response_time': hc.response_time,
                    'status': hc.status.value
                }
                for node_key, hc in self.health_checks.items()
            }
        } 