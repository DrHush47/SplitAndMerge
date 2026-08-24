# docx

Installation

CommandPrompt

`$ npx skills add https://github.com/anthropics/skills --skill docx`

Summary

**Create, read, edit, and manipulate Word documents (.docx files) with full formatting control.**

- Create new .docx files from scratch using JavaScript with support for headings, tables, images, hyperlinks, footnotes, headers/footers, and table of contents
- Edit existing documents by unpacking XML, making targeted changes (including tracked changes and comments), and repacking with validation
- Extract text and analyze content using pandoc or raw XML access; convert legacy .doc files to .docx format
- Handle professional formatting: page sizes (US Letter/A4), margins, multi-column layouts, tab stops, and styled lists without manual unicode characters

SKILL.md

# DOCX creation, editing, and analysis

A `.docx` is a ZIP archive of XML files. Choose your approach by task:

| Task | Approach |
| --- | --- |
| **Create** a new document | Write a `docx` (npm) script — see gotchas below |
| **Edit** an existing document | `unzip` → edit `word/document.xml` → `zip` (docx-js cannot open existing files) |
| **Read** content | `pandoc -t markdown file.docx` |

> Script paths below are relative to this skill's directory.

## Creating with docx-js — gotchas

`docx` is preinstalled — do not run `npm install` first; write the script and `require('docx')` directly. Only if that require fails: `npm install docx`. The model knows the API; these are the footguns:

Show more

Installs

154.5K

Repository

[anthropics/skills](https://github.com/anthropics/skills "anthropics/skills")

GitHub Stars

162.7K

First Seen

Jan 19, 2026

Security Audits

[Gen Agent Trust HubPass](https://www.skills.sh/anthropics/skills/docx/security/agent-trust-hub) [SocketPass](https://www.skills.sh/anthropics/skills/docx/security/socket) [SnykPass](https://www.skills.sh/anthropics/skills/docx/security/snyk)

docx — anthropics/skills