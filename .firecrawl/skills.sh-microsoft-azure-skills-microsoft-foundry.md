# microsoft-foundry

Installation

CommandPrompt

`$ npx skills add https://github.com/microsoft/azure-skills --skill microsoft-foundry`

Summary

**End-to-end deployment, evaluation, and management of AI agents on Microsoft Foundry.**

- Covers the complete agent lifecycle: creation from starter samples, containerization and ACR push, hosted or prompt agent deployment, invocation, batch evaluation, and prompt optimization
- Includes specialized sub-skills for deploy, invoke, observe (evaluation and prompt optimization), trace analysis, troubleshooting, and dataset curation from production traces
- Supports project and resource provisioning, RBAC management, quota tracking, and model deployment with intelligent routing across regions and SKUs
- Requires `.foundry/agent-metadata.yaml` as the source of truth for environment-specific configuration, datasets, and evaluation test cases

SKILL.md

# Microsoft Foundry Skill

This skill helps developers work with Microsoft Foundry resources, covering model discovery and deployment, complete dev lifecycle of AI agent, evaluation workflows, and troubleshooting.

## Pre-Execution Requirements

Before using Foundry MCP operations, call the Azure MCP `foundry` tool and inspect the available Foundry MCP tools and related parameters. Treat this as the discovery/help step for MCP-based workflows.

## Sub-Skills

> **MANDATORY: Before executing ANY workflow-specific steps, you MUST read the corresponding sub-skill document.** Do not call workflow-specific MCP tools for a workflow without reading its skill document. This applies even if you already know the MCP tool parameters — the skill document contains required workflow steps, pre-checks, and validation logic that must be followed. This rule applies on every new user message that triggers a different workflow, even if the skill is already loaded.

Before executing Foundry-specific azd commands, read [azd-guidance](https://github.com/microsoft/azure-skills/blob/HEAD/.github/plugins/azure-skills/skills/microsoft-foundry/foundry-agent/azd-guidance/azd-guidance.md) first. Then read any applicable workflow-specific sub-skill. Direct questions about the Foundry azd CLI can use `azd-guidance` independently.

This skill includes specialized sub-skills for specific workflows. **Use these instead of the main skill when they match your task:**

Show more

Installs

468.3K

Repository

[microsoft/azure-skills](https://github.com/microsoft/azure-skills "microsoft/azure-skills")

GitHub Stars

1.3K

First Seen

Feb 4, 2026

Security Audits

[Gen Agent Trust HubPass](https://www.skills.sh/microsoft/azure-skills/microsoft-foundry/security/agent-trust-hub) [SocketPass](https://www.skills.sh/microsoft/azure-skills/microsoft-foundry/security/socket) [SnykWarn](https://www.skills.sh/microsoft/azure-skills/microsoft-foundry/security/snyk)

microsoft-foundry — microsoft/azure-skills