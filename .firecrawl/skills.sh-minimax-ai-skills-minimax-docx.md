# minimax-docx

Installation

CommandPrompt

`$ npx skills add https://github.com/minimax-ai/skills --skill minimax-docx`

SKILL.md

# minimax-docx

Create, edit, and format DOCX documents via CLI tools or direct C# scripts built on OpenXML SDK (.NET).

## Setup

**First time:**`bash scripts/setup.sh` (or `powershell scripts/setup.ps1` on Windows, `--minimal` to skip optional deps).

**First operation in session:**`scripts/env_check.sh` — do not proceed if `NOT READY`. (Skip on subsequent operations within the same session.)

## Quick Start: Direct C\# Path

When the task requires structural document manipulation (custom styles, complex tables, multi-section layouts, headers/footers, TOC, images), write C# directly instead of wrestling with CLI limitations. Use this scaffold:

```csharp
// File: scripts/dotnet/task.csx  (or a new .cs in a Console project)
// dotnet run --project scripts/dotnet/MiniMaxAIDocx.Cli -- run-script task.csx
#r "nuget: DocumentFormat.OpenXml, 3.2.0"
```

Show more

Installs

4.0K

Repository

[minimax-ai/skills](https://github.com/minimax-ai/skills "minimax-ai/skills")

GitHub Stars

13.1K

First Seen

Mar 22, 2026

Security Audits

[Gen Agent Trust HubPass](https://www.skills.sh/minimax-ai/skills/minimax-docx/security/agent-trust-hub) [SocketPass](https://www.skills.sh/minimax-ai/skills/minimax-docx/security/socket) [SnykPass](https://www.skills.sh/minimax-ai/skills/minimax-docx/security/snyk)

minimax-docx — minimax-ai/skills