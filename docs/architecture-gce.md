# Compute Engine Runner Architecture

Each GitHub Actions job triggers provisioning of a new
Google Compute Engine virtual machine.

The instance lifecycle:

1. Provisioned by Terraform
2. Registers itself as a GitHub Actions runner
3. Executes assigned workflow job
4. Performs self-termination upon completion

This architecture provides:

- Strong workload isolation
- Deterministic runner lifecycle
- Zero persistent build infrastructure
- Native integration with Google Cloud IAM and networking
- Cost efficiency through on-demand resource usage
- Scalability to handle varying workloads
- Simplified maintenance with immutable infrastructure
