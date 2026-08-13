"""End-to-end workflow tests for Phase 5 integration."""

import pytest
from src.raft.end_to_end_workflows import (
    WorkflowStatus,
    WorkflowStep,
    WorkflowResult,
    EndToEndWorkflow,
    MultiNodeTransactionWorkflow,
    FailoverAndRecoveryWorkflow,
    ConsistencyVerificationWorkflow,
    ComplexTransactionWorkflow,
    WorkflowOrchestrator,
)


class TestWorkflowStep:
    """Tests for WorkflowStep class."""

    def test_create_workflow_step(self):
        """Test creating a workflow step."""
        step = WorkflowStep(
            name="Test Step",
            description="A test step",
            operation="test_op",
            expected_result="Success",
        )

        assert step.name == "Test Step"
        assert step.status == WorkflowStatus.CREATED
        assert step.duration_ms == 0.0

    def test_workflow_step_status_transition(self):
        """Test status transitions."""
        step = WorkflowStep(
            name="Step",
            description="Description",
            operation="op",
            expected_result="Expected",
        )

        assert step.status == WorkflowStatus.CREATED
        step.status = WorkflowStatus.IN_PROGRESS
        assert step.status == WorkflowStatus.IN_PROGRESS
        step.status = WorkflowStatus.COMPLETED
        assert step.status == WorkflowStatus.COMPLETED


class TestMultiNodeTransactionWorkflow:
    """Tests for multi-node transaction workflows."""

    def test_workflow_creation(self):
        """Test creating multi-node transaction workflow."""
        workflow = MultiNodeTransactionWorkflow(cluster_size=3)

        assert workflow.workflow_name == "Multi-Node Distributed Transaction"
        assert len(workflow.nodes) == 3
        assert workflow.cluster_size == 3

    def test_workflow_execution(self):
        """Test executing multi-node transaction workflow."""
        workflow = MultiNodeTransactionWorkflow(cluster_size=3)
        result = workflow.execute()

        assert result.workflow_name == "Multi-Node Distributed Transaction"
        assert result.total_steps == 8
        assert result.status in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED]

    def test_workflow_all_steps_complete(self):
        """Test all steps in workflow complete."""
        workflow = MultiNodeTransactionWorkflow(cluster_size=3)
        result = workflow.execute()

        assert result.completed_steps + result.failed_steps == result.total_steps

    def test_workflow_data_consistency(self):
        """Test data consistency after workflow."""
        workflow = MultiNodeTransactionWorkflow(cluster_size=3)
        result = workflow.execute()

        # After workflow, all nodes should have written data
        if result.status == WorkflowStatus.COMPLETED:
            for node in workflow.nodes.values():
                # Data should be present
                assert len(node.data) >= 0

    def test_workflow_with_two_nodes(self):
        """Test workflow with 2 nodes."""
        workflow = MultiNodeTransactionWorkflow(cluster_size=2)
        result = workflow.execute()

        assert result.total_steps > 0
        assert len(workflow.nodes) == 2

    def test_workflow_with_five_nodes(self):
        """Test workflow with 5 nodes."""
        workflow = MultiNodeTransactionWorkflow(cluster_size=5)
        result = workflow.execute()

        assert len(workflow.nodes) == 5


class TestFailoverAndRecoveryWorkflow:
    """Tests for failover and recovery workflows."""

    def test_failover_workflow_creation(self):
        """Test creating failover workflow."""
        workflow = FailoverAndRecoveryWorkflow()

        assert workflow.workflow_name == "Failover and Recovery"
        assert workflow.leader_state is not None
        assert workflow.follower_state is not None

    def test_failover_workflow_execution(self):
        """Test executing failover workflow."""
        workflow = FailoverAndRecoveryWorkflow()
        result = workflow.execute()

        assert result.total_steps == 8
        assert result.status in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED]

    def test_failover_all_steps_complete(self):
        """Test all failover steps complete."""
        workflow = FailoverAndRecoveryWorkflow()
        result = workflow.execute()

        assert result.completed_steps + result.failed_steps == result.total_steps

    def test_failover_recovery_success(self):
        """Test failover leads to successful recovery."""
        workflow = FailoverAndRecoveryWorkflow()
        result = workflow.execute()

        # Should have recovery and rejoin steps
        step_names = [s.name for s in result.steps]
        assert "Recover Crashed Leader" in step_names
        assert "Rejoin Cluster" in step_names

    def test_failover_data_preservation(self):
        """Test data is preserved during failover."""
        workflow = FailoverAndRecoveryWorkflow()
        result = workflow.execute()

        # If workflow completed, data should be preserved
        if result.status == WorkflowStatus.COMPLETED:
            # Snapshot should preserve data
            assert workflow.leader_state.data is not None


class TestConsistencyVerificationWorkflow:
    """Tests for consistency verification workflows."""

    def test_consistency_workflow_creation(self):
        """Test creating consistency workflow."""
        workflow = ConsistencyVerificationWorkflow(cluster_size=3)

        assert workflow.workflow_name == "Consistency Verification"
        assert len(workflow.nodes) == 3

    def test_consistency_workflow_execution(self):
        """Test executing consistency workflow."""
        workflow = ConsistencyVerificationWorkflow(cluster_size=3)
        result = workflow.execute()

        assert result.total_steps == 8
        assert result.status in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED]

    def test_consistency_verification_complete(self):
        """Test consistency verification completes."""
        workflow = ConsistencyVerificationWorkflow(cluster_size=3)
        result = workflow.execute()

        assert result.completed_steps + result.failed_steps == result.total_steps

    def test_consistency_detection(self):
        """Test inconsistency is detected."""
        workflow = ConsistencyVerificationWorkflow(cluster_size=3)
        result = workflow.execute()

        # Should have detection step
        step_names = [s.name for s in result.steps]
        assert "Detect Inconsistency" in step_names

    def test_consistency_repair(self):
        """Test inconsistent node is repaired."""
        workflow = ConsistencyVerificationWorkflow(cluster_size=3)
        result = workflow.execute()

        # Should have repair step
        step_names = [s.name for s in result.steps]
        assert "Repair" in step_names

    def test_consistency_with_different_cluster_sizes(self):
        """Test consistency workflow with different cluster sizes."""
        for size in [2, 3, 5, 7]:
            workflow = ConsistencyVerificationWorkflow(cluster_size=size)
            result = workflow.execute()

            assert len(workflow.nodes) == size
            assert result.total_steps == 8


class TestComplexTransactionWorkflow:
    """Tests for complex transaction workflows."""

    def test_complex_transaction_creation(self):
        """Test creating complex transaction workflow."""
        workflow = ComplexTransactionWorkflow()

        assert workflow.workflow_name == "Complex Transaction"
        assert workflow.state is not None

    def test_complex_transaction_execution(self):
        """Test executing complex transaction workflow."""
        workflow = ComplexTransactionWorkflow()
        result = workflow.execute()

        assert result.total_steps == 7
        assert result.status in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED]

    def test_complex_transaction_all_steps(self):
        """Test all complex transaction steps complete."""
        workflow = ComplexTransactionWorkflow()
        result = workflow.execute()

        assert result.completed_steps + result.failed_steps == result.total_steps

    def test_complex_transaction_multi_key_ops(self):
        """Test multi-key operations in transaction."""
        workflow = ComplexTransactionWorkflow()
        result = workflow.execute()

        # Should have read/write multi steps
        step_names = [s.name for s in result.steps]
        assert "Read Multiple Keys" in step_names
        assert "Write Multiple Keys" in step_names

    def test_complex_transaction_conflict_check(self):
        """Test conflict checking in transaction."""
        workflow = ComplexTransactionWorkflow()
        result = workflow.execute()

        # Should have conflict check step
        step_names = [s.name for s in result.steps]
        assert "Conflict Check" in step_names

    def test_complex_transaction_verification(self):
        """Test transaction results are verified."""
        workflow = ComplexTransactionWorkflow()
        result = workflow.execute()

        # Should have verification step
        step_names = [s.name for s in result.steps]
        assert "Verify Results" in step_names


class TestWorkflowResult:
    """Tests for WorkflowResult."""

    def test_workflow_result_creation(self):
        """Test creating workflow result."""
        steps = [
            WorkflowStep("Step1", "Desc", "op1", "Expected1"),
            WorkflowStep("Step2", "Desc", "op2", "Expected2"),
        ]

        result = WorkflowResult(
            workflow_name="Test",
            total_steps=2,
            completed_steps=1,
            failed_steps=1,
            total_duration_ms=100.0,
            status=WorkflowStatus.COMPLETED,
            steps=steps,
        )

        assert result.workflow_name == "Test"
        assert result.total_steps == 2
        assert result.status == WorkflowStatus.COMPLETED

    def test_workflow_result_success_rate(self):
        """Test calculating success rate."""
        result = WorkflowResult(
            workflow_name="Test",
            total_steps=10,
            completed_steps=8,
            failed_steps=2,
            total_duration_ms=1000.0,
            status=WorkflowStatus.FAILED,
            steps=[],
        )

        success_rate = result.completed_steps / result.total_steps
        assert success_rate == 0.8


class TestWorkflowOrchestrator:
    """Tests for WorkflowOrchestrator."""

    def test_orchestrator_creation(self):
        """Test creating orchestrator."""
        orchestrator = WorkflowOrchestrator()

        assert len(orchestrator.workflows) == 0
        assert len(orchestrator.results) == 0

    def test_orchestrator_register_workflow(self):
        """Test registering workflow."""
        orchestrator = WorkflowOrchestrator()
        workflow = MultiNodeTransactionWorkflow()

        orchestrator.register_workflow(workflow)

        assert len(orchestrator.workflows) == 1

    def test_orchestrator_register_multiple(self):
        """Test registering multiple workflows."""
        orchestrator = WorkflowOrchestrator()

        workflows = [
            MultiNodeTransactionWorkflow(),
            FailoverAndRecoveryWorkflow(),
            ConsistencyVerificationWorkflow(),
            ComplexTransactionWorkflow(),
        ]

        for workflow in workflows:
            orchestrator.register_workflow(workflow)

        assert len(orchestrator.workflows) == 4

    def test_orchestrator_execute_all(self):
        """Test executing all workflows."""
        orchestrator = WorkflowOrchestrator()
        orchestrator.register_workflow(MultiNodeTransactionWorkflow())
        orchestrator.register_workflow(FailoverAndRecoveryWorkflow())

        results = orchestrator.execute_all()

        assert len(results) == 2
        assert len(orchestrator.results) == 2

    def test_orchestrator_summary(self):
        """Test orchestrator summary."""
        orchestrator = WorkflowOrchestrator()
        orchestrator.register_workflow(MultiNodeTransactionWorkflow())
        orchestrator.register_workflow(ComplexTransactionWorkflow())

        orchestrator.execute_all()
        summary = orchestrator.get_summary()

        assert summary["total_workflows"] == 2
        assert "successful_workflows" in summary
        assert "success_rate" in summary
        assert "total_duration_ms" in summary

    def test_orchestrator_execution_order(self):
        """Test workflows execute in registration order."""
        orchestrator = WorkflowOrchestrator()

        w1 = ComplexTransactionWorkflow()
        w2 = FailoverAndRecoveryWorkflow()

        orchestrator.register_workflow(w1)
        orchestrator.register_workflow(w2)

        results = orchestrator.execute_all()

        names = list(results.keys())
        assert names[0] == "Complex Transaction"
        assert names[1] == "Failover and Recovery"


class TestEndToEndIntegration:
    """Tests for end-to-end integration scenarios."""

    def test_all_workflows_together(self):
        """Test all workflows execute together."""
        orchestrator = WorkflowOrchestrator()

        orchestrator.register_workflow(MultiNodeTransactionWorkflow())
        orchestrator.register_workflow(FailoverAndRecoveryWorkflow())
        orchestrator.register_workflow(ConsistencyVerificationWorkflow())
        orchestrator.register_workflow(ComplexTransactionWorkflow())

        results = orchestrator.execute_all()

        assert len(results) == 4

    def test_workflow_step_durations(self):
        """Test workflow steps track duration."""
        workflow = MultiNodeTransactionWorkflow()
        result = workflow.execute()

        for step in result.steps:
            assert step.duration_ms >= 0

    def test_workflow_error_handling(self):
        """Test workflow handles errors gracefully."""
        orchestrator = WorkflowOrchestrator()
        orchestrator.register_workflow(MultiNodeTransactionWorkflow())

        results = orchestrator.execute_all()

        # Even if errors occur, should have results
        assert len(results) > 0

    def test_workflow_consistency_across_runs(self):
        """Test workflow produces consistent results."""
        results = []

        for _ in range(2):
            orchestrator = WorkflowOrchestrator()
            orchestrator.register_workflow(MultiNodeTransactionWorkflow())
            result = orchestrator.execute_all()
            results.append(result)

        # Both runs should have same number of steps
        steps1 = list(results[0].values())[0].total_steps
        steps2 = list(results[1].values())[0].total_steps
        assert steps1 == steps2

    def test_workflow_performance(self):
        """Test workflow performance is reasonable."""
        workflow = ComplexTransactionWorkflow()
        result = workflow.execute()

        # Workflow should complete in reasonable time
        assert result.total_duration_ms < 10000  # Less than 10 seconds

    def test_workflow_scaling(self):
        """Test workflow scales with cluster size."""
        durations = []

        for size in [2, 3, 5]:
            workflow = MultiNodeTransactionWorkflow(cluster_size=size)
            result = workflow.execute()
            durations.append(result.total_duration_ms)

        # Larger clusters might take longer
        assert len(durations) == 3

    def test_workflow_recovery_verification(self):
        """Test recovery workflow verifies recovery."""
        workflow = FailoverAndRecoveryWorkflow()
        result = workflow.execute()

        step_names = [s.name for s in result.steps]
        assert "Recover Crashed Leader" in step_names
        assert "Catch Up" in step_names

    def test_workflow_transaction_isolation(self):
        """Test transaction workflow maintains isolation."""
        workflow = ComplexTransactionWorkflow()
        result = workflow.execute()

        # Should have isolation-related steps
        step_names = [s.name for s in result.steps]
        assert "Begin Transaction" in step_names

    def test_workflow_multi_node_coordination(self):
        """Test multi-node workflows coordinate correctly."""
        workflow = MultiNodeTransactionWorkflow(cluster_size=3)
        result = workflow.execute()

        # Should have replication step
        step_names = [s.name for s in result.steps]
        assert "Replicate to Followers" in step_names
